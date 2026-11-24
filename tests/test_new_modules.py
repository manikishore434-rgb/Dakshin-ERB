"""Automated tests for SNACKFLOW ERP advanced modules:
MRP, Quality Management, Batch Traceability, Procurement, Profitability, and Alerts.
"""
import datetime as dt
import unittest

from app import create_app, seed
from app.db import connect, tx
from app.services import alerts, decisions, mrp, procurement, production, profitability, quality, sales, stock, traceability
from app.util import ServiceError, to_milli, to_paise

TODAY = dt.date.today().isoformat()


class AdvancedModulesTest(unittest.TestCase):
    def setUp(self):
        self.db = connect(":memory:")
        seed.seed(self.db)
        self.ids = {r["code"]: r["id"] for r in self.db.execute("SELECT id, code FROM items")}
        self.cust = {r["name"]: r["id"] for r in self.db.execute("SELECT id, name FROM customers")}
        get = lambda n: dict(self.db.execute("SELECT * FROM users WHERE username=?", (n,)).fetchone())
        self.admin, self.prod, self.sa = get("admin"), get("production"), get("salesman_a")

    # 1. Procurement & PO Lifecycle
    def test_procurement_po_lifecycle(self):
        supp = self.db.execute("SELECT id FROM suppliers LIMIT 1").fetchone()
        self.assertIsNotNone(supp)
        poid = procurement.create_purchase_order(
            self.db, self.admin, supp["id"], TODAY,
            [{"item_id": self.ids["RM-FLOUR"], "qty_milli": to_milli(50), "rate_paise": to_paise(45)}],
            "Urgent flour order"
        )
        po = self.db.execute("SELECT * FROM purchase_orders WHERE id=?", (poid,)).fetchone()
        self.assertEqual(po["status"], "draft")
        self.assertEqual(po["total_amount_paise"], to_paise(2250))

        # Approve
        procurement.approve_purchase_order(self.db, self.admin, poid)
        po = self.db.execute("SELECT * FROM purchase_orders WHERE id=?", (poid,)).fetchone()
        self.assertEqual(po["status"], "approved")

        # Receive Goods (GRN)
        flour_before, _ = stock.balance(self.db, self.ids["RM-FLOUR"])
        pur_id, grn_no = procurement.receive_purchase_order(
            self.db, self.prod, poid, TODAY, "INV-VENDOR-01", None, "LOT-FLOUR-TEST", None
        )
        flour_after, _ = stock.balance(self.db, self.ids["RM-FLOUR"])
        self.assertEqual(flour_after - flour_before, to_milli(50))
        self.assertTrue(grn_no.startswith("GRN-"))

        # Check PO status changed to received
        po = self.db.execute("SELECT * FROM purchase_orders WHERE id=?", (poid,)).fetchone()
        self.assertEqual(po["status"], "received")

    # 2. Quality Management & Dispatch Blocking
    def test_quality_inspection_blocks_dispatch_when_rejected(self):
        # 1. Create a production run and complete it
        rid = production.start_run(self.db, self.prod, self.ids["FG-MUR200"], 1, {self.ids["RM-FLOUR"]: to_milli(40)}, TODAY)
        production.complete_run(self.db, self.prod, rid, to_milli(190), 0, None, TODAY)
        run = self.db.execute("SELECT * FROM production_runs WHERE id=?", (rid,)).fetchone()

        # 2. Register QA inspection and mark REJECTED
        qid = quality.create_inspection(
            self.db, self.prod, "finished_goods", self.ids["FG-MUR200"],
            "production_run", rid, run["batch_no"], "5 pkts", {}, "Testing rancidity"
        )
        quality.record_verdict(
            self.db, self.prod, qid, "rejected",
            defect_category="Rancidity / Off-Flavor",
            defect_description="High peroxide value detected",
            corrective_action="Quarantine entire batch and scrap"
        )

        # Verify inspection is rejected
        qi = quality.get_inspection(self.db, qid)
        self.assertEqual(qi["status"], "rejected")

        # Verify dispatch is strictly BLOCKED by QA enforcement
        oid, _ = sales.create_order(
            self.db, self.sa, self.cust["Retailer A"],
            [{"item_id": self.ids["FG-MUR200"], "qty": 20, "unit": "packet"}]
        )
        sales.approve_order(self.db, self.admin, oid)
        inv = sales.create_invoice(self.db, self.admin, oid, TODAY)

        with self.assertRaises(ServiceError) as ctx:
            sales.dispatch(self.db, self.admin, inv, TODAY)
        self.assertIn("Quality Control", str(ctx.exception))

    # 3. Material Requirements Planning (MRP)
    def test_mrp_calculation_and_suggestions(self):
        # Create a large order of 300 packets (on hand is only 50 packets)
        oid, _ = sales.create_order(
            self.db, self.sa, self.cust["Retailer A"],
            [{"item_id": self.ids["FG-MUR200"], "qty": 300, "unit": "packet"}]
        )
        sales.approve_order(self.db, self.admin, oid, allow_shortage=True)

        # Run MRP
        mrp_data = mrp.run_mrp(self.db)
        self.assertTrue(len(mrp_data["demand_orders"]) > 0)
        self.assertTrue(len(mrp_data["production_suggestions"]) > 0)
        fg_sugg = mrp_data["production_suggestions"][0]
        self.assertGreater(fg_sugg["batches_needed"], 0)

        # Auto-generate POs from MRP
        created_pos = mrp.create_suggested_pos_action(self.db, self.admin)
        if mrp_data["shortages"]:
            self.assertTrue(len(created_pos) > 0)

    # 4. End-to-End Batch Traceability
    def test_batch_traceability(self):
        # Run a production batch
        rid = production.start_run(self.db, self.prod, self.ids["FG-MUR200"], 1, {self.ids["RM-FLOUR"]: to_milli(40)}, TODAY)
        production.complete_run(self.db, self.prod, rid, to_milli(190), 0, None, TODAY)
        run = self.db.execute("SELECT * FROM production_runs WHERE id=?", (rid,)).fetchone()

        # Trace by batch number
        res = traceability.trace_batch(self.db, run["batch_no"])
        self.assertTrue(res["found"])
        self.assertEqual(res["type"], "finished_batch")
        self.assertEqual(res["run"]["run_no"], run["run_no"])
        self.assertTrue(len(res["materials"]) > 0)

    # 5. Profitability & Unit Economics
    def test_profitability_calculations(self):
        # Run a batch and complete it
        rid = production.start_run(self.db, self.prod, self.ids["FG-MUR200"], 1, {self.ids["RM-FLOUR"]: to_milli(40)}, TODAY)
        production.complete_run(self.db, self.prod, rid, to_milli(190), 0, None, TODAY)

        # Invoice and dispatch 50 packets
        oid, _ = sales.create_order(
            self.db, self.sa, self.cust["Retailer A"],
            [{"item_id": self.ids["FG-MUR200"], "qty": 50, "unit": "packet"}]
        )
        sales.approve_order(self.db, self.admin, oid)
        inv = sales.create_invoice(self.db, self.admin, oid, TODAY)
        sales.dispatch(self.db, self.admin, inv, TODAY)

        # Check profitability analytics
        prods = profitability.calculate_product_profitability(self.db)
        self.assertTrue(len(prods) > 0)
        fg = prods[0]
        self.assertGreater(fg["net_revenue_paise"], 0)
        self.assertGreater(fg["unit_cost_paise"], 0)

    # 6. Smart Alerts & Decision Support
    def test_alerts_and_decisions(self):
        alts = alerts.get_active_alerts(self.db)
        self.assertIsInstance(alts, list)
        recs = decisions.generate_recommendations(self.db)
        self.assertIsInstance(recs, list)
        if recs:
            r = recs[0]
            self.assertIn("priority", r)
            self.assertIn("suggested_action", r)


class HttpViewsTest(unittest.TestCase):
    def setUp(self):
        import os, tempfile
        self.tmp = tempfile.mkdtemp()
        self.app = create_app(os.path.join(self.tmp, "t_new.db"))

    def client(self, user):
        c = self.app.test_client()
        r = c.post("/login", data={"username": user, "password": "demo123"})
        self.assertEqual(r.status_code, 302)
        return c

    def test_new_modules_http(self):
        ad = self.client("admin")
        self.assertEqual(ad.get("/mrp").status_code, 200)
        self.assertEqual(ad.get("/quality/inspections").status_code, 200)
        self.assertEqual(ad.get("/traceability").status_code, 200)
        self.assertEqual(ad.get("/procurement/orders").status_code, 200)
        self.assertEqual(ad.get("/procurement/suppliers").status_code, 200)
        self.assertEqual(ad.get("/profitability").status_code, 200)
        self.assertEqual(ad.get("/decisions").status_code, 200)
        self.assertEqual(ad.get("/alerts").status_code, 200)
        self.assertEqual(ad.get("/owner/suite").status_code, 200)
        self.assertEqual(ad.get("/dashboard").status_code, 200)
        self.assertEqual(ad.get("/roles").status_code, 200)

        # Global search API
        search_res = ad.get("/api/search?q=Retailer").get_json()
        self.assertIn("results", search_res)


if __name__ == "__main__":
    unittest.main()
