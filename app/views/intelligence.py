"""Enterprise Intelligence, Planning, Simulators, Control Tower & Quality routes."""
import datetime as dt
import io
import json
import os
import zipfile
from decimal import Decimal
from flask import (Blueprint, Response, current_app, flash, g, jsonify,
                   redirect, render_template, request, send_file, url_for)
from werkzeug.utils import secure_filename

from ..db import get_db, next_seq, tx
from ..services import intelligence as intel, production, reports, sales, stock
from ..util import D, ServiceError, money, qty as fmt_qty, round_half_up, to_milli, to_paise, today
from .auth import login_required

bp = Blueprint("intelligence", __name__)
ADMIN_PROD = ("admin", "production", "owner")
ADMIN_ACCT = ("admin", "accountant", "owner")
ALL_STAFF = ("admin", "production", "salesman", "accountant", "owner")
MGMT = ("admin", "owner")


# ---------------------------------------------------------------- Control Tower
@bp.route("/control-tower")
@login_required(*ALL_STAFF)
def control_tower():
    db = get_db()
    summary = intel.get_control_tower_summary(db)
    return render_template("control_tower/index.html", s=summary)


# ---------------------------------------------------------------- Smart Production Planner
@bp.route("/production/planner")
@login_required(*ADMIN_PROD)
def production_planner():
    db = get_db()
    pid = request.args.get("product_id", type=int)
    plan_data = intel.get_production_plan_analysis(db, pid)
    products = db.execute("SELECT id, name FROM items WHERE kind='finished' AND active=1").fetchall()
    return render_template("intelligence/planner.html", data=plan_data, products=products, selected_pid=pid)


@bp.route("/production/planner/save", methods=["POST"])
@login_required(*ADMIN_PROD)
def save_plan():
    db = get_db()
    f = request.form
    try:
        pid = int(f["product_id"])
        batches = f.get("batches", 1)
        notes = f.get("notes", "")
        order_id = int(f.get("order_id") or 0) or None
        with tx(db):
            plan_id = intel.save_production_plan(db, g.user, pid, batches, notes, order_id)
        flash("Production Plan generated and saved", "ok")
    except Exception as e:
        flash(f"Error creating plan: {e}", "error")
    return redirect(url_for("intelligence.production_planner"))


@bp.route("/production/planner/<int:plan_id>/convert", methods=["POST"])
@login_required(*ADMIN_PROD)
def convert_plan(plan_id):
    """Converts an approved production plan directly into a production run."""
    db = get_db()
    plan = db.execute("SELECT * FROM production_plans WHERE id=?", (plan_id,)).fetchone()
    if not plan:
        flash("Plan not found", "error")
        return redirect(url_for("intelligence.production_planner"))
    try:
        # Calculate issues according to BOM
        bom, lines = production.get_bom(db, plan["product_id"])
        batches = D(plan["batches_milli"]) / 1000
        issues = {}
        for bl in lines:
            if bl["kind"] == "raw":
                needed = round_half_up(D(bl["qty_milli"]) * batches)
                bal, _ = stock.balance(db, bl["item_id"])
                if bal < needed:
                    raise ServiceError(f"Insufficient stock for {bl['name']}: need {fmt_qty(needed)}, available {fmt_qty(bal)}")
                issues[bl["item_id"]] = needed

        with tx(db):
            rid = production.start_run(db, g.user, plan["product_id"], batches, issues, today(), f"Created from Plan {plan['plan_no']}")
            db.execute("UPDATE production_plans SET status='converted' WHERE id=?", (plan_id,))
        flash(f"Run started successfully from Plan {plan['plan_no']}", "ok")
        return redirect(url_for("production.run_detail", rid=rid))
    except Exception as e:
        flash(f"Could not convert plan to run: {e}", "error")
        return redirect(url_for("intelligence.production_planner"))


# ---------------------------------------------------------------- Inventory Health & Reorder Predictor
@bp.route("/inventory/health")
@login_required(*ADMIN_PROD)
def inventory_health():
    db = get_db()
    health = intel.get_inventory_health(db)
    return render_template("intelligence/inventory_health.html", h=health)


@bp.route("/inventory/reorder")
@login_required(*ADMIN_PROD)
def reorder_predictor():
    db = get_db()
    reorders = intel.get_smart_reorder_recommendations(db)
    return render_template("intelligence/reorder_predictor.html", reorders=reorders)


# ---------------------------------------------------------------- Advanced Batch & Expiry (FEFO)
@bp.route("/inventory/batches")
@login_required(*ADMIN_PROD)
def batch_management():
    db = get_db()
    batches = intel.get_batch_inventory(db)
    return render_template("intelligence/batches.html", batches=batches)


@bp.route("/api/fefo-suggest")
@login_required(*ADMIN_PROD)
def api_fefo_suggest():
    db = get_db()
    item_id = request.args.get("item_id", type=int)
    qty = to_milli(request.args.get("qty", 1))
    sugg, err = intel.suggest_fefo_batch(db, item_id, qty)
    if err:
        return jsonify(ok=False, error=err), 400
    return jsonify(ok=True, suggestion=sugg)


# ---------------------------------------------------------------- Material Wastage & Root Cause Analysis
@bp.route("/production/wastage")
@login_required(*ADMIN_PROD)
def material_wastage():
    db = get_db()
    data = intel.get_wastage_analytics(db)
    return render_template("intelligence/wastage.html", data=data)


@bp.route("/production/rca")
@login_required(*ADMIN_PROD)
def root_cause_analysis():
    db = get_db()
    rid = request.args.get("run_id", type=int)
    cases = intel.run_root_cause_analysis(db, rid)
    runs = db.execute("SELECT id, run_no, batch_no FROM production_runs WHERE status='completed' ORDER BY id DESC LIMIT 20").fetchall()
    return render_template("intelligence/rca.html", cases=cases, runs=runs, selected_rid=rid)


# ---------------------------------------------------------------- Profitability & Profit Leakage
@bp.route("/analytics/profitability")
@login_required(*ADMIN_ACCT)
def profitability():
    db = get_db()
    profs = intel.get_product_profitability(db)
    return render_template("intelligence/profitability.html", profs=profs)


@bp.route("/analytics/leakage")
@login_required(*ADMIN_ACCT)
def profit_leakage():
    db = get_db()
    leakages = intel.detect_profit_leakage(db)
    tot_impact = sum(l["impact_paise"] for l in leakages)
    return render_template("intelligence/profit_leakage.html", leakages=leakages, tot_impact=tot_impact)


@bp.route("/analytics/cost-fluctuations")
@login_required(*ADMIN_ACCT)
def cost_fluctuations():
    db = get_db()
    rows = db.execute(
        "SELECT pl.item_id, i.name item_name, i.base_unit, pl.rate, p.date, s.name supplier_name "
        "FROM purchase_lines pl "
        "JOIN purchases p ON p.id=pl.purchase_id "
        "LEFT JOIN suppliers s ON s.id=p.supplier_id "
        "JOIN items i ON i.id=pl.item_id "
        "ORDER BY pl.item_id, p.date DESC").fetchall()
    return render_template("intelligence/cost_fluctuations.html", rows=rows)


# ---------------------------------------------------------------- Supplier & Customer Intelligence
@bp.route("/suppliers/intelligence")
@login_required(*ADMIN_PROD)
def supplier_intelligence():
    db = get_db()
    cards = intel.get_supplier_scorecards(db)
    return render_template("intelligence/supplier_intelligence.html", cards=cards)


@bp.route("/customers/intelligence")
@login_required(*ADMIN_ACCT)
def customer_intelligence():
    db = get_db()
    custs = intel.get_customer_intelligence(db)
    return render_template("intelligence/customer_intelligence.html", custs=custs)


# ---------------------------------------------------------------- Lost Sales & Performance
@bp.route("/sales/lost-sales", methods=["GET", "POST"])
@login_required(*ALL_STAFF)
def lost_sales():
    db = get_db()
    if request.method == "POST":
        f = request.form
        try:
            with tx(db):
                intel.record_lost_sale(
                    db, g.user, int(f["customer_id"]), int(f["item_id"]),
                    to_milli(f["qty"]), f["reason"], f.get("notes", ""))
            flash("Lost sale record submitted for intelligence review", "ok")
        except Exception as e:
            flash(f"Error: {e}", "error")
        return redirect(url_for("intelligence.lost_sales"))

    summary = intel.get_lost_sales_summary(db)
    customers = db.execute("SELECT id, name FROM customers ORDER BY name").fetchall()
    products = db.execute("SELECT id, name FROM items WHERE kind='finished' AND active=1 ORDER BY name").fetchall()
    return render_template("intelligence/lost_sales.html", summary=summary, customers=customers, products=products)


@bp.route("/sales/performance")
@login_required(*ALL_STAFF)
def sales_performance():
    db = get_db()
    salesmen = db.execute("SELECT * FROM users WHERE role='salesman'").fetchall()
    ranks = []
    for sm in salesmen:
        res = db.execute(
            "SELECT COUNT(DISTINCT o.id) orders_cnt, "
            "COALESCE(SUM(ol.qty_milli * ol.price_paise / 1000), 0) total_paise "
            "FROM orders o "
            "JOIN order_lines ol ON ol.order_id=o.id "
            "WHERE o.salesman_id=? AND o.status NOT IN ('rejected','cancelled')", (sm["id"],)).fetchone()
        target_paise = to_paise(100000) # Rs 1 Lakh target
        achieved_paise = res["total_paise"]
        ach_pct = (D(achieved_paise) * 100 / D(target_paise)).quantize(Decimal("0.1")) if target_paise else Decimal(0)
        ranks.append({
            "name": sm["full_name"],
            "orders": res["orders_cnt"],
            "achieved_paise": achieved_paise,
            "target_paise": target_paise,
            "ach_pct": ach_pct,
        })
    ranks.sort(key=lambda x: -x["achieved_paise"])
    return render_template("intelligence/sales_performance.html", ranks=ranks)


# ---------------------------------------------------------------- Demand & Cash Flow Forecasting
@bp.route("/analytics/forecasting")
@login_required(*ADMIN_ACCT)
def demand_forecasting():
    db = get_db()
    forecasts = intel.forecast_demand(db)
    return render_template("intelligence/demand_forecasting.html", forecasts=forecasts)


@bp.route("/finance/cash-flow")
@login_required(*ADMIN_ACCT)
def cash_flow_forecasting():
    db = get_db()
    days = request.args.get("days", 30, type=int)
    flow = intel.forecast_cash_flow(db, days)
    return render_template("intelligence/cash_flow.html", flow=flow)


@bp.route("/finance/credit-collection")
@login_required(*ADMIN_ACCT)
def credit_collection():
    db = get_db()
    recs, _ = sales.receivables(db)
    customers = db.execute("SELECT * FROM customers ORDER BY name").fetchall()
    cust_dues = []
    for c in customers:
        cust_invs = [r for r in recs if r["invoice"]["customer_id"] == c["id"] and r["outstanding"] > 0]
        total_due = sum(r["outstanding"] for r in cust_invs)
        limit = c["credit_limit_paise"] or 5000000
        exposure_pct = (D(total_due) * 100 / D(limit)).quantize(Decimal("0.1")) if limit else Decimal(0)

        # Ageing buckets
        b0_30 = sum(r["outstanding"] for r in cust_invs if r["age_days"] <= 30)
        b31_60 = sum(r["outstanding"] for r in cust_invs if 31 <= r["age_days"] <= 60)
        b61_90 = sum(r["outstanding"] for r in cust_invs if 61 <= r["age_days"] <= 90)
        b90_plus = sum(r["outstanding"] for r in cust_invs if r["age_days"] > 90)

        cust_dues.append({
            "id": c["id"],
            "name": c["name"],
            "limit_paise": limit,
            "total_due": total_due,
            "exposure_pct": exposure_pct,
            "b0_30": b0_30,
            "b31_60": b31_60,
            "b61_90": b61_90,
            "b90_plus": b90_plus,
            "in_violation": total_due > limit,
        })
    cust_dues.sort(key=lambda x: -x["total_due"])
    return render_template("intelligence/credit_collection.html", cust_dues=cust_dues)


# ---------------------------------------------------------------- Simulators
@bp.route("/simulator/what-if", methods=["GET", "POST"])
@login_required(*ALL_STAFF)
def simulator_what_if():
    db = get_db()
    rm_p = request.values.get("rm_p", 0, type=float)
    sp_p = request.values.get("sp_p", 0, type=float)
    dem_p = request.values.get("dem_p", 0, type=float)
    yld_p = request.values.get("yld_p", 0, type=float)

    sim = intel.simulate_what_if(db, rm_p, sp_p, dem_p, yld_p)
    return render_template("intelligence/simulator_what_if.html",
                           sim=sim, rm_p=rm_p, sp_p=sp_p, dem_p=dem_p, yld_p=yld_p)


@bp.route("/simulator/continuity")
@login_required(*ALL_STAFF)
def simulator_continuity():
    db = get_db()
    items = db.execute("SELECT * FROM items WHERE kind='raw' AND active=1").fetchall()
    continuity_cases = []
    for it in items:
        q, _ = stock.balance(db, it["id"])
        # Daily usage
        res = db.execute(
            "SELECT COALESCE(SUM(-qty_milli), 0) consumed "
            "FROM stock_ledger WHERE item_id=? AND move_type='production_issue'", (it["id"],)).fetchone()
        cons = res["consumed"] / 10 if res["consumed"] > 0 else (it["reorder_level_milli"] / 5 or 5000)
        days_left = int(q / cons) if cons > 0 else 99
        continuity_cases.append({
            "item_name": it["name"],
            "unit": it["base_unit"],
            "stock": q,
            "daily_rate": int(cons),
            "days_until_shutdown": days_left,
            "risk_level": "Critical Risk" if days_left <= 3 else ("Moderate" if days_left <= 7 else "Safe Buffer"),
        })
    return render_template("intelligence/simulator_continuity.html", cases=continuity_cases)


@bp.route("/simulator/factory")
@login_required(*ALL_STAFF)
def simulator_factory():
    """Digital Factory flow simulation."""
    return render_template("intelligence/simulator_factory.html")


# ---------------------------------------------------------------- AI Assistant
@bp.route("/ai-assistant")
@login_required(*ALL_STAFF)
def ai_assistant_view():
    return render_template("intelligence/ai_assistant.html")


@bp.route("/api/ai-assistant/query", methods=["POST"])
@login_required(*ALL_STAFF)
def api_ai_assistant():
    db = get_db()
    d = request.get_json(force=True, silent=True) or {}
    query = d.get("query", "").strip()
    if not query:
        return jsonify(ok=False, error="Query cannot be empty"), 400
    res = intel.answer_business_query(db, g.user, query)
    return jsonify(ok=True, **res)


# ---------------------------------------------------------------- Alert Center
@bp.route("/alerts")
@login_required(*ALL_STAFF)
def alerts_center():
    db = get_db()
    rows = db.execute("SELECT * FROM alerts ORDER BY status ASC, id DESC").fetchall()
    return render_template("intelligence/alerts.html", alerts=rows)


@bp.route("/alerts/<int:aid>/<action>", methods=["POST"])
@login_required(*ALL_STAFF)
def alert_action(aid, action):
    db = get_db()
    with tx(db):
        if action == "ack":
            db.execute("UPDATE alerts SET status='acknowledged' WHERE id=?", (aid,))
        elif action == "resolve":
            db.execute("UPDATE alerts SET status='resolved', resolved_at=? WHERE id=?", (NOW(), aid))
    flash("Alert status updated", "ok")
    return redirect(url_for("intelligence.alerts_center"))


# ---------------------------------------------------------------- Audit Readiness & Traceability
@bp.route("/audit/readiness")
@login_required(*ADMIN_ACCT)
def audit_readiness():
    db = get_db()
    scorecard = intel.calculate_audit_readiness(db)
    return render_template("intelligence/audit_readiness.html", sc=scorecard)


@bp.route("/traceability")
@login_required(*ALL_STAFF)
def traceability():
    db = get_db()
    term = request.args.get("q", "").strip()
    results = intel.trace_transaction(db, term) if term else None
    return render_template("intelligence/traceability.html", term=term, r=results)


# ---------------------------------------------------------------- Smart Recall Management
@bp.route("/production/recall", methods=["GET", "POST"])
@login_required(*ADMIN_PROD)
def recall_management():
    db = get_db()
    if request.method == "POST":
        f = request.form
        batch_no = f["batch_no"].strip()
        reason = f["reason"].strip()
        severity = f["severity"]
        # Find affected customers and quantity from stock_ledger & invoices
        rows = db.execute(
            "SELECT i.id, i.invoice_no, c.name cust_name, c.phone, sl.qty_milli, sl.item_id "
            "FROM stock_ledger sl "
            "JOIN invoices i ON i.id=sl.source_id AND sl.source_type='invoice' "
            "JOIN customers c ON c.id=i.customer_id "
            "WHERE sl.batch_no=?", (batch_no,)).fetchall()

        affected_qty = sum(-r["qty_milli"] for r in rows if r["qty_milli"] < 0)
        item_id = rows[0]["item_id"] if rows else db.execute("SELECT id FROM items WHERE kind='finished' LIMIT 1").fetchone()["id"]

        n = next_seq(db, "RCL")
        rcl_no = f"RCL-{n:04d}"
        with tx(db):
            db.execute(
                "INSERT INTO recalls(recall_no, batch_no, product_id, date, reason, severity, affected_qty_milli, status, created_by, created_at) "
                "VALUES (?,?,?,?,?,?,?,'initiated',?,?)",
                (rcl_no, batch_no, item_id, today(), reason, severity, affected_qty, g.user["id"], NOW()))
        flash(f"Batch Recall Protocol {rcl_no} Initiated for {batch_no}", "ok")
        return redirect(url_for("intelligence.recall_management"))

    recalls = db.execute("SELECT r.*, i.name product_name FROM recalls r JOIN items i ON i.id=r.product_id ORDER BY r.id DESC").fetchall()
    batches = db.execute("SELECT DISTINCT batch_no FROM stock_ledger WHERE batch_no IS NOT NULL ORDER BY batch_no").fetchall()
    return render_template("intelligence/recalls.html", recalls=recalls, batches=batches)


# ---------------------------------------------------------------- Digital Document Vault
@bp.route("/vault", methods=["GET", "POST"])
@login_required(*ALL_STAFF)
def document_vault():
    db = get_db()
    vault_dir = os.path.join(current_app.root_path, "..", "data", "vault")
    os.makedirs(vault_dir, exist_ok=True)

    if request.method == "POST":
        file = request.files.get("file")
        if not file or not file.filename:
            flash("Please choose a file to upload", "error")
            return redirect(url_for("intelligence.document_vault"))

        title = request.form.get("title", file.filename)
        category = request.form.get("category", "other")
        filename = secure_filename(file.filename)
        stored_name = f"{int(dt.datetime.now().timestamp())}_{filename}"
        dest_path = os.path.join(vault_dir, stored_name)
        file.save(dest_path)
        size = os.path.getsize(dest_path)

        with tx(db):
            db.execute(
                "INSERT INTO documents(title, category, filename, stored_filename, mime_type, file_size, uploaded_by, notes, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (title, category, filename, stored_name, file.content_type, size, g.user["id"], request.form.get("notes", ""), NOW()))
        flash("Document securely uploaded to vault", "ok")
        return redirect(url_for("intelligence.document_vault"))

    docs = db.execute("SELECT d.*, u.full_name uploaded_by_name FROM documents d LEFT JOIN users u ON u.id=d.uploaded_by ORDER BY d.id DESC").fetchall()
    return render_template("intelligence/vault.html", docs=docs)


@bp.route("/vault/download/<int:doc_id>")
@login_required(*ALL_STAFF)
def vault_download(doc_id):
    db = get_db()
    d = db.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    if not d:
        flash("Document not found", "error")
        return redirect(url_for("intelligence.document_vault"))
    vault_dir = os.path.join(current_app.root_path, "..", "data", "vault")
    path = os.path.join(vault_dir, d["stored_filename"])
    if not os.path.exists(path):
        flash("File missing from vault storage", "error")
        return redirect(url_for("intelligence.document_vault"))
    return send_file(path, as_attachment=True, download_name=d["filename"])


# ---------------------------------------------------------------- One-Click Audit Package
@bp.route("/audit/package", methods=["GET", "POST"])
@login_required(*ADMIN_ACCT)
def audit_package():
    db = get_db()
    f_date = request.values.get("from", today()[:8] + "01")
    t_date = request.values.get("to", today())

    if request.args.get("download") == "zip":
        # Generate full zip bundle containing all reports as CSVs
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            params = {"from": f_date, "to": t_date}
            for slug, (title, rep_fn, _) in reports.REPORTS.items():
                try:
                    rep_data = rep_fn(db, params)
                    csv_data = reports.to_csv(rep_data)
                    zf.writestr(f"{slug}_{f_date}_to_{t_date}.csv", csv_data)
                except Exception:
                    pass
        buf.seek(0)
        return Response(buf.getvalue(), mimetype="application/zip",
                        headers={"Content-Disposition": f"attachment; filename=SnackFlow-Audit-Package-{f_date}-to-{t_date}.zip"})

    return render_template("intelligence/audit_package.html", f=f_date, t=t_date)


# ---------------------------------------------------------------- Daily Closing
@bp.route("/audit/daily-closing", methods=["GET", "POST"])
@login_required(*ADMIN_ACCT)
def daily_closing():
    db = get_db()
    d = request.values.get("date", today())

    # Compile day's figures
    sales_day = db.execute("SELECT COUNT(*) n, COALESCE(SUM(taxable_paise),0) s, COALESCE(SUM(total_paise),0) tot FROM invoices WHERE date=? AND status='posted'", (d,)).fetchone()
    payments_day = db.execute("SELECT COUNT(*) n, COALESCE(SUM(amount_paise),0) s FROM payments WHERE date=?", (d,)).fetchone()
    purchases_day = db.execute("SELECT COUNT(*) n FROM purchases WHERE date=?", (d,)).fetchone()
    runs_day = db.execute("SELECT COUNT(*) n, COALESCE(SUM(actual_milli),0) fg, COALESCE(SUM(damaged_milli),0) dam FROM production_runs WHERE date=? AND status='completed'", (d,)).fetchone()

    closing_record = db.execute("SELECT * FROM daily_closings WHERE closing_date=?", (d,)).fetchone()

    if request.method == "POST" and not closing_record:
        summary_payload = json.dumps({
            "invoices_count": sales_day["n"],
            "sales_total_paise": sales_day["tot"],
            "payments_count": payments_day["n"],
            "payments_total_paise": payments_day["s"],
            "runs_count": runs_day["n"],
            "output_packets": runs_day["fg"] // 1000,
        })
        with tx(db):
            db.execute(
                "INSERT INTO daily_closings(closing_date, closed_by, closed_at, summary_json, notes) "
                "VALUES (?,?,?,?,?)",
                (d, g.user["id"], NOW(), summary_payload, request.form.get("notes", "")))
        from .. import audit
        audit.log(db, g.user, "daily_closing", None, "close", {"date": d})
        flash(f"Daily Business Books officially closed for {d}", "ok")
        return redirect(url_for("intelligence.daily_closing", date=d))

    return render_template("intelligence/daily_closing.html", date=d, sales=sales_day, payments=payments_day,
                           purchases=purchases_day, runs=runs_day, record=closing_record)


# ---------------------------------------------------------------- Digital Batch Card & QR Tracking
@bp.route("/prod/runs/<int:rid>/card")
@login_required(*ADMIN_PROD)
def batch_card(rid):
    db = get_db()
    s = production.run_summary(db, rid)
    qr_url = url_for("intelligence.verify_batch", batch_no=s["run"]["batch_no"], _external=True)
    return render_template("intelligence/batch_card.html", s=s, qr_url=qr_url)


@bp.route("/verify/batch/<batch_no>")
def verify_batch(batch_no):
    """Publicly accessible batch authenticity verification page."""
    db = get_db()
    run = db.execute(
        "SELECT r.run_no, r.batch_no, r.date, r.expiry, r.qa_status, i.name product_name, i.hsn "
        "FROM production_runs r JOIN items i ON i.id=r.product_id "
        "WHERE r.batch_no=?", (batch_no,)).fetchone()
    if not run:
        return render_template("intelligence/batch_verify.html", found=False, batch_no=batch_no)
    return render_template("intelligence/batch_verify.html", found=True, run=dict(run))


# ---------------------------------------------------------------- Quality Management
@bp.route("/quality", methods=["GET", "POST"])
@login_required(*ADMIN_PROD)
def quality_management():
    db = get_db()
    if request.method == "POST":
        f = request.form
        n = next_seq(db, "QA")
        qa_no = f"QA-{n:04d}"
        with tx(db):
            db.execute(
                "INSERT INTO quality_inspections(inspection_no, target_type, target_id, batch_no, date, inspector_id, "
                "status, moisture_pct, seal_integrity, aroma_taste, weight_check, defects_count, remarks, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (qa_no, f["target_type"], int(f["target_id"]), f.get("batch_no"), today(), g.user["id"],
                 f["status"], float(f.get("moisture", 0)), f.get("seal", "Pass"), f.get("aroma", "Pass"),
                 f.get("weight", "Pass"), int(f.get("defects", 0)), f.get("remarks", ""), NOW()))
            # Update run qa_status if applicable
            if f["target_type"] == "batch":
                db.execute("UPDATE production_runs SET qa_status=? WHERE id=?", (f["status"], int(f["target_id"])))
        flash(f"Quality inspection {qa_no} recorded", "ok")
        return redirect(url_for("intelligence.quality_management"))

    inspections = db.execute("SELECT q.*, u.full_name inspector_name FROM quality_inspections q LEFT JOIN users u ON u.id=q.inspector_id ORDER BY q.id DESC").fetchall()
    completed_runs = db.execute("SELECT id, run_no, batch_no, qa_status FROM production_runs WHERE status='completed' ORDER BY id DESC LIMIT 20").fetchall()
    return render_template("intelligence/quality.html", inspections=inspections, runs=completed_runs)


# ---------------------------------------------------------------- Production Bottlenecks & Capacity
@bp.route("/bottlenecks-capacity")
@login_required(*ADMIN_PROD)
def bottlenecks_capacity():
    db = get_db()
    # Rated capacity: e.g. 500 packets per operating day
    rated_capacity_day = 500
    runs = db.execute("SELECT * FROM production_runs WHERE status='completed' ORDER BY id DESC LIMIT 30").fetchall()
    total_output_packets = sum(r["actual_milli"] // 1000 for r in runs)
    days_operated = len({r["date"] for r in runs}) or 1
    actual_daily_avg = total_output_packets / days_operated
    utilization_pct = (D(actual_daily_avg * 100) / D(rated_capacity_day)).quantize(Decimal("0.1"))

    # Delay / Bottleneck issues
    delayed_runs = [r for r in runs if r["expected_milli"] > r["actual_milli"]]

    return render_template("intelligence/bottlenecks_capacity.html",
                           rated_capacity=rated_capacity_day, actual_avg=int(actual_daily_avg),
                           utilization_pct=utilization_pct, delayed_runs=delayed_runs, total_runs=len(runs))
