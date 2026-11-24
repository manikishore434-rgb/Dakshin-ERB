"""Quality Management (QA/QC) Blueprint."""
from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..db import get_db, tx
from ..services import quality
from ..util import ServiceError
from .auth import login_required

bp = Blueprint("quality", __name__)
ROLES = ("admin", "production", "owner")


@bp.route("/quality/inspections")
@login_required(*ROLES)
def inspections():
    db = get_db()
    st = request.args.get("status")
    typ = request.args.get("type")
    insps = quality.list_inspections(db, status=st, insp_type=typ)
    summary = quality.quality_summary(db)
    return render_template("quality/inspections.html", inspections=insps, summary=summary, status=st, type=typ)


@bp.route("/quality/inspections/new", methods=["GET", "POST"])
@login_required("admin", "production")
def inspection_new():
    db = get_db()
    items = db.execute("SELECT * FROM items WHERE active=1 ORDER BY kind DESC, name").fetchall()
    runs = db.execute("SELECT id, run_no, batch_no, product_id FROM production_runs ORDER BY id DESC LIMIT 20").fetchall()
    purchases = db.execute("SELECT id, purchase_no, grn_no FROM purchases ORDER BY id DESC LIMIT 20").fetchall()

    if request.method == "POST":
        f = request.form
        itype = f.get("inspection_type")
        item_id = int(f.get("item_id") or 0)
        ref_type = f.get("reference_type")
        ref_id = int(f.get("reference_id") or 0)
        batch = f.get("batch_no", "")
        sample = f.get("sample_size", "")
        notes = f.get("notes", "")

        try:
            with tx(db):
                qid = quality.create_inspection(db, g.user, itype, item_id, ref_type, ref_id, batch, sample, {}, notes)
            flash("Inspection registered", "ok")
            return redirect(url_for("quality.inspection_detail", qid=qid))
        except ServiceError as e:
            flash(str(e), "error")

    return render_template("quality/inspection_new.html", items=items, runs=runs, purchases=purchases)


@bp.route("/quality/inspections/<int:qid>", methods=["GET", "POST"])
@login_required(*ROLES)
def inspection_detail(qid):
    db = get_db()
    insp = quality.get_inspection(db, qid)
    if not insp:
        flash("Inspection record not found", "error")
        return redirect(url_for("quality.inspections"))

    if request.method == "POST":
        f = request.form
        verdict = f.get("status")
        cat = f.get("defect_category", "")
        desc = f.get("defect_description", "")
        capa = f.get("corrective_action", "")
        notes = f.get("notes", "")

        try:
            with tx(db):
                quality.record_verdict(db, g.user, qid, verdict, cat, desc, capa, notes)
            flash(f"Verdict recorded: Marked as {verdict.upper()}", "ok")
            return redirect(url_for("quality.inspection_detail", qid=qid))
        except ServiceError as e:
            flash(str(e), "error")

    return render_template("quality/inspection_detail.html", insp=insp)
