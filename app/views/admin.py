"""Factory admin: order verification, GST invoices, dispatch, payments, masters."""
from urllib.parse import quote

from flask import Blueprint, Response, flash, g, redirect, render_template, request, url_for
from itsdangerous import BadSignature, URLSafeSerializer
from flask import current_app

from ..db import get_db, tx
from ..services import sales
from ..services.invoice_pdf import invoice_pdf
from ..util import D, ServiceError, round_half_up, to_milli, to_paise, today, money
from .auth import login_required

bp = Blueprint("admin", __name__)
ADMIN = ("admin",)
VIEW_INV = ("admin", "accountant", "owner")


def _do(fn, ok_msg, *a, **kw):
    db = get_db()
    try:
        with tx(db):
            r = fn(db, g.user, *a, **kw)
        flash(ok_msg, "ok")
        return r
    except (ServiceError, ValueError) as e:
        flash(str(e), "error")


@bp.route("/admin/orders")
@login_required(*ADMIN)
def orders():
    db = get_db()
    status = request.args.get("status", "")
    rows = []
    for o in db.execute("SELECT o.*, c.name customer, u.full_name salesman FROM orders o JOIN customers c ON c.id=o.customer_id "
                        "JOIN users u ON u.id=o.salesman_id WHERE (?='' OR o.status=?) ORDER BY o.id DESC", (status, status)):
        short = o["status"] == "submitted" and any(c["shortage"] for c in sales.stock_check(db, o["id"]))
        rows.append({**dict(o), "total": sales.order_total_paise(db, o["id"]), "short": short})
    return render_template("admin/orders.html", orders=rows, status=status)


@bp.route("/admin/orders/<int:oid>")
@login_required(*ADMIN)
def order_detail(oid):
    db = get_db()
    o = db.execute("SELECT o.*, c.name customer, c.state_name, c.gstin, u.full_name salesman FROM orders o JOIN customers c ON c.id=o.customer_id "
                   "JOIN users u ON u.id=o.salesman_id WHERE o.id=?", (oid,)).fetchone()
    inv = db.execute("SELECT * FROM invoices WHERE order_id=? AND status='posted' ORDER BY id DESC", (oid,)).fetchone()
    return render_template("admin/order_detail.html", o=o, checks=sales.stock_check(db, oid), inv=inv,
                           total=sales.order_total_paise(db, oid), share=_share(inv) if inv else None)


def _token(inv_id):
    return URLSafeSerializer(current_app.config["SECRET_KEY"], salt="invoice-share").dumps(inv_id)


def _share(inv):
    link = url_for("admin.public_invoice", token=_token(inv["id"]), _external=True)
    text = f"Invoice {inv['invoice_no']} for Rs {money(inv['total_paise'])}: {link}"
    return {"link": link, "whatsapp": "https://wa.me/?text=" + quote(text),
            "mail": "mailto:?subject=" + quote("Invoice " + inv["invoice_no"]) + "&body=" + quote(text)}


@bp.route("/admin/orders/<int:oid>/edit", methods=["POST"])
@login_required(*ADMIN)
def order_edit(oid):
    db = get_db()
    changes = {}
    for ln in db.execute("SELECT id FROM order_lines WHERE order_id=?", (oid,)):
        changes[ln["id"]] = (to_milli(request.form[f"qty_{ln['id']}"]), to_paise(request.form[f"price_{ln['id']}"]))
    _do(lambda db, u: sales.edit_order(db, u, oid, changes), "Order updated")
    return redirect(url_for("admin.order_detail", oid=oid))


@bp.route("/admin/orders/<int:oid>/approve", methods=["POST"])
@login_required(*ADMIN)
def order_approve(oid):
    _do(lambda db, u: sales.approve_order(db, u, oid, bool(request.form.get("allow_shortage"))), "Order approved")
    return redirect(url_for("admin.order_detail", oid=oid))


@bp.route("/admin/orders/<int:oid>/reject", methods=["POST"])
@login_required(*ADMIN)
def order_reject(oid):
    _do(lambda db, u: sales.reject_order(db, u, oid, request.form.get("reason", "")), "Order rejected")
    return redirect(url_for("admin.order_detail", oid=oid))


@bp.route("/admin/orders/<int:oid>/invoice", methods=["POST"])
@login_required(*ADMIN)
def order_invoice(oid):
    _do(lambda db, u: sales.create_invoice(db, u, oid), "GST invoice raised")
    return redirect(url_for("admin.order_detail", oid=oid))


@bp.route("/admin/invoices/<int:iid>/dispatch", methods=["POST"])
@login_required(*ADMIN)
def invoice_dispatch(iid):
    _do(lambda db, u: sales.dispatch(db, u, iid), "Dispatched - finished-goods stock reduced")
    return redirect(request.referrer or url_for("admin.invoices"))


@bp.route("/admin/invoices/<int:iid>/cancel", methods=["POST"])
@login_required(*ADMIN)
def invoice_cancel(iid):
    _do(lambda db, u: sales.cancel_invoice(db, u, iid, request.form.get("reason", "")), "Invoice cancelled with a credit note")
    return redirect(url_for("admin.invoices"))


@bp.route("/admin/invoices")
@login_required(*VIEW_INV)
def invoices():
    db = get_db()
    rows = db.execute("SELECT i.*, c.name customer FROM invoices i JOIN customers c ON c.id=i.customer_id ORDER BY i.id DESC").fetchall()
    return render_template("admin/invoices.html", invoices=rows, share={r["id"]: _share(r) for r in rows if r["status"] == "posted"})


@bp.route("/invoice/<int:iid>.pdf")
@login_required(*VIEW_INV)
def invoice_pdf_view(iid):
    inv = get_db().execute("SELECT invoice_no FROM invoices WHERE id=?", (iid,)).fetchone()
    return Response(invoice_pdf(get_db(), iid), mimetype="application/pdf",
                    headers={"Content-Disposition": f"inline; filename={inv['invoice_no'].replace('/', '-')}.pdf"})


@bp.route("/inv/<token>.pdf")
def public_invoice(token):
    """Unguessable signed link used for the WhatsApp / e-mail share (no login needed by the customer)."""
    try:
        iid = URLSafeSerializer(current_app.config["SECRET_KEY"], salt="invoice-share").loads(token)
    except BadSignature:
        return "Invalid link", 404
    return Response(invoice_pdf(get_db(), iid), mimetype="application/pdf")


@bp.route("/admin/payments", methods=["GET", "POST"])
@login_required(*ADMIN)
def payments():
    db = get_db()
    if request.method == "POST":
        inv = int(request.form.get("invoice_id") or 0) or None
        _do(lambda db, u: sales.record_payment(db, u, int(request.form["customer_id"]), to_paise(request.form["amount"]),
                                               request.form.get("date") or today(), request.form.get("mode", ""),
                                               request.form.get("reference", ""), inv), "Payment recorded")
        return redirect(url_for("admin.payments"))
    recs, advances = sales.receivables(db)
    return render_template("admin/payments.html", open_invoices=[r for r in recs if r["outstanding"] > 0],
                           customers=db.execute("SELECT * FROM customers ORDER BY name").fetchall(),
                           payments=db.execute("SELECT p.*, c.name customer, i.invoice_no FROM payments p JOIN customers c ON c.id=p.customer_id "
                                               "LEFT JOIN invoices i ON i.id=p.invoice_id ORDER BY p.id DESC LIMIT 30").fetchall())


@bp.route("/admin/masters")
@login_required(*ADMIN)
def masters():
    db = get_db()
    boms = []
    for b in db.execute("SELECT b.*, i.name FROM boms b JOIN items i ON i.id=b.product_id"):
        boms.append({**dict(b), "lines": db.execute("SELECT bl.*, i.name, i.base_unit FROM bom_lines bl JOIN items i ON i.id=bl.item_id "
                                                    "WHERE bom_id=? ORDER BY i.kind DESC", (b["id"],)).fetchall()})
    return render_template("admin/masters.html", items=db.execute("SELECT * FROM items ORDER BY kind DESC, name").fetchall(),
                           customers=db.execute("SELECT c.*, u.full_name salesman FROM customers c LEFT JOIN users u ON u.id=c.salesman_id").fetchall(),
                           suppliers=db.execute("SELECT * FROM suppliers").fetchall(), boms=boms,
                           salesmen=db.execute("SELECT * FROM users WHERE role='salesman'").fetchall(),
                           finished=db.execute("SELECT * FROM items WHERE kind='finished'").fetchall(),
                           inputs=db.execute("SELECT * FROM items WHERE kind<>'finished'").fetchall(),
                           tolerance=db.execute("SELECT value FROM settings WHERE key='variance_tolerance_bp'").fetchone()["value"])


@bp.route("/admin/masters/<what>", methods=["POST"])
@login_required(*ADMIN)
def masters_add(what):
    f, db = request.form, get_db()
    try:
        with tx(db):
            if what == "item":
                db.execute("INSERT INTO items(code,name,kind,base_unit,hsn,gst_bp,price_paise,carton_size,pack_role,reorder_level_milli,shelf_life_days)"
                           " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                           (f["code"], f["name"], f["kind"], f["base_unit"], f.get("hsn") or None, round_half_up(D(f.get("gst") or 0) * 100),
                            to_paise(f["price"]) if f.get("price") else None, int(f["carton_size"]) if f.get("carton_size") else None,
                            f.get("pack_role") or None, to_milli(f.get("reorder") or 0), int(f["shelf"]) if f.get("shelf") else None))
            elif what == "customer":
                db.execute("INSERT INTO customers(name,type,gstin,state_code,state_name,address,phone,salesman_id) VALUES (?,?,?,?,?,?,?,?)",
                           (f["name"], f["type"], f.get("gstin") or None, f["state_code"], f["state_name"], f.get("address"), f.get("phone"),
                            int(f["salesman_id"]) if f.get("salesman_id") else None))
            elif what == "supplier":
                db.execute("INSERT INTO suppliers(name,gstin,phone) VALUES (?,?,?)", (f["name"], f.get("gstin"), f.get("phone")))
            elif what == "customer-price":
                db.execute("INSERT INTO customer_prices(customer_id,item_id,price_paise) VALUES (?,?,?) ON CONFLICT(customer_id,item_id) "
                           "DO UPDATE SET price_paise=excluded.price_paise", (int(f["customer_id"]), int(f["item_id"]), to_paise(f["price"])))
            elif what == "bom":
                pid = int(f["product_id"])
                b = db.execute("SELECT id FROM boms WHERE product_id=?", (pid,)).fetchone()
                if f.get("yield"):
                    if b:
                        db.execute("UPDATE boms SET yield_milli=? WHERE id=?", (to_milli(f["yield"]), b["id"]))
                    else:
                        b = {"id": db.execute("INSERT INTO boms(product_id,yield_milli) VALUES (?,?)", (pid, to_milli(f["yield"]))).lastrowid}
                if f.get("item_id") and b:
                    if D(f.get("qty") or 0) == 0:
                        db.execute("DELETE FROM bom_lines WHERE bom_id=? AND item_id=?", (b["id"], int(f["item_id"])))
                    else:
                        db.execute("INSERT INTO bom_lines(bom_id,item_id,qty_milli) VALUES (?,?,?) ON CONFLICT(bom_id,item_id) DO UPDATE SET "
                                   "qty_milli=excluded.qty_milli", (b["id"], int(f["item_id"]), to_milli(f["qty"])))
            elif what == "tolerance":
                db.execute("UPDATE settings SET value=? WHERE key='variance_tolerance_bp'", (str(round_half_up(D(f["pct"]) * 100)),))
        flash("Saved", "ok")
    except Exception as e:  # noqa: BLE001  (duplicate codes, bad numbers ...)
        flash(f"Could not save: {e}", "error")
    return redirect(url_for("admin.masters"))
