"""Production supervisor: purchases/receipts, BOM-based runs, output, wastage, overheads, adjustments."""
from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..db import get_db, tx
from ..routes_helpers import record_purchase
from ..services import production, stock
from ..units import units_for
from ..util import D, ServiceError, to_milli, to_paise, today
from .auth import login_required

bp = Blueprint("production", __name__)
ROLES = ("production", "admin")


def _do(fn, ok_msg):
    db = get_db()
    try:
        with tx(db):
            r = fn(db, g.user)
        flash(ok_msg, "ok")
        return r
    except (ServiceError, ValueError, ArithmeticError) as e:
        flash(str(e), "error")


@bp.route("/prod/runs")
@login_required(*ROLES)
def runs():
    db = get_db()
    rows = [production.run_summary(db, r["id"]) for r in db.execute("SELECT id FROM production_runs ORDER BY id DESC LIMIT 50")]
    return render_template("prod/runs.html", runs=rows)


@bp.route("/prod/runs/new", methods=["GET", "POST"])
@login_required(*ROLES)
def run_new():
    db = get_db()
    products = db.execute("SELECT i.* FROM items i JOIN boms b ON b.product_id=i.id").fetchall()
    pid = int(request.values.get("product_id") or (products[0]["id"] if products else 0))
    batches = D(request.values.get("batches") or 1)
    if request.method == "POST":
        bom, lines = production.get_bom(db, pid)
        issues = {}
        for bl in lines:
            if bl["kind"] == "raw" and request.form.get(f"issue_{bl['item_id']}", "") != "":
                item = db.execute("SELECT * FROM items WHERE id=?", (bl["item_id"],)).fetchone()
                from ..units import to_base_milli
                issues[bl["item_id"]] = to_base_milli(request.form[f"issue_{bl['item_id']}"], request.form.get(f"unit_{bl['item_id']}"), item)
        rid = _do(lambda db, u: production.start_run(db, u, pid, batches, issues, request.form.get("date") or today(), request.form.get("notes", "")),
                  "Run started - raw materials issued from stock")
        if rid:
            return redirect(url_for("production.run_detail", rid=rid))
    plan = []
    if pid:
        bom, lines = production.get_bom(db, pid)
        plan = [{**dict(l), "planned": int(D(l["qty_milli"]) * to_milli(batches) / 1000), "units": units_for(l)} for l in lines if l["kind"] == "raw"]
        expected = int(D(bom["yield_milli"]) * to_milli(batches) / 1000)
    else:
        expected = 0
    return render_template("prod/run_new.html", products=products, pid=pid, batches=batches, plan=plan, expected=expected)


@bp.route("/prod/runs/<int:rid>")
@login_required(*ROLES)
def run_detail(rid):
    db = get_db()
    s = production.run_summary(db, rid)
    raw_lines = [l for l in s["lines"] if l["kind"] == "raw"]
    pack_lines = [l for l in s["lines"] if l["kind"] == "packaging"]
    overheads = db.execute("SELECT * FROM run_overheads WHERE run_id=? ORDER BY id", (rid,)).fetchall()
    ledger = db.execute("SELECT l.*, i.name FROM stock_ledger l JOIN items i ON i.id=l.item_id WHERE source_type='production_run' AND source_id=? ORDER BY l.id", (rid,)).fetchall()
    return render_template("prod/run_detail.html", s=s, raw_lines=raw_lines, pack_lines=pack_lines, overheads=overheads, ledger=ledger)


@bp.route("/prod/runs/<int:rid>/<action>", methods=["POST"])
@login_required(*ROLES)
def run_action(rid, action):
    f, db = request.form, get_db()
    from ..units import to_base_milli
    if action == "issue":
        def go(db, u):
            iss = {}
            for l in db.execute("SELECT rl.item_id FROM run_lines rl JOIN items i ON i.id=rl.item_id WHERE run_id=? AND i.kind='raw'", (rid,)):
                v = f.get(f"issue_{l['item_id']}", "")
                if v != "":
                    item = db.execute("SELECT * FROM items WHERE id=?", (l["item_id"],)).fetchone()
                    iss[l["item_id"]] = to_base_milli(v, f.get(f"unit_{l['item_id']}"), item)
            production.issue_materials(db, u, rid, iss, f.get("date") or today())
        _do(go, "Materials issued")
    elif action == "complete":
        def go(db, u):
            pk = {}
            for l in db.execute("SELECT rl.item_id FROM run_lines rl JOIN items i ON i.id=rl.item_id WHERE run_id=? AND i.kind='packaging'", (rid,)):
                v = f.get(f"pack_{l['item_id']}", "")
                pk[l["item_id"]] = to_milli(v) if v != "" else None
            production.complete_run(db, u, rid, to_milli(f["good"]), to_milli(f.get("damaged") or 0), pk, f.get("date") or today())
        _do(go, "Output recorded - raw/packaging stock down, finished goods up")
    elif action == "overhead":
        _do(lambda db, u: production.add_overhead(db, u, rid, f["kind"], to_paise(f["amount"]), f.get("note", ""), f.get("date") or today()), "Overhead added")
    elif action == "cancel":
        _do(lambda db, u: production.cancel_run(db, u, rid, f.get("reason", "")), "Run cancelled; stock movements reversed")
    return redirect(url_for("production.run_detail", rid=rid))


@bp.route("/prod/pool-overhead", methods=["POST"])
@login_required(*ROLES)
def pool_overhead():
    f = request.form
    _do(lambda db, u: production.add_overhead(db, u, None, f["kind"], to_paise(f["amount"]), f.get("note", ""), f.get("date") or today()),
        "Monthly overhead added (allocated to runs by good packets)")
    return redirect(url_for("production.runs"))


@bp.route("/prod/purchases", methods=["GET", "POST"])
@login_required(*ROLES)
def purchases():
    db, f = get_db(), request.form
    if request.method == "POST":
        lines = []
        for i in range(1, 6):
            if f.get(f"item_{i}") and f.get(f"qty_{i}"):
                lines.append((int(f[f"item_{i}"]), f[f"qty_{i}"], f.get(f"unit_{i}"), f.get(f"rate_{i}") or "0", f.get(f"batch_{i}") or None, f.get(f"expiry_{i}") or None))
        _do(lambda db, u: record_purchase(db, u, int(f["supplier_id"]) if f.get("supplier_id") else None, f.get("date") or today(),
                                          f.get("supplier_invoice_no", ""), lines), "Receipt recorded - stock increased")
        return redirect(url_for("production.purchases"))
    inputs = db.execute("SELECT * FROM items WHERE kind<>'finished' AND active=1 ORDER BY kind, name").fetchall()
    return render_template("prod/purchases.html", inputs=inputs, units={i["id"]: units_for(i) for i in inputs},
                           suppliers=db.execute("SELECT * FROM suppliers").fetchall(),
                           recent=db.execute("SELECT p.*, s.name supplier FROM purchases p LEFT JOIN suppliers s ON s.id=p.supplier_id ORDER BY p.id DESC LIMIT 10").fetchall(),
                           items_all=db.execute("SELECT * FROM items WHERE active=1 ORDER BY kind, name").fetchall())


@bp.route("/prod/adjust", methods=["POST"])
@login_required(*ROLES)
def adjust():
    f = request.form
    from ..units import to_base_milli
    def go(db, u):
        item = db.execute("SELECT * FROM items WHERE id=?", (int(f["item_id"]),)).fetchone()
        sign = -1 if f.get("direction") == "decrease" else 1
        stock.adjust(db, u, item["id"], sign * to_base_milli(f["qty"], f.get("unit"), item), f.get("reason", ""), f.get("date") or today())
    _do(go, "Stock adjustment posted")
    return redirect(url_for("production.purchases"))
