"""Profitability & Unit Economics Blueprint."""
from flask import Blueprint, render_template

from ..db import get_db
from ..services import profitability
from .auth import login_required

bp = Blueprint("profitability", __name__)
ROLES = ("admin", "owner", "accountant")


@bp.route("/profitability")
@login_required(*ROLES)
def view():
    db = get_db()
    products = profitability.calculate_product_profitability(db)
    customers = profitability.calculate_customer_profitability(db)

    tot_rev = sum(p["net_revenue_paise"] for p in products)
    tot_cogs = sum(p["cogs_paise"] for p in products)
    tot_gp = tot_rev - tot_cogs
    avg_margin = round((tot_gp * 100 / tot_rev), 1) if tot_rev > 0 else 0.0

    return render_template(
        "profitability/view.html",
        products=products,
        customers=customers,
        total_revenue_paise=tot_rev,
        total_cogs_paise=tot_cogs,
        total_gross_profit_paise=tot_gp,
        avg_margin_pct=avg_margin,
    )
