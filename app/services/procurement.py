"""Procurement service: Suppliers, Purchase Orders, Goods Receipt (GRN), and Supplier Payables."""
import datetime as dt

from .. import audit
from ..db import next_seq
from ..util import D, ServiceError, round_half_up, to_milli, to_paise, today
from . import stock

NOW = lambda: dt.datetime.now().isoformat(timespec="seconds")


def list_suppliers(db, active_only=True):
    sql = "SELECT * FROM suppliers"
    if active_only:
        sql += " WHERE active=1"
    sql += " ORDER BY name"
    return [dict(r) for r in db.execute(sql)]


def get_supplier(db, supplier_id):
    r = db.execute("SELECT * FROM suppliers WHERE id=?", (supplier_id,)).fetchone()
    return dict(r) if r else None


def save_supplier(db, user, data, supplier_id=None):
    name = (data.get("name") or "").strip()
    if not name:
        raise ServiceError("Supplier name is required")
    gstin = (data.get("gstin") or "").strip().upper()
    phone = (data.get("phone") or "").strip()
    email = (data.get("email") or "").strip()
    address = (data.get("address") or "").strip()
    contact = (data.get("contact_person") or "").strip()
    lead_time = int(data.get("lead_time_days") or 7)
    rating = float(data.get("rating") or 5.0)
    terms = int(data.get("payment_terms_days") or 30)

    if supplier_id:
        db.execute(
            "UPDATE suppliers SET name=?, gstin=?, phone=?, email=?, address=?, contact_person=?, "
            "lead_time_days=?, rating=?, payment_terms_days=? WHERE id=?",
            (name, gstin, phone, email, address, contact, lead_time, rating, terms, supplier_id),
        )
        audit.log(db, user, "supplier", supplier_id, "update", {"name": name})
        return supplier_id
    cur = db.execute(
        "INSERT INTO suppliers(name, gstin, phone, email, address, contact_person, lead_time_days, rating, payment_terms_days) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (name, gstin, phone, email, address, contact, lead_time, rating, terms),
    )
    sid = cur.lastrowid
    audit.log(db, user, "supplier", sid, "create", {"name": name})
    return sid


# ---------------------------------------------------------------- Purchase Orders
def create_purchase_order(db, user, supplier_id, order_date=None, lines=None, notes="", expected_delivery=None):
    """lines = [{'item_id': int, 'qty_milli': int, 'rate_paise': int}]"""
    order_date = order_date or today()
    supp = get_supplier(db, supplier_id)
    if not supp:
        raise ServiceError("Valid supplier is required")
    if not lines:
        raise ServiceError("At least one item is required in Purchase Order")

    n = next_seq(db, "PO")
    po_no = f"PO-{n:05d}"
    tot = sum(round_half_up(D(ln["qty_milli"]) * ln["rate_paise"] / 1000) for ln in lines)

    cur = db.execute(
        "INSERT INTO purchase_orders(po_no, supplier_id, status, order_date, expected_delivery, "
        "total_amount_paise, notes, created_by, created_at, updated_at) "
        "VALUES (?, ?, 'draft', ?, ?, ?, ?, ?, ?, ?)",
        (po_no, supplier_id, order_date, expected_delivery, tot, notes, user["id"] if user else None, NOW(), NOW()),
    )
    po_id = cur.lastrowid

    for ln in lines:
        amt = round_half_up(D(ln["qty_milli"]) * ln["rate_paise"] / 1000)
        db.execute(
            "INSERT INTO purchase_order_lines(po_id, item_id, qty_milli, rate_paise, amount_paise) "
            "VALUES (?, ?, ?, ?, ?)",
            (po_id, ln["item_id"], ln["qty_milli"], ln["rate_paise"], amt),
        )

    audit.log(db, user, "purchase_order", po_id, "create", {"po_no": po_no, "total_paise": tot})
    return po_id


def approve_purchase_order(db, user, po_id):
    po = db.execute("SELECT * FROM purchase_orders WHERE id=?", (po_id,)).fetchone()
    if not po or po["status"] != "draft":
        raise ServiceError("Only draft Purchase Orders can be approved")
    db.execute(
        "UPDATE purchase_orders SET status='approved', approved_by=?, updated_at=? WHERE id=?",
        (user["id"] if user else None, NOW(), po_id),
    )
    audit.log(db, user, "purchase_order", po_id, "approve", {"po_no": po["po_no"]})


def cancel_purchase_order(db, user, po_id, reason=""):
    po = db.execute("SELECT * FROM purchase_orders WHERE id=?", (po_id,)).fetchone()
    if not po or po["status"] in ("received", "cancelled"):
        raise ServiceError("This Purchase Order cannot be cancelled")
    db.execute(
        "UPDATE purchase_orders SET status='cancelled', notes=notes || ' | Cancelled: ' || ?, updated_at=? WHERE id=?",
        (reason, NOW(), po_id),
    )
    audit.log(db, user, "purchase_order", po_id, "cancel", {"reason": reason})


def receive_purchase_order(db, user, po_id, date, supplier_invoice_no="", received_lines=None, batch_no="", expiry=None):
    """Fulfills an approved PO, creates a purchase record with GRN, and updates stock ledger."""
    po = db.execute("SELECT * FROM purchase_orders WHERE id=?", (po_id,)).fetchone()
    if not po or po["status"] not in ("approved", "partially_received"):
        raise ServiceError("Only approved Purchase Orders can receive goods")

    date = date or today()
    lines_db = db.execute("SELECT * FROM purchase_order_lines WHERE po_id=?", (po_id,)).fetchall()
    recs = received_lines or {l["id"]: (l["qty_milli"] - l["received_qty_milli"]) for l in lines_db}

    # Generate GRN & Purchase No
    p_num = next_seq(db, "PUR")
    purchase_no = f"PUR-{p_num:05d}"
    grn_no = f"GRN-{p_num:05d}"

    cur = db.execute(
        "INSERT INTO purchases(purchase_no, supplier_id, date, supplier_invoice_no, created_by, created_at, "
        "po_id, status, grn_no, payment_status, paid_paise, notes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'completed', ?, 'unpaid', 0, ?)",
        (purchase_no, po["supplier_id"], date, supplier_invoice_no, user["id"] if user else None, NOW(),
         po_id, grn_no, f"Received against {po['po_no']}"),
    )
    purchase_id = cur.lastrowid

    total_po_fulfilled = True
    for ln in lines_db:
        rec_qty = recs.get(ln["id"], 0)
        if rec_qty <= 0:
            if ln["received_qty_milli"] < ln["qty_milli"]:
                total_po_fulfilled = False
            continue

        new_rec = ln["received_qty_milli"] + rec_qty
        if new_rec < ln["qty_milli"]:
            total_po_fulfilled = False

        db.execute(
            "UPDATE purchase_order_lines SET received_qty_milli=? WHERE id=?",
            (new_rec, ln["id"]),
        )

        item = db.execute("SELECT * FROM items WHERE id=?", (ln["item_id"],)).fetchone()
        rate_rupees_str = str(D(ln["rate_paise"]) / 100)
        amt_paise = round_half_up(D(rec_qty) * ln["rate_paise"] / 1000)
        line_batch = batch_no or f"LOT-{po['supplier_id']}-{date.replace('-', '')}-{ln['id']}"

        db.execute(
            "INSERT INTO purchase_lines(purchase_id, item_id, qty_milli, rate, amount_paise, batch_no, expiry) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (purchase_id, ln["item_id"], rec_qty, rate_rupees_str, amt_paise, line_batch, expiry),
        )

        stock.post(
            db,
            item_id=ln["item_id"],
            qty_milli=rec_qty,
            value_paise=amt_paise,
            move_type="purchase",
            source_type="purchase",
            source_id=purchase_id,
            user=user,
            date=date,
            batch_no=line_batch,
            expiry=expiry,
            note=f"GRN: {grn_no} against {po['po_no']}",
        )

    new_status = "received" if total_po_fulfilled else "partially_received"
    db.execute(
        "UPDATE purchase_orders SET status=?, updated_at=? WHERE id=?",
        (new_status, NOW(), po_id),
    )
    audit.log(db, user, "purchase", purchase_id, "receive_grn", {"po_id": po_id, "grn_no": grn_no})
    return purchase_id, grn_no


# ---------------------------------------------------------------- Supplier Payables & Payments
def record_supplier_payment(db, user, supplier_id, amount_paise, date=None, mode="Bank Transfer", reference="", notes="", purchase_id=None, po_id=None):
    date = date or today()
    if amount_paise <= 0:
        raise ServiceError("Payment amount must be greater than zero")

    cur = db.execute(
        "INSERT INTO supplier_payments(supplier_id, purchase_id, po_id, date, amount_paise, mode, reference, notes, created_by, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (supplier_id, purchase_id, po_id, date, amount_paise, mode, reference, notes, user["id"] if user else None, NOW()),
    )
    pay_id = cur.lastrowid

    # If linked to a purchase, update paid amount and status
    if purchase_id:
        p = db.execute("SELECT * FROM purchases WHERE id=?", (purchase_id,)).fetchone()
        if p:
            tot = db.execute("SELECT COALESCE(SUM(amount_paise), 0) s FROM purchase_lines WHERE purchase_id=?", (purchase_id,)).fetchone()["s"]
            new_paid = (p["paid_paise"] or 0) + amount_paise
            new_st = "paid" if new_paid >= tot else "partial"
            db.execute("UPDATE purchases SET paid_paise=?, payment_status=? WHERE id=?", (new_paid, new_st, purchase_id))

    audit.log(db, user, "supplier_payment", pay_id, "create", {"supplier_id": supplier_id, "amount_paise": amount_paise})
    return pay_id


def supplier_payables(db, as_of=None):
    """Calculates outstanding dues to each supplier based on purchases and payments."""
    as_of = as_of or today()
    suppliers = list_suppliers(db, active_only=False)
    results = []

    for s in suppliers:
        purchases = db.execute(
            """SELECT p.id, p.purchase_no, p.date, p.grn_no, p.supplier_invoice_no,
                      COALESCE(SUM(pl.amount_paise), 0) total_paise,
                      p.paid_paise
               FROM purchases p
               JOIN purchase_lines pl ON pl.purchase_id=p.id
               WHERE p.supplier_id=? AND p.date<=?
               GROUP BY p.id ORDER BY p.date""",
            (s["id"], as_of),
        ).fetchall()

        total_billed = sum(p["total_paise"] for p in purchases)
        total_paid_records = db.execute(
            "SELECT COALESCE(SUM(amount_paise), 0) s FROM supplier_payments WHERE supplier_id=? AND date<=?",
            (s["id"], as_of),
        ).fetchone()["s"]

        outstanding = max(0, total_billed - total_paid_records)
        results.append({
            "supplier": s,
            "total_purchases_paise": total_billed,
            "total_paid_paise": total_paid_records,
            "outstanding_paise": outstanding,
            "purchases": [dict(p) for p in purchases],
        })

    return sorted(results, key=lambda x: -x["outstanding_paise"])


def get_supplier_performance(db, supplier_id):
    """Calculates supplier delivery reliability and purchase history."""
    s = get_supplier(db, supplier_id)
    if not s:
        return None

    pos = db.execute(
        "SELECT * FROM purchase_orders WHERE supplier_id=? ORDER BY id DESC",
        (supplier_id,),
    ).fetchall()

    purchases = db.execute(
        """SELECT p.*, COALESCE(SUM(pl.amount_paise), 0) total_paise
           FROM purchases p
           LEFT JOIN purchase_lines pl ON pl.purchase_id=p.id
           WHERE p.supplier_id=?
           GROUP BY p.id ORDER BY p.date DESC""",
        (supplier_id,),
    ).fetchall()

    return {
        "supplier": s,
        "total_pos": len(pos),
        "total_purchases": len(purchases),
        "total_spend_paise": sum(p["total_paise"] for p in purchases),
        "pos": [dict(po) for po in pos],
        "purchases": [dict(p) for p in purchases],
    }
