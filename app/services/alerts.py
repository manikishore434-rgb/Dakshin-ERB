"""Smart Alerts and Exception Management Engine.

Scans the database in real-time and identifies critical operational exceptions:
stock shortages, expiring lots, pending approvals, production variances, and overdue payments.
"""
import datetime as dt

from ..util import money, qty, today
from . import procurement, production, sales, stock

NOW = lambda: dt.datetime.now().isoformat(timespec="seconds")


def get_active_alerts(db):
    """Scans live database data and returns a consolidated list of active alerts with severities."""
    alerts = []
    d_today = today()

    # 1. Low stock / Reorder Point breaches
    items = db.execute("SELECT * FROM items WHERE active=1 ORDER BY kind DESC, name").fetchall()
    for item in items:
        on_hand, _ = stock.balance(db, item["id"])
        rop = item["reorder_level_milli"] or 0
        safety = item["safety_stock_milli"] or 0

        if rop > 0 and on_hand <= rop:
            sev = "critical" if (safety > 0 and on_hand <= safety) else "high"
            alerts.append({
                "id": f"stock-{item['id']}",
                "category": "Inventory",
                "severity": sev,
                "title": f"Low Stock: {item['name']}",
                "message": f"On-hand quantity {qty(on_hand)} {item['base_unit']} is below reorder point of {qty(rop)} {item['base_unit']}.",
                "entity_type": "item",
                "entity_id": item["id"],
                "action_url": f"/mrp?item={item['id']}",
                "action_label": "Run MRP & Order",
            })

    # 2. Material shortages blocking open sales orders
    pending_orders = db.execute(
        "SELECT id, order_no, customer_id FROM orders WHERE status='submitted' ORDER BY id"
    ).fetchall()
    for o in pending_orders:
        checks = sales.stock_check(db, o["id"])
        short = [c for c in checks if c["shortage"] > 0]
        if short:
            short_desc = ", ".join(f"{c['name']} (short by {qty(c['shortage'])})" for c in short)
            alerts.append({
                "id": f"order-short-{o['id']}",
                "category": "Orders",
                "severity": "critical",
                "title": f"Order {o['order_no']} Blocked by Shortage",
                "message": f"Approval blocked due to insufficient stock: {short_desc}.",
                "entity_type": "order",
                "entity_id": o["id"],
                "action_url": f"/admin/orders/{o['id']}",
                "action_label": "View Order",
            })

    # 3. Quality Rejections or Quarantine holds
    q_issues = db.execute(
        """SELECT qi.*, i.name item_name
           FROM quality_inspections qi
           JOIN items i ON i.id=qi.item_id
           WHERE qi.status IN ('rejected', 'quarantine')
           ORDER BY qi.id DESC LIMIT 10"""
    ).fetchall()
    for qi in q_issues:
        alerts.append({
            "id": f"qc-{qi['id']}",
            "category": "Quality",
            "severity": "critical",
            "title": f"Quality {qi['status'].upper()}: {qi['item_name']}",
            "message": f"Batch {qi['batch_no'] or ''} flagged as {qi['status']}. Defect: {qi['defect_category'] or 'Non-conformance'}.",
            "entity_type": "quality_inspection",
            "entity_id": qi["id"],
            "action_url": f"/quality/inspections/{qi['id']}",
            "action_label": "Review QA Report",
        })

    # 4. Production variances (> tolerance)
    runs = db.execute(
        "SELECT id, run_no, date, product_id FROM production_runs WHERE status='completed' ORDER BY id DESC LIMIT 10"
    ).fetchall()
    for r in runs:
        s = production.run_summary(db, r["id"])
        if s["any_flag"]:
            flag_msgs = []
            if s["yield_flag"]:
                flag_msgs.append(f"Yield variance {s['yield_var_pct']}%")
            for l in s["lines"]:
                if l["flag"]:
                    flag_msgs.append(f"{l['name']} consumption variance {l['var_pct']}%")
            alerts.append({
                "id": f"run-var-{r['id']}",
                "category": "Production",
                "severity": "high",
                "title": f"Production Variance: {r['run_no']}",
                "message": f"{'; '.join(flag_msgs)} beyond tolerance.",
                "entity_type": "production_run",
                "entity_id": r["id"],
                "action_url": f"/prod/runs/{r['id']}",
                "action_label": "Investigate Run",
            })

    # 5. Overdue receivables
    recs, _ = sales.receivables(db, d_today)
    for r in recs:
        if r["outstanding"] > 0 and r["age_days"] > 30:
            sev = "critical" if r["age_days"] > 60 else "high"
            alerts.append({
                "id": f"rec-{r['invoice']['id']}",
                "category": "Finance",
                "severity": sev,
                "title": f"Overdue Receivable: {r['invoice']['customer']}",
                "message": f"Invoice {r['invoice']['invoice_no']} of Rs {money(r['outstanding'])} is overdue by {r['age_days']} days.",
                "entity_type": "invoice",
                "entity_id": r["invoice"]["id"],
                "action_url": "/admin/payments",
                "action_label": "Collect Payment",
            })

    # 6. Orders waiting for dispatch
    undispatched = db.execute(
        """SELECT i.id, i.invoice_no, i.date, c.name customer
           FROM invoices i
           JOIN customers c ON c.id=i.customer_id
           WHERE i.status='posted' AND i.dispatched_on IS NULL
           ORDER BY i.date"""
    ).fetchall()
    for inv in undispatched:
        alerts.append({
            "id": f"disp-{inv['id']}",
            "category": "Dispatch",
            "severity": "medium",
            "title": f"Awaiting Dispatch: {inv['invoice_no']}",
            "message": f"Invoiced to {inv['customer']} on {inv['date']}. Ready for shipment.",
            "entity_type": "invoice",
            "entity_id": inv["id"],
            "action_url": f"/admin/orders",
            "action_label": "Dispatch",
        })

    # Priority sorting: critical > high > medium > low
    sev_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return sorted(alerts, key=lambda a: sev_rank.get(a["severity"], 4))


def alert_counts(db):
    alerts = get_active_alerts(db)
    counts = {"total": len(alerts), "critical": 0, "high": 0, "medium": 0, "low": 0}
    for a in alerts:
        counts[a["severity"]] = counts.get(a["severity"], 0) + 1
    return counts
