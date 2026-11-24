"""Procurement blueprint: Purchase Orders, Suppliers, and Supplier Payables."""
from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..db import get_db, tx
from ..services import procurement
from ..util import D, ServiceError, round_half_up, to_milli, to_paise, today, money
from .auth import login_required

bp = Blueprint("procurement", __name__)
ROLES = ("admin", "production", "owner", "accountant")


def _do(fn, ok_msg):
    db = get_db()
    try:
        with tx(db):
            r = fn(db, g.user)
        flash(ok_msg, "ok")
        return r
    except (ServiceError, ValueError) as e:
        flash(str(e), "error")


@bp.route("/procurement/orders")
@login_required(*ROLES)
def purchase_orders():
    db = get_db()
    st = request.args.get("status", "")
    query = """SELECT po.*, s.name supplier_name, u.full_name creator_name,
                      COALESCE(SUM(pol.qty_milli), 0) total_qty_milli
               FROM purchase_orders po
               JOIN suppliers s ON s.id=po.supplier_id
               LEFT JOIN users u ON u.id=po.created_by
               LEFT JOIN purchase_order_lines pol ON pol.po_id=po.id
               WHERE (?='' OR po.status=?)
               GROUP BY po.id ORDER BY po.id DESC"""
    orders = [dict(r) for r in db.execute(query, (st, st))]
    return render_template("procurement/orders.html", orders=orders, status=st)


@bp.route("/procurement/orders/new", methods=["GET", "POST"])
@login_required("admin", "production")
def purchase_order_new():
    db = get_db()
    suppliers = procurement.list_suppliers(db)
    items = db.execute("SELECT * FROM items WHERE kind IN ('raw', 'packaging') AND active=1 ORDER BY kind DESC, name").fetchall()

    if request.method == "POST":
        f = request.form
        supp_id = int(f.get("supplier_id") or 0)
        lines = []
        for i in range(1, 6):
            it_id = f.get(f"item_{i}")
            qty_val = f.get(f"qty_{i}")
            rate_val = f.get(f"rate_{i}")
            if it_id and qty_val and rate_val:
                lines.append({
                    "item_id": int(it_id),
                    "qty_milli": to_milli(qty_val),
                    "rate_paise": to_paise(rate_val),
                })
        poid = _do(
            lambda db, u: procurement.create_purchase_order(
                db, u, supp_id, f.get("order_date") or today(), lines,
                f.get("notes", ""), f.get("expected_delivery")
            ),
            "Purchase Order created successfully"
        )
        if poid:
            return redirect(url_for("procurement.purchase_order_detail", poid=poid))

    return render_template("procurement/order_new.html", suppliers=suppliers, items=items)


@bp.route("/procurement/orders/<int:poid>")
@login_required(*ROLES)
def purchase_order_detail(poid):
    db = get_db()
    po = db.execute(
        """SELECT po.*, s.name supplier_name, s.gstin, s.phone, s.email, s.address,
                  u.full_name creator_name, ap.full_name approver_name
           FROM purchase_orders po
           JOIN suppliers s ON s.id=po.supplier_id
           LEFT JOIN users u ON u.id=po.created_by
           LEFT JOIN users ap ON ap.id=po.approved_by
           WHERE po.id=?""",
        (poid,),
    ).fetchone()
    if not po:
        flash("Purchase order not found", "error")
        return redirect(url_for("procurement.purchase_orders"))

    lines = db.execute(
        """SELECT pol.*, i.name item_name, i.code item_code, i.base_unit
           FROM purchase_order_lines pol
           JOIN items i ON i.id=pol.item_id
           WHERE pol.po_id=? ORDER BY pol.id""",
        (poid,),
    ).fetchall()

    receipts = db.execute(
        """SELECT p.*, COALESCE(SUM(pl.amount_paise), 0) total_paise
           FROM purchases p
           LEFT JOIN purchase_lines pl ON pl.purchase_id=p.id
           WHERE p.po_id=?
           GROUP BY p.id ORDER BY p.date DESC""",
        (poid,),
    ).fetchall()

    return render_template("procurement/order_detail.html", po=dict(po), lines=[dict(l) for l in lines], receipts=[dict(r) for r in receipts])


@bp.route("/procurement/orders/<int:poid>/approve", methods=["POST"])
@login_required("admin")
def purchase_order_approve(poid):
    _do(lambda db, u: procurement.approve_purchase_order(db, u, poid), "Purchase Order approved")
    return redirect(url_for("procurement.purchase_order_detail", poid=poid))


@bp.route("/procurement/orders/<int:poid>/cancel", methods=["POST"])
@login_required("admin")
def purchase_order_cancel(poid):
    reason = request.form.get("reason", "Cancelled by Admin")
    _do(lambda db, u: procurement.cancel_purchase_order(db, u, poid, reason), "Purchase Order cancelled")
    return redirect(url_for("procurement.purchase_order_detail", poid=poid))


@bp.route("/procurement/orders/<int:poid>/receive", methods=["POST"])
@login_required("admin", "production")
def purchase_order_receive(poid):
    f = request.form
    date = f.get("date") or today()
    inv_no = f.get("supplier_invoice_no", "")
    batch_no = f.get("batch_no", "")
    expiry = f.get("expiry") or None

    _do(
        lambda db, u: procurement.receive_purchase_order(db, u, poid, date, inv_no, None, batch_no, expiry),
        "Goods received (GRN) and added to stock ledger"
    )
    return redirect(url_for("procurement.purchase_order_detail", poid=poid))


# ---------------------------------------------------------------- Suppliers
@bp.route("/procurement/suppliers")
@login_required(*ROLES)
def suppliers():
    db = get_db()
    payables = procurement.supplier_payables(db)
    return render_template("procurement/suppliers.html", suppliers=payables)


@bp.route("/procurement/suppliers/new", methods=["GET", "POST"])
@login_required("admin")
def supplier_new():
    if request.method == "POST":
        sid = _do(lambda db, u: procurement.save_supplier(db, u, request.form), "Supplier created")
        if sid:
            return redirect(url_for("procurement.suppliers"))
    return render_template("procurement/supplier_form.html", s=None)


@bp.route("/procurement/suppliers/<int:sid>/edit", methods=["GET", "POST"])
@login_required("admin")
def supplier_edit(sid):
    db = get_db()
    s = procurement.get_supplier(db, sid)
    if not s:
        flash("Supplier not found", "error")
        return redirect(url_for("procurement.suppliers"))
    if request.method == "POST":
        _do(lambda db, u: procurement.save_supplier(db, u, request.form, sid), "Supplier updated")
        return redirect(url_for("procurement.suppliers"))
    return render_template("procurement/supplier_form.html", s=s)


@bp.route("/procurement/suppliers/<int:sid>/pay", methods=["POST"])
@login_required("admin", "accountant")
def supplier_payment(sid):
    f = request.form
    amt = to_paise(f["amount"])
    date = f.get("date") or today()
    mode = f.get("mode", "Bank Transfer")
    ref = f.get("reference", "")
    _do(
        lambda db, u: procurement.record_supplier_payment(db, u, sid, amt, date, mode, ref, f.get("notes", "")),
        "Supplier payment recorded"
    )
    return redirect(url_for("procurement.suppliers"))
