"""Material Requirements Planning (MRP) Blueprint."""
from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..db import get_db, tx
from ..services import mrp
from ..util import ServiceError
from .auth import login_required

bp = Blueprint("mrp", __name__)
ROLES = ("admin", "production", "owner")


@bp.route("/mrp")
@login_required(*ROLES)
def view():
    db = get_db()
    data = mrp.run_mrp(db)
    return render_template("mrp/dashboard.html", mrp=data)


@bp.route("/mrp/generate-pos", methods=["POST"])
@login_required("admin")
def generate_pos():
    db = get_db()
    try:
        with tx(db):
            created = mrp.create_suggested_pos_action(db, g.user)
        if created:
            flash(f"Successfully generated {len(created)} Purchase Orders from MRP suggestions!", "ok")
        else:
            flash("No material shortages requiring new Purchase Orders at this time.", "ok")
    except ServiceError as e:
        flash(str(e), "error")
    return redirect(url_for("mrp.view"))
