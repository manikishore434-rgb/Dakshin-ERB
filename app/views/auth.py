from functools import wraps

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from ..db import get_db

bp = Blueprint("auth", __name__)

HOME = {
    "salesman": "sales.order_new",
    "admin": "admin.orders",
    "production": "production.runs",
    "accountant": "reports.index",
    "owner": "owner.suite"
}


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
    return redirect(url_for(HOME.get(g.user["role"], "admin.orders")) if g.user else url_for("auth.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = get_db().execute("SELECT * FROM users WHERE username=? AND active=1", (request.form["username"].strip(),)).fetchone()
        if u and check_password_hash(u["password_hash"], request.form["password"]):
            session.clear()
            session["uid"] = u["id"]
            return redirect(request.args.get("next") or url_for(HOME.get(u["role"], "admin.orders")))
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


@bp.route("/roles", methods=["GET", "POST"])
def roles():
    db = get_db()
    if request.method == "POST":
        target_role = request.form.get("role")
        u = db.execute(
            "SELECT * FROM users WHERE (role=? OR username=?) AND active=1 LIMIT 1",
            (target_role, target_role)
        ).fetchone()
        if u:
            session.clear()
            session["uid"] = u["id"]
            flash(f"Switched role to {u['full_name']} ({u['role']})", "ok")
            return redirect(url_for(HOME.get(u["role"], "admin.orders")))
    users = db.execute("SELECT * FROM users WHERE active=1 ORDER BY role, id").fetchall()
    return render_template("roles.html", users=users)


@bp.route("/api/search")
def api_search():
    """Global search across Orders, Customers, Items, Invoices, Production Batches, and POs."""
    q = (request.args.get("q") or "").strip()
    if not q or len(q) < 2:
        return {"results": []}

    db = get_db()
    like = f"%{q}%"
    results = []

    # 1. Orders
    for o in db.execute("SELECT id, order_no, status FROM orders WHERE order_no LIKE ? LIMIT 4", (like,)):
        results.append({
            "category": "Order",
            "badge_class": "badge-blue",
            "title": f"Order #{o['order_no']}",
            "subtitle": f"Status: {o['status'].capitalize()}",
            "url": url_for("admin.order_detail", oid=o["id"]) if (g.user and g.user["role"] in ("admin", "owner", "accountant")) else url_for("sales.my_orders"),
        })

    # 2. Customers
    for c in db.execute("SELECT id, name, type, phone FROM customers WHERE name LIKE ? OR phone LIKE ? LIMIT 4", (like, like)):
        results.append({
            "category": "Customer",
            "badge_class": "badge-green",
            "title": c["name"],
            "subtitle": f"{c['type'].capitalize()} Â· Phone: {c['phone'] or 'N/A'}",
            "url": url_for("admin.masters") if (g.user and g.user["role"] in ("admin", "owner")) else url_for("sales.order_new"),
        })

    # 3. Items / Products
    for i in db.execute("SELECT id, code, name, kind, base_unit FROM items WHERE name LIKE ? OR code LIKE ? LIMIT 4", (like, like)):
        results.append({
            "category": "Item / SKU",
            "badge_class": "badge-purple",
            "title": f"{i['name']} ({i['code']})",
            "subtitle": f"Kind: {i['kind']} Â· Unit: {i['base_unit']}",
            "url": url_for("reports.report_view", key="stock-summary") if (g.user and g.user["role"] in ("admin", "owner", "accountant")) else url_for("production.runs"),
        })

    # 4. Invoices
    for inv in db.execute("SELECT id, invoice_no, total_paise, date FROM invoices WHERE invoice_no LIKE ? LIMIT 4", (like,)):
        results.append({
            "category": "Invoice",
            "badge_class": "badge-orange",
            "title": f"Invoice #{inv['invoice_no']}",
            "subtitle": f"Date: {inv['date']} Â· Total: â‚¹{inv['total_paise']/100:.2f}",
            "url": url_for("admin.invoices"),
        })

    # 5. Production Runs / Batches
    for r in db.execute("SELECT r.id, r.run_no, r.batch_no, i.name item_name FROM production_runs r JOIN items i ON i.id=r.product_id WHERE r.run_no LIKE ? OR r.batch_no LIKE ? LIMIT 4", (like, like)):
        results.append({
            "category": "Batch",
            "badge_class": "badge-teal",
            "title": f"Run #{r['run_no']} (Batch {r['batch_no'] or 'N/A'})",
            "subtitle": f"Product: {r['item_name']}",
            "url": url_for("production.run_detail", rid=r["id"]),
        })

    # 6. Purchase Orders
    try:
        for po in db.execute("SELECT po.id, po.po_no, po.status, s.name supplier_name FROM purchase_orders po JOIN suppliers s ON s.id=po.supplier_id WHERE po.po_no LIKE ? LIMIT 4", (like,)):
            results.append({
                "category": "PO",
                "badge_class": "badge-blue",
                "title": f"PO #{po['po_no']}",
                "subtitle": f"Supplier: {po['supplier_name']} Â· {po['status'].capitalize()}",
                "url": url_for("procurement.po_detail", poid=po["id"]),
            })
    except Exception:
        pass

    return {"results": results[:10]}


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
