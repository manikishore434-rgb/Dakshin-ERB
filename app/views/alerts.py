"""Smart Alerts and Exception Management Blueprint."""
from flask import Blueprint, render_template, request

from ..db import get_db
from ..services import alerts
from .auth import login_required

bp = Blueprint("alerts", __name__)
ROLES = ("admin", "owner", "production", "accountant")


@bp.route("/alerts")
@login_required(*ROLES)
def view():
    db = get_db()
    cat = request.args.get("category")
    sev = request.args.get("severity")
    all_alerts = alerts.get_active_alerts(db)

    filtered = all_alerts
    if cat:
        filtered = [a for a in filtered if a["category"].lower() == cat.lower()]
    if sev:
        filtered = [a for a in filtered if a["severity"].lower() == sev.lower()]

    counts = alerts.alert_counts(db)
    return render_template("alerts/view.html", alerts=filtered, counts=counts, current_cat=cat, current_sev=sev)
