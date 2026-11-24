"""Business Decision Support Blueprint."""
from flask import Blueprint, render_template

from ..db import get_db
from ..services import decisions
from .auth import login_required

bp = Blueprint("decisions", __name__)
ROLES = ("admin", "owner")


@bp.route("/decisions")
@login_required(*ROLES)
def view():
    db = get_db()
    recs = decisions.generate_recommendations(db)
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for r in recs:
        counts[r["priority"]] = counts.get(r["priority"], 0) + 1
    return render_template("decisions/view.html", recommendations=recs, counts=counts)
