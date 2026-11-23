"""Runs the Section 5 benchmark end to end through the service layer and checks every expected figure.

    python -m app.benchmark            # runs on a throw-away in-memory database
"""
import sys
from decimal import Decimal

from . import seed as seed_mod
from .db import connect, tx
from .services import production, sales, stock
from .services.stock import InsufficientStock
from .util import money, qty, to_milli, to_paise


def _user(db, name):
    return dict(db.execute("SELECT * FROM users WHERE username=?", (name,)).fetchone())


def run(db, date):
    """Executes steps 1-8 and returns a dict of results."""
    ids = {r["code"]: r["id"] for r in db.execute("SELECT id, code FROM items")}
    cust = {r["name"]: r["id"] for r in db.execute("SELECT id, name FROM customers")}
    admin, prod, sa, sb = (_user(db, n) for n in ("admin", "production", "salesman_a", "salesman_b"))
    res = {}
    with tx(db):  # 1. purchase 60 kg flour @ 45
        from .routes_helpers import record_purchase
        record_purchase(db, prod, None, date, "FL-001", [(ids["RM-FLOUR"], 60, "kg", "45")])
    with tx(db):  # 2. start run, issue 40 kg flour, 10.5 L oil, 1.2 kg spice
        run_id = production.start_run(db, prod, ids["FG-MUR200"], 1, {
            ids["RM-FLOUR"]: to_milli(40), ids["RM-OIL"]: to_milli("10.5"), ids["RM-SPICE"]: to_milli("1.2")}, date)
    with tx(db):  # 3. 188 good packets, 6 pouches damaged, 9 cartons used
        production.complete_run(db, prod, run_id, to_milli(188), to_milli(6), {ids["PK-CARTON"]: to_milli(9)}, date)
    for k, code in [("flour", "RM-FLOUR"), ("oil", "RM-OIL"), ("pouches", "PK-POUCH200"), ("cartons", "PK-CARTON"), ("spice", "RM-SPICE")]:
        res[f"{k}_closing"] = stock.balance(db, ids[code])[0]
    res["fg_after_run"] = stock.balance(db, ids["FG-MUR200"])[0]
    with tx(db):  # 4. salesman A orders 150 packets for Retailer A
        order_a, _ = sales.create_order(db, sa, cust["Retailer A"], [{"item_id": ids["FG-MUR200"], "qty": 150, "unit": "packet"}], "bench-a")
    with tx(db):  # 5. approve, invoice (CGST+SGST), dispatch
        sales.approve_order(db, admin, order_a)
        inv_a = sales.create_invoice(db, admin, order_a, date)
        sales.dispatch(db, admin, inv_a, date)
    res["fg_after_dispatch"] = stock.balance(db, ids["FG-MUR200"])[0]
    res["invoice_a"] = dict(db.execute("SELECT * FROM invoices WHERE id=?", (inv_a,)).fetchone())
    with tx(db):  # 6. salesman B orders 120 for Distributor B -> shortage
        order_b, _ = sales.create_order(db, sb, cust["Distributor B"], [{"item_id": ids["FG-MUR200"], "qty": 120, "unit": "packet"}], "bench-b")
    res["order_b_check"] = sales.stock_check(db, order_b)[0]
    try:
        sales.approve_order(db, admin, order_b)
        res["order_b_blocked"] = False
    except Exception as e:  # noqa: BLE001
        res["order_b_blocked"] = str(e)
    with tx(db):  # 6b. show IGST: approve with back-order and invoice, but dispatch must fail on stock
        sales.approve_order(db, admin, order_b, allow_shortage=True)
        inv_b = sales.create_invoice(db, admin, order_b, date)
    res["invoice_b"] = dict(db.execute("SELECT * FROM invoices WHERE id=?", (inv_b,)).fetchone())
    try:
        with tx(db):
            sales.dispatch(db, admin, inv_b, date)
        res["dispatch_b_blocked"] = False
    except InsufficientStock as e:
        res["dispatch_b_blocked"] = str(e)
    with tx(db):  # 7. payment of Rs 4,000 from Retailer A
        sales.record_payment(db, admin, cust["Retailer A"], to_paise(4000), date, "UPI", "UTR123", inv_a)
    rec, _ = sales.receivables(db, date)
    res["outstanding_a"] = next(r["outstanding"] for r in rec if r["invoice"]["id"] == inv_a)
    with tx(db):  # 8. labour 1,200 + gas/power 600
        production.add_overhead(db, prod, run_id, "labour", to_paise(1200), "", date)
        production.add_overhead(db, prod, run_id, "power_gas", to_paise(600), "", date)
    res["summary"] = production.run_summary(db, run_id)
    res["run_id"] = run_id
    return res


def check(res):
    s = res["summary"]
    oil = next(l for l in s["lines"] if l["name"] == "Cooking oil")
    checks = [
        ("Flour closing balance", "120 kg", f"{qty(res['flour_closing'])} kg", res["flour_closing"] == to_milli(120)),
        ("Oil closing balance", "19.5 L", f"{qty(res['oil_closing'])} L", res["oil_closing"] == to_milli("19.5")),
        ("Pouches closing balance", "306", qty(res["pouches_closing"]), res["pouches_closing"] == to_milli(306)),
        ("Finished goods after run", "238", qty(res["fg_after_run"]), res["fg_after_run"] == to_milli(238)),
        ("Finished goods after dispatch", "88", qty(res["fg_after_dispatch"]), res["fg_after_dispatch"] == to_milli(88)),
        ("Yield variance (flagged)", "-6.00% flagged", f"{s['yield_var_pct']}% {'flagged' if s['yield_flag'] else 'ok'}",
         s["yield_var_pct"] == Decimal("-6.00") and s["yield_flag"]),
        ("Oil variance (flagged)", "+5.00% flagged", f"{oil['var_pct']}% {'flagged' if oil['flag'] else 'ok'}",
         oil["var_pct"] == Decimal("5.00") and oil["flag"]),
        ("Retailer A taxable", "7,500.00", money(res["invoice_a"]["taxable_paise"]), res["invoice_a"]["taxable_paise"] == 750000),
        ("Retailer A CGST / SGST", "187.50 / 187.50", f"{money(res['invoice_a']['cgst_paise'])} / {money(res['invoice_a']['sgst_paise'])}",
         res["invoice_a"]["cgst_paise"] == 18750 == res["invoice_a"]["sgst_paise"]),
        ("Retailer A invoice total", "7,875.00", money(res["invoice_a"]["total_paise"]), res["invoice_a"]["total_paise"] == 787500),
        ("Retailer A outstanding", "3,875.00", money(res["outstanding_a"]), res["outstanding_a"] == 387500),
        ("Distributor B shortage", "32 packets", f"{qty(res['order_b_check']['shortage'])} packets", res["order_b_check"]["shortage"] == to_milli(32)),
        ("Distributor B tax type", "IGST 300.00", f"IGST {money(res['invoice_b']['igst_paise'])} (CGST {money(res['invoice_b']['cgst_paise'])})",
         res["invoice_b"]["igst_paise"] == 30000 and res["invoice_b"]["cgst_paise"] == 0),
        ("Distributor B dispatch blocked", "blocked", "blocked" if res["dispatch_b_blocked"] else "NOT blocked", bool(res["dispatch_b_blocked"])),
    ]
    return checks


def main():
    import datetime as dt
    db = connect(":memory:")
    seed_mod.seed(db)
    res = run(db, dt.date.today().isoformat())
    ok = True
    print(f"{'Check':36}{'Expected':20}{'Actual':28}Result")
    for name, exp, act, passed in check(res):
        ok &= passed
        print(f"{name:36}{exp:20}{act:28}{'PASS' if passed else 'FAIL'}")
    s = res["summary"]
    print(f"\nCost per packet: Rs {money(s['cost_per_packet_paise'])} "
          f"(materials {money(s['material_paise'])} + overheads {money(s['direct_overhead_paise'])} = {money(s['total_cost_paise'])} / 188 packets); "
          f"margin Rs {money(s['margin_per_packet_paise'])} ({s['margin_pct']}%)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
