"""Salesman (mobile) views + JSON API used by the offline-capable order form."""
from flask import Blueprint, g, jsonify, render_template, request, redirect, flash

from ..db import get_db, tx
from ..services import sales
from ..units import units_for
from ..util import ServiceError, money
from .auth import login_required

bp = Blueprint("sales", __name__)


@bp.route("/m/order")
@login_required("salesman")
def order_new():
    return render_template("sales/order_new.html")


@bp.route("/api/catalog")
@login_required("salesman")
def catalog():
    db = get_db()
    products = db.execute("SELECT * FROM items WHERE kind='finished' AND active=1 ORDER BY name").fetchall()
    prices = {}
    for r in db.execute("SELECT * FROM customer_prices"):
        prices.setdefault(r["customer_id"], {})[r["item_id"]] = r["price_paise"]
    return jsonify(
        customers=[{"id": c["id"], "name": c["name"], "type": c["type"], "state": c["state_name"], "mine": c["salesman_id"] == g.user["id"]}
                   for c in db.execute("SELECT * FROM customers ORDER BY name")],
        products=[{"id": p["id"], "name": p["name"], "price_paise": p["price_paise"], "units": units_for(p), "base_unit": p["base_unit"],
                   "carton_size": p["carton_size"]} for p in products],
        prices=prices)


@bp.route("/api/orders", methods=["POST"])
@login_required("salesman")
def api_orders():
    d = request.get_json(force=True, silent=True) or {}
    db = get_db()
    try:
        with tx(db):
            oid, created = sales.create_order(db, g.user, int(d.get("customer_id") or 0), d.get("lines") or [],
                                              d.get("client_uuid"), d.get("notes", ""))
    except (ServiceError, ValueError, KeyError) as e:
        return jsonify(ok=False, error=str(e)), 400
    o = db.execute("SELECT order_no FROM orders WHERE id=?", (oid,)).fetchone()
    return jsonify(ok=True, id=oid, order_no=o["order_no"], duplicate=not created)


@bp.route("/my/orders")
@login_required("salesman")
def my_orders():
    db = get_db()
    rows = [{**dict(o), "total": sales.order_total_paise(db, o["id"])} for o in db.execute(
        "SELECT o.*, c.name customer FROM orders o JOIN customers c ON c.id=o.customer_id WHERE o.salesman_id=? ORDER BY o.id DESC", (g.user["id"],))]
    for r in rows:
        r["lines"] = db.execute("SELECT i.name, ol.uom_note FROM order_lines ol JOIN items i ON i.id=ol.item_id WHERE order_id=?", (r["id"],)).fetchall()
    return render_template("sales/my_orders.html", orders=rows)


@bp.route("/my/sales")
@login_required("salesman")
def my_sales():
    db = get_db()
    by = {}
    for o in db.execute("SELECT o.id, c.name FROM orders o JOIN customers c ON c.id=o.customer_id "
                        "WHERE o.salesman_id=? AND o.status NOT IN ('rejected','cancelled')", (g.user["id"],)):
        a = by.setdefault(o["name"], [0, 0])
        a[0] += 1
        a[1] += sales.order_total_paise(db, o["id"])
    return render_template("sales/my_sales.html", rows=sorted(by.items(), key=lambda kv: -kv[1][1]))


@bp.route("/m/visits", methods=["GET", "POST"])
@login_required("salesman")
def visit_log():
    db = get_db()
    if request.method == "POST":
        try:
            lat, lon = float(request.form["latitude"]), float(request.form["longitude"])
            if not (-90 <= lat <= 90 and -180 <= lon <= 180): raise ValueError("Invalid coordinates")
            customer_id = int(request.form.get("customer_id") or 0) or None
            if customer_id and not db.execute("SELECT 1 FROM customers WHERE id=?", (customer_id,)).fetchone():
                raise ValueError("Invalid customer")
            with tx(db):
                db.execute("INSERT INTO salesman_visits(salesman_id,customer_id,visited_at,latitude,longitude,note) VALUES(?,?,?,?,?,?)",
                    (g.user["id"], customer_id, __import__('app.util', fromlist=['now']).now(), lat, lon, request.form.get("note", "")))
            flash("GPS visit recorded", "success")
        except (ValueError, KeyError) as e:
            flash(str(e), "error")
        return redirect("/m/visits")
    customers = db.execute("SELECT id,name FROM customers WHERE salesman_id=? OR salesman_id IS NULL ORDER BY name", (g.user["id"],)).fetchall()
    visits = db.execute("SELECT v.*,c.name customer FROM salesman_visits v LEFT JOIN customers c ON c.id=v.customer_id WHERE v.salesman_id=? ORDER BY v.id DESC", (g.user["id"],)).fetchall()
    return render_template("sales/visits.html", customers=customers, visits=visits)
