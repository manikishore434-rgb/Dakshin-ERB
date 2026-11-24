"""Business Decision Support Engine.

Rule-based decision support calculating clear, actionable recommendations
directly from production, inventory, sales, and financial records.
All recommendations are grounded in database evidence and transparent business logic.
"""
from ..util import money, qty, today
from . import mrp, production, sales, stock


def generate_recommendations(db):
    """Calculates prioritized business decisions with evidence, suggested actions, and impacts."""
    recs = []
    d_today = today()

    # Rule 1: Material Shortages & MRP Purchase Recommendations
    mrp_data = mrp.run_mrp(db)
    for shortage in mrp_data["shortages"]:
        item = shortage["item"]
        recs.append({
            "id": f"rec-mrp-{item['id']}",
            "title": f"Procure {item['name']} immediately",
            "category": "Procurement",
            "priority": "critical",
            "problem": f"Raw material deficit of {qty(shortage['net_deficit_milli'])} {item['base_unit']} threatens production continuity.",
            "evidence": (
                f"Current stock is {qty(shortage['on_hand_milli'])} {item['base_unit']}. "
                f"Open approved order demand requires {qty(shortage['gross_req_milli'])} {item['base_unit']} "
                f"with safety threshold of {qty(shortage['safety_stock_milli'])} {item['base_unit']}."
            ),
            "suggested_action": f"Issue Purchase Order to {shortage['supplier_name']} for {qty(shortage['suggested_buy_milli'])} {item['base_unit']}.",
            "impact": f"Prevents production halt; estimated purchase outlay Rs {money(shortage['est_cost_paise'])}.",
            "action_url": "/mrp",
            "action_label": "Generate PO in MRP",
        })

    # Rule 2: Backlogged Finished Goods & Production Batch Scheduling
    for ps in mrp_data["production_suggestions"]:
        if ps["batches_needed"] > 0:
            recs.append({
                "id": f"rec-prod-{ps['product']['id']}",
                "title": f"Schedule Production: {ps['product']['name']}",
                "category": "Manufacturing",
                "priority": "high",
                "problem": f"Finished stock deficit of {qty(ps['net_deficit_milli'])} packets blocks customer dispatches.",
                "evidence": (
                    f"Customer demand stands at {qty(ps['demanded_milli'])} packets against on-hand finished stock of "
                    f"{qty(ps['on_hand_milli'])} packets."
                ),
                "suggested_action": f"Schedule and start {ps['batches_needed']} batch(es) of {ps['product']['name']} immediately.",
                "impact": f"Fulfills backlogged orders and unlocks Rs {money(ps['demanded_milli'] * (ps['product']['price_paise'] or 0) // 1000)} in sales revenue.",
                "action_url": f"/prod/runs/new?product_id={ps['product']['id']}&batches={ps['batches_needed']}",
                "action_label": "Start Production Run",
            })

    # Rule 3: Investigate Yield and Material Wastage Variances
    runs = db.execute(
        "SELECT id, run_no, date, product_id FROM production_runs WHERE status='completed' ORDER BY id DESC LIMIT 5"
    ).fetchall()
    for r in runs:
        s = production.run_summary(db, r["id"])
        if s["yield_flag"]:
            recs.append({
                "id": f"rec-yield-{r['id']}",
                "title": f"Investigate Yield Loss: {r['run_no']}",
                "category": "Operations",
                "priority": "high",
                "problem": f"Batch output fell short of BOM expectation by {s['yield_var_pct']}%.",
                "evidence": f"Expected {qty(s['run']['expected_milli'])} packets, but actual good output was {qty(s['run']['actual_milli'])} packets ({qty(s['run']['damaged_milli'])} damaged).",
                "suggested_action": "Audit extrusion temperature, frying time, and operator pouch sealing tolerances.",
                "impact": f"Yield loss increased packet unit cost to Rs {money(s['cost_per_packet_paise'])}, compressing profit margin to {s['margin_pct']}%.",
                "action_url": f"/prod/runs/{r['id']}",
                "action_label": "View Run Details",
            })

    # Rule 4: Overdue Receivables & Cash Flow Recovery
    recs_finance, _ = sales.receivables(db, d_today)
    for rf in recs_finance:
        if rf["outstanding"] > 0 and rf["age_days"] > 14:
            prio = "critical" if rf["age_days"] > 45 else "medium"
            recs.append({
                "id": f"rec-cash-{rf['invoice']['id']}",
                "title": f"Follow up on Payment: {rf['invoice']['customer']}",
                "category": "Finance",
                "priority": prio,
                "problem": f"Outstanding payment of Rs {money(rf['outstanding'])} is pending for {rf['age_days']} days.",
                "evidence": f"Invoice {rf['invoice']['invoice_no']} dated {rf['invoice']['date']} has uncollected balance of Rs {money(rf['outstanding'])}.",
                "suggested_action": f"Contact accounts payable at {rf['invoice']['customer']} and place subsequent orders on hold until resolved.",
                "impact": f"Recovers Rs {money(rf['outstanding'])} working capital and reduces bad debt risk.",
                "action_url": "/admin/payments",
                "action_label": "Record Payment",
            })

    # Sort by priority
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return sorted(recs, key=lambda x: rank.get(x["priority"], 4))
