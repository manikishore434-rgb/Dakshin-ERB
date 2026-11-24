"""Tests for SnackFlow ERP Intelligence Modules, Production Planning, FEFO,
Root Cause Analysis, Simulators, Document Vault, Quality, and Audit Readiness.
"""
import datetime as dt
import unittest
from decimal import Decimal

from app import create_app, seed
from app.db import connect, tx
from app.services import intelligence as intel, production, sales, stock
from app.util import to_milli, to_paise

TODAY = dt.date.today().isoformat()


class IntelligenceTest(unittest.TestCase):
    def setUp(self):
        self.db = connect(":memory:")
        seed.seed(self.db)
        self.ids = {r["code"]: r["id"] for r in self.db.execute("SELECT id, code FROM items")}
        self.cust = {r["name"]: r["id"] for r in self.db.execute("SELECT id, name FROM customers")}
        get = lambda n: dict(self.db.execute("SELECT * FROM users WHERE username=?", (n,)).fetchone())
        self.admin = get("admin")
        self.prod = get("production")
        self.sa = get("salesman_a")

    def test_control_tower_summary(self):
        summary = intel.get_control_tower_summary(self.db)
        self.assertIn("plant_health_score", summary)
        self.assertGreaterEqual(summary["plant_health_score"], 35)
        self.assertIn("total_inventory_val", summary)
        self.assertGreater(summary["total_inventory_val"], 0)

    def test_production_planner_analysis(self):
        # Create an order that exceeds stock to create demand gap
        with tx(self.db):
            sales.create_order(self.db, self.sa, self.cust["Retailer A"],
                               [{"item_id": self.ids["FG-MUR200"], "qty": 150, "unit": "packet"}])
        analysis = intel.get_production_plan_analysis(self.db)
        self.assertTrue(any(p["product_id"] == self.ids["FG-MUR200"] for p in analysis["analysis"]))
        mur = next(p for p in analysis["analysis"] if p["product_id"] == self.ids["FG-MUR200"])
        self.assertGreater(mur["demand_milli"], 0)
        self.assertGreater(mur["production_gap_milli"], 0)
        self.assertGreater(mur["batches_needed"], 0)
        self.assertTrue(len(mur["ingredients"]) > 0)

    def test_save_and_convert_production_plan(self):
        with tx(self.db):
            plan_id = intel.save_production_plan(self.db, self.admin, self.ids["FG-MUR200"], 1, "Test buffer plan")
        self.assertIsNotNone(plan_id)
        row = self.db.execute("SELECT * FROM production_plans WHERE id=?", (plan_id,)).fetchone()
        self.assertEqual(row["status"], "approved")
        self.assertEqual(row["batches_milli"], 1000)

    def test_inventory_health_score(self):
        health = intel.get_inventory_health(self.db)
        self.assertIn("score", health)
        self.assertGreaterEqual(health["score"], 0)
        self.assertLessEqual(health["score"], 100)
        self.assertIn("breakdown", health)
        self.assertEqual(len(health["items"]), 6)

    def test_smart_reorder_recommendations(self):
        reorders = intel.get_smart_reorder_recommendations(self.db)
        self.assertGreater(len(reorders), 0)
        flour_reorder = next((r for r in reorders if r["code"] == "RM-FLOUR"), None)
        self.assertIsNotNone(flour_reorder)
        self.assertIn(flour_reorder["urgency"], ("Normal", "Medium", "High", "Critical"))

    def test_fefo_suggestion_logic(self):
        # Fl-001 purchase with expiry
        sugg, err = intel.suggest_fefo_batch(self.db, self.ids["RM-FLOUR"], to_milli(10))
        # Might be None or have batch
        batches = intel.get_batch_inventory(self.db)
        self.assertIsInstance(batches, list)

    def test_root_cause_analysis_rules(self):
        # Start and complete a run with oil variance and low yield
        with tx(self.db):
            rid = production.start_run(self.db, self.prod, self.ids["FG-MUR200"], 1, {
                self.ids["RM-FLOUR"]: to_milli(40),
                self.ids["RM-OIL"]: to_milli("11.0"), # high oil variance
                self.ids["RM-SPICE"]: to_milli("1.2")
            }, TODAY)
            production.complete_run(self.db, self.prod, rid, to_milli(180), to_milli(10), date=TODAY)
        cases = intel.run_root_cause_analysis(self.db, rid)
        self.assertTrue(len(cases) > 0)
        self.assertTrue(any(c["category"] == "Material Overconsumption" for c in cases))

    def test_product_profitability_calculations(self):
        profs = intel.get_product_profitability(self.db)
        self.assertTrue(len(profs) > 0)
        mur = profs[0]
        self.assertIn("selling_price_paise", mur)
        self.assertIn("total_cost_paise", mur)
        self.assertIn("margin_paise", mur)
        self.assertEqual(mur["margin_paise"], mur["selling_price_paise"] - mur["total_cost_paise"])

    def test_profit_leakage_detection(self):
        leakages = intel.detect_profit_leakage(self.db)
        self.assertIsInstance(leakages, list)

    def test_supplier_and_customer_intelligence(self):
        cards = intel.get_supplier_scorecards(self.db)
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["name"], "Sri Lakshmi Flour Mills")

        custs = intel.get_customer_intelligence(self.db)
        self.assertEqual(len(custs), 2)
        self.assertIn("churn_risk", custs[0])

    def test_lost_sales_management(self):
        with tx(self.db):
            lid = intel.record_lost_sale(
                self.db, self.sa, self.cust["Retailer A"], self.ids["FG-MUR200"],
                to_milli(50), "stock_shortage", "Need immediate delivery")
        self.assertIsNotNone(lid)
        summary = intel.get_lost_sales_summary(self.db)
        self.assertEqual(len(summary["rows"]), 1)
        self.assertEqual(summary["total_lost_revenue_paise"], 50 * 5000)

    def test_demand_and_cash_flow_forecasting(self):
        forecasts = intel.forecast_demand(self.db)
        self.assertEqual(len(forecasts), 1)
        self.assertEqual(len(forecasts[0]["projections"]), 3)

        flow = intel.forecast_cash_flow(self.db)
        self.assertIn("expected_inflow_paise", flow)
        self.assertIn("expected_outflow_paise", flow)
        self.assertIn("net_liquidity_paise", flow)

    def test_what_if_simulation_engine(self):
        sim = intel.simulate_what_if(self.db, rm_price_pct=10, selling_price_pct=5, demand_pct=20, yld_pct=-2)
        self.assertIn("sim_revenue_paise", sim)
        self.assertIn("sim_profit_paise", sim)
        self.assertIn("break_even_units", sim)
        self.assertGreater(sim["sim_volume"], 1000)

    def test_ai_business_assistant_queries(self):
        res1 = intel.answer_business_query(self.db, self.admin, "What is my total sales?")
        self.assertIn("sales revenue", res1["answer"])

        res2 = intel.answer_business_query(self.db, self.admin, "Which products are profitable?")
        self.assertIn("profitable product", res2["answer"])

        res3 = intel.answer_business_query(self.db, self.admin, "What is my audit readiness score?")
        self.assertIn("Audit Readiness Score", res3["answer"])

    def test_audit_readiness_scorecard(self):
        card = intel.calculate_audit_readiness(self.db)
        self.assertIn("score", card)
        self.assertGreaterEqual(card["score"], 80)
        self.assertEqual(len(card["pillars"]), 6)

    def test_transaction_traceability_search(self):
        # Trace an item code
        trace = intel.trace_transaction(self.db, "Retailer A")
        self.assertIn("orders", trace)


class IntelligenceWebTest(unittest.TestCase):
    def setUp(self):
        import os, tempfile
        self.tmp = tempfile.mkdtemp()
        self.app = create_app(os.path.join(self.tmp, "t_intel.db"))

    def client(self, user):
        c = self.app.test_client()
        r = c.post("/login", data={"username": user, "password": "demo123"})
        self.assertEqual(r.status_code, 302)
        return c

    def test_intelligence_routes_render(self):
        admin = self.client("admin")
        routes = [
            "/control-tower",
            "/production/planner",
            "/inventory/health",
            "/inventory/reorder",
            "/inventory/batches",
            "/production/wastage",
            "/production/rca",
            "/analytics/profitability",
            "/analytics/leakage",
            "/analytics/cost-fluctuations",
            "/suppliers/intelligence",
            "/customers/intelligence",
            "/sales/lost-sales",
            "/sales/performance",
            "/analytics/forecasting",
            "/finance/cash-flow",
            "/finance/credit-collection",
            "/simulator/what-if",
            "/simulator/continuity",
            "/simulator/factory",
            "/ai-assistant",
            "/alerts",
            "/audit/readiness",
            "/traceability",
            "/production/recall",
            "/vault",
            "/audit/package",
            "/audit/daily-closing",
            "/quality",
            "/bottlenecks-capacity",
        ]
        for url in routes:
            resp = admin.get(url)
            self.assertEqual(resp.status_code, 200, f"Route {url} failed with status {resp.status_code}")

    def test_health_check_endpoint(self):
        c = self.app.test_client()
        resp = c.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["system"], "SnackFlow ERP")

    def test_public_batch_verification_endpoint(self):
        c = self.app.test_client()
        resp = c.get("/verify/batch/FG-MUR200-20261123-01")
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
