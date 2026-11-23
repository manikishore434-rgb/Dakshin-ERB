"""Stock never goes negative, credit notes reverse invoices, idempotent offline sync, role access."""
import datetime as dt
import unittest

from app import benchmark, create_app, seed
from app.db import connect, tx
from app.services import production, sales, stock
from app.util import ServiceError, to_milli

TODAY = dt.date.today().isoformat()


class RulesTest(unittest.TestCase):
    def setUp(self):
        self.db = connect(":memory:")
        seed.seed(self.db)
        self.ids = {r["code"]: r["id"] for r in self.db.execute("SELECT id, code FROM items")}
        self.cust = {r["name"]: r["id"] for r in self.db.execute("SELECT id, name FROM customers")}
        get = lambda n: dict(self.db.execute("SELECT * FROM users WHERE username=?", (n,)).fetchone())
        self.admin, self.prod, self.sa = get("admin"), get("production"), get("salesman_a")

    def order(self, qty, uuid=None, unit="packet"):
        oid, _ = sales.create_order(self.db, self.sa, self.cust["Retailer A"], [{"item_id": self.ids["FG-MUR200"], "qty": qty, "unit": unit}], uuid)
        return oid

    def test_cannot_issue_more_than_stock(self):
        with self.assertRaises(stock.InsufficientStock):
            production.start_run(self.db, self.prod, self.ids["FG-MUR200"], 1, {self.ids["RM-FLOUR"]: to_milli(500)}, TODAY)

    def test_offline_resync_is_idempotent(self):
        a = self.order(10, "same-uuid")
        b = self.order(10, "same-uuid")
        self.assertEqual(a, b)
        self.assertEqual(self.db.execute("SELECT COUNT(*) n FROM orders").fetchone()["n"], 1)

    def test_carton_order_converts_to_packets(self):
        oid = self.order(2, unit="carton")
        self.assertEqual(self.db.execute("SELECT qty_milli FROM order_lines WHERE order_id=?", (oid,)).fetchone()["qty_milli"], 40000)

    def test_shortage_blocks_approval_unless_overridden_and_blocks_dispatch(self):
        oid = self.order(500)   # only 50 packets in stock at the start
        with self.assertRaises(ServiceError):
            sales.approve_order(self.db, self.admin, oid)
        sales.approve_order(self.db, self.admin, oid, allow_shortage=True)
        inv = sales.create_invoice(self.db, self.admin, oid, TODAY)
        with self.assertRaises(stock.InsufficientStock):
            sales.dispatch(self.db, self.admin, inv, TODAY)
        self.assertEqual(stock.balance(self.db, self.ids["FG-MUR200"])[0], to_milli(50))

    def test_credit_note_returns_stock_and_clears_outstanding(self):
        oid = self.order(20)
        sales.approve_order(self.db, self.admin, oid)
        inv = sales.create_invoice(self.db, self.admin, oid, TODAY)
        sales.dispatch(self.db, self.admin, inv, TODAY)
        self.assertEqual(stock.balance(self.db, self.ids["FG-MUR200"])[0], to_milli(30))
        sales.cancel_invoice(self.db, self.admin, inv, "wrong price", TODAY)
        self.assertEqual(stock.balance(self.db, self.ids["FG-MUR200"])[0], to_milli(50))
        self.assertEqual(self.db.execute("SELECT status FROM invoices WHERE id=?", (inv,)).fetchone()["status"], "cancelled")
        recs, _ = sales.receivables(self.db, TODAY)
        self.assertEqual([r for r in recs if r["outstanding"] > 0], [])
        self.assertEqual(self.db.execute("SELECT COUNT(*) n FROM credit_notes").fetchone()["n"], 1)

    def test_invoice_numbers_run_by_financial_year(self):
        o1, o2 = self.order(1), self.order(1)
        for o in (o1, o2):
            sales.approve_order(self.db, self.admin, o)
        a = sales.create_invoice(self.db, self.admin, o1, "2027-03-31")
        b = sales.create_invoice(self.db, self.admin, o2, "2027-04-01")
        nos = [self.db.execute("SELECT invoice_no FROM invoices WHERE id=?", (i,)).fetchone()[0] for i in (a, b)]
        self.assertEqual(nos, ["INV/2026-27/0001", "INV/2027-28/0001"])

    def test_cancel_run_reverses_stock(self):
        rid = production.start_run(self.db, self.prod, self.ids["FG-MUR200"], 1, {self.ids["RM-FLOUR"]: to_milli(40)}, TODAY)
        production.complete_run(self.db, self.prod, rid, to_milli(190), 0, None, TODAY)
        production.cancel_run(self.db, self.prod, rid, "test")
        self.assertEqual(stock.balance(self.db, self.ids["RM-FLOUR"])[0], to_milli(100))
        self.assertEqual(stock.balance(self.db, self.ids["FG-MUR200"])[0], to_milli(50))

    def test_default_packaging_consumption(self):
        rid = production.start_run(self.db, self.prod, self.ids["FG-MUR200"], 1, {self.ids["RM-FLOUR"]: to_milli(40)}, TODAY)
        production.complete_run(self.db, self.prod, rid, to_milli(190), to_milli(5), None, TODAY)
        self.assertEqual(stock.balance(self.db, self.ids["PK-POUCH200"])[0], to_milli(500 - 195))
        self.assertEqual(stock.balance(self.db, self.ids["PK-CARTON"])[0], to_milli(30 - 10))   # ceil(190/20)


class WebTest(unittest.TestCase):
    def setUp(self):
        import os, tempfile
        self.tmp = tempfile.mkdtemp()
        self.app = create_app(os.path.join(self.tmp, "t.db"))

    def client(self, user):
        c = self.app.test_client()
        r = c.post("/login", data={"username": user, "password": "demo123"})
        self.assertEqual(r.status_code, 302)
        return c

    def test_role_access(self):
        self.assertEqual(self.client("salesman_a").get("/admin/orders").status_code, 403)
        self.assertEqual(self.client("production").get("/reports/sales-register").status_code, 403)
        self.assertEqual(self.client("accountant").get("/prod/runs").status_code, 403)
        self.assertEqual(self.client("accountant").post("/admin/payments", data={"customer_id": 1, "amount": 1}).status_code, 403)
        self.assertEqual(self.client("admin").get("/admin/orders").status_code, 200)
        self.assertEqual(self.app.test_client().get("/admin/orders").status_code, 302)

    def test_full_flow_over_http(self):
        sa, ad, pr, acc = (self.client(u) for u in ("salesman_a", "admin", "production", "accountant"))
        cat = sa.get("/api/catalog").get_json()
        pid, cid = cat["products"][0]["id"], [c["id"] for c in cat["customers"] if c["name"] == "Retailer A"][0]
        body = {"client_uuid": "u-1", "customer_id": cid, "lines": [{"item_id": pid, "qty": 2, "unit": "carton"}]}
        j = sa.post("/api/orders", json=body).get_json()
        self.assertTrue(j["ok"])
        self.assertTrue(sa.post("/api/orders", json=body).get_json()["duplicate"])
        self.assertIn(b"ORD-00001", sa.get("/my/orders").data)
        self.assertEqual(ad.post(f"/admin/orders/{j['id']}/approve").status_code, 302)
        ad.post(f"/admin/orders/{j['id']}/invoice")
        pdf = ad.get("/invoice/1.pdf")
        self.assertEqual((pdf.status_code, pdf.data[:4]), (200, b"%PDF"))
        ad.post("/admin/invoices/1/dispatch")
        self.assertIn(b"Dispatched", ad.get(f"/admin/orders/{j['id']}").data)
        # step 1 of the benchmark through the receipts form, then a production run over HTTP
        self.assertEqual(pr.post("/prod/purchases", data={"supplier_id": 1, "supplier_invoice_no": "FL-1", "item_1": 1, "qty_1": "60",
                                                          "unit_1": "kg", "rate_1": "45"}).status_code, 302)
        r = pr.post("/prod/runs/new", data={"product_id": pid, "batches": "1", "issue_1": "40", "unit_1": "kg", "issue_2": "10.5", "unit_2": "l",
                                           "issue_3": "1200", "unit_3": "g"})
        self.assertEqual(r.status_code, 302)
        pr.post("/prod/runs/1/complete", data={"good": "188", "damaged": "6", "pack_5": "9"})
        pr.post("/prod/runs/1/overhead", data={"kind": "labour", "amount": "1200"})
        pr.post("/prod/runs/1/overhead", data={"kind": "power_gas", "amount": "600"})
        self.assertIn(b"31.14", pr.get("/prod/runs/1").data)
        for slug in ("sales-register", "gst-summary", "stock-summary", "stock-ledger", "production", "outstanding", "purchase-register"):
            for fmt, sig in (("html", b"<table"), ("csv", b","), ("xlsx", b"PK"), ("pdf", b"%PDF")):
                resp = acc.get(f"/reports/{slug}?fmt={fmt}")
                self.assertEqual(resp.status_code, 200, (slug, fmt))
                self.assertIn(sig, resp.data[:200000], (slug, fmt))


if __name__ == "__main__":
    unittest.main()
