from functools import wraps

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from ..db import get_db

bp = Blueprint("auth", __name__)

HOME = {"salesman": "sales.order_new", "admin": "admin.orders", "production": "production.runs",
        "accountant": "reports.index", "owner": "reports.dashboard"}


def login_required(*roles):
    """Role-based access control. No roles = any logged-in user."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if not g.user:
                return redirect(url_for("auth.login", next=request.path))
            if roles and g.user["role"] not in roles:
                return render_template("forbidden.html"), 403
            return fn(*a, **kw)
        return wrapper
    return deco


@bp.route("/")
def home():
    return redirect(url_for(HOME[g.user["role"]]) if g.user else url_for("auth.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = get_db().execute("SELECT * FROM users WHERE username=? AND active=1", (request.form["username"].strip(),)).fetchone()
        if u and check_password_hash(u["password_hash"], request.form["password"]):
            session.clear()
            session["uid"] = u["id"]
            return redirect(request.args.get("next") or url_for(HOME[u["role"]]))
        flash("Wrong username or password", "error")
    return render_template("login.html")


@bp.route("/language/<lang>")
def language(lang):
    if lang in ("en", "ta"):
        session["lang"] = lang
    return redirect(request.referrer or url_for("auth.login"))


@bp.route("/switch-role/<role>")
def switch_role(role):
    db = get_db()
    u = db.execute("SELECT * FROM users WHERE role=? AND active=1 ORDER BY id LIMIT 1", (role,)).fetchone()
    if u:
        session.clear()
        session["uid"] = u["id"]
        flash(f"Switched persona to {u['full_name']} ({u['role']})", "info")
        return redirect(url_for(HOME.get(u["role"], "auth.login")))
    flash("Role user not found", "error")
    return redirect(url_for("auth.login"))


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
