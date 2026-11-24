"""Batch Traceability Blueprint."""
from flask import Blueprint, render_template, request

from ..db import get_db
from ..services import traceability
from .auth import login_required

bp = Blueprint("traceability", __name__)


@bp.route("/traceability")
@login_required()
def view():
    db = get_db()
    batch_q = (request.args.get("batch") or "").strip()
    result = None
    if batch_q:
        result = traceability.trace_batch(db, batch_q)

    # Fetch recent batches to show as quick click hints
    recent_runs = db.execute(
        "SELECT batch_no, run_no, date FROM production_runs WHERE batch_no IS NOT NULL ORDER BY id DESC LIMIT 6"
    ).fetchall()
    recent_lots = db.execute(
        "SELECT pl.batch_no, p.purchase_no, p.grn_no FROM purchase_lines pl JOIN purchases p ON p.id=pl.purchase_id WHERE pl.batch_no IS NOT NULL ORDER BY p.id DESC LIMIT 6"
    ).fetchall()

    return render_template("traceability/view.html", batch_q=batch_q, result=result, recent_runs=recent_runs, recent_lots=recent_lots)
