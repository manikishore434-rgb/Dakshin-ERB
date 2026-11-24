"""Owner Executive Suite & Business Health Dashboard."""
from flask import Blueprint, render_template

from ..db import get_db
from ..services import alerts, decisions, procurement, production, profitability, quality, sales, stock
from ..util import today
from .auth import login_required

bp = Blueprint("owner", __name__)
ROLES = ("owner", "admin")


@bp.route("/owner/suite")
@login_required(*ROLES)
def suite():
    db = get_db()
    d_today = today()

    # 1. Financial Highlights
    products_profit = profitability.calculate_product_profitability(db)
    tot_revenue = sum(p["net_revenue_paise"] for p in products_profit)
    tot_cogs = sum(p["cogs_paise"] for p in products_profit)
    gross_profit = tot_revenue - tot_cogs
    margin_pct = round((gross_profit * 100 / tot_revenue), 1) if tot_revenue > 0 else 0.0

    recs, _ = sales.receivables(db, d_today)
    tot_receivables = sum(r["outstanding"] for r in recs if r["outstanding"] > 0)

    payables = procurement.supplier_payables(db, d_today)
    tot_payables = sum(p["outstanding_paise"] for p in payables)

    stock_ana = stock.stock_analytics(db, d_today)
    tot_inventory_val = stock_ana["total_valuation_paise"]

    # 2. Operational Metrics
    total_orders = db.execute("SELECT COUNT(*) n FROM orders").fetchone()["n"]
    dispatched_orders = db.execute("SELECT COUNT(*) n FROM orders WHERE status='dispatched'").fetchone()["n"]
    pending_orders = db.execute("SELECT COUNT(*) n FROM orders WHERE status IN ('submitted', 'approved', 'invoiced')").fetchone()["n"]

    runs = db.execute("SELECT id FROM production_runs WHERE status='completed'").fetchall()
    tot_expected = 0
    tot_actual = 0
    for r in runs:
        s = production.run_summary(db, r["id"])
        tot_expected += s["run"]["expected_milli"]
        tot_actual += s["run"]["actual_milli"]
    yield_efficiency = round((tot_actual * 100 / tot_expected), 1) if tot_expected > 0 else 100.0

    qc_summary = quality.quality_summary(db)
    active_alerts = alerts.get_active_alerts(db)
    recs_decisions = decisions.generate_recommendations(db)

    # 3. Business Health Score (0 - 100)
    # Pillar A: Production Yield Efficiency (25 pts)
    score_yield = min(25, int(yield_efficiency * 0.25))

    # Pillar B: Order Fulfilment (25 pts)
    fulfill_rate = (dispatched_orders / total_orders * 100) if total_orders > 0 else 100.0
    score_orders = min(25, int(fulfill_rate * 0.25))

    # Pillar C: Quality Pass Rate (25 pts)
    score_quality = min(25, int(qc_summary["pass_rate_pct"] * 0.25))

    # Pillar D: Liquidity & Receivables Health (25 pts)
    # Deduct 5 points per overdue invoice > 30 days
    overdue_count = sum(1 for r in recs if r["outstanding"] > 0 and r["age_days"] > 30)
    score_liquidity = max(0, 25 - (overdue_count * 5))

    health_score = score_yield + score_orders + score_quality + score_liquidity

    health_rating = "Excellent" if health_score >= 85 else "Good" if health_score >= 70 else "Needs Attention" if health_score >= 50 else "Critical"

    return render_template(
        "owner/suite.html",
        health_score=health_score,
        health_rating=health_rating,
        score_yield=score_yield,
        score_orders=score_orders,
        score_quality=score_quality,
        score_liquidity=score_liquidity,
        total_revenue_paise=tot_revenue,
        gross_profit_paise=gross_profit,
        margin_pct=margin_pct,
        total_receivables_paise=tot_receivables,
        total_payables_paise=tot_payables,
        total_inventory_val_paise=tot_inventory_val,
        yield_efficiency=yield_efficiency,
        fulfill_rate=round(fulfill_rate, 1),
        qc_summary=qc_summary,
        alerts=active_alerts[:5],
        recommendations=recs_decisions[:4],
        stock_ana=stock_ana,
    )
