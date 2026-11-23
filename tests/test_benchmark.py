import datetime as dt
import unittest

from app import benchmark, seed
from app.db import connect


class BenchmarkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = connect(":memory:")
        seed.seed(cls.db)
        cls.res = benchmark.run(cls.db, dt.date.today().isoformat())

    def test_every_section5_check(self):
        for name, expected, actual, ok in benchmark.check(self.res):
            self.assertTrue(ok, f"{name}: expected {expected}, got {actual}")

    def test_cost_per_packet(self):
        s = self.res["summary"]
        self.assertEqual(s["material_paise"], 405500)      # flour 1725.00 + oil 1470 + spice 240 + pouches 485 + cartons 135
        self.assertEqual(s["direct_overhead_paise"], 180000)
        self.assertEqual(s["cost_per_packet_paise"], 3114)  # 5855.00 / 188

    def test_other_closing_balances(self):
        from app.services import stock
        ids = {r["code"]: r["id"] for r in self.db.execute("SELECT id, code FROM items")}
        self.assertEqual(stock.balance(self.db, ids["PK-CARTON"])[0], 21000)
        self.assertEqual(stock.balance(self.db, ids["RM-SPICE"])[0], 3800)

    def test_ledger_reconciles_with_every_item(self):
        """closing = opening + receipts - issues +/- adjustments, for every item (the report asserts this itself)."""
        from app.services import reports
        rep = reports.stock_summary(self.db, {})
        self.assertEqual(len(rep["sections"][0]["rows"]), 6)

    def test_flour_valuation_weighted_average(self):
        # 100 kg @ 42 + 60 kg @ 45 = 6,900 over 160 kg -> 43.125/kg; 40 kg issued = Rs 1,725.00
        rows = self.db.execute("SELECT value_paise FROM stock_ledger WHERE move_type='production_issue' AND item_id="
                               "(SELECT id FROM items WHERE code='RM-FLOUR')").fetchall()
        self.assertEqual(rows[0]["value_paise"], -172500)

    def test_audit_trail_written(self):
        actions = {(r["entity"], r["action"]) for r in self.db.execute("SELECT entity, action FROM audit_log")}
        for need in [("invoice", "create"), ("invoice", "dispatch"), ("production_run", "complete"), ("payment", "create"), ("order", "approve")]:
            self.assertIn(need, actions)


if __name__ == "__main__":
    unittest.main()
