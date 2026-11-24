"""Order -> approval -> GST invoice -> dispatch -> payment, plus credit-note cancellation."""
import datetime as dt

from .. import audit
from ..db import next_seq, setting
from ..units import to_base_milli
from ..util import D, ServiceError, fy_of, qty as fmt_qty, round_half_up, today
from . import stock

NOW = lambda: dt.datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------- orders
def price_for(db, customer_id, item):
    r = db.execute("SELECT price_paise FROM customer_prices WHERE customer_id=? AND item_id=?",
                   (customer_id, item["id"])).fetchone()
    return r["price_paise"] if r else item["price_paise"]


def create_order(db, user, customer_id, lines, client_uuid=None, notes="", priority="normal", delivery_date=None):
    """lines = [{'item_id':, 'qty':, 'unit':}]. Idempotent on client_uuid (safe for offline re-sync).
    Returns (order_id, created: bool)."""
    if client_uuid:
        ex = db.execute("SELECT id FROM orders WHERE client_uuid=?", (client_uuid,)).fetchone()
        if ex:
            return ex["id"], False
    cust = db.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
    if not cust:
        raise ServiceError("Select a customer")
    if not lines:
        raise ServiceError("Add at least one product")
    prepared = []
    for ln in lines:
        item = db.execute("SELECT * FROM items WHERE id=? AND kind='finished' AND active=1", (ln["item_id"],)).fetchone()
        if not item:
            raise ServiceError("Unknown product")
        q = to_base_milli(ln["qty"], ln.get("unit"), item)
        if q <= 0:
            raise ServiceError("Quantity must be positive")
        prepared.append((item["id"], q, price_for(db, customer_id, item), f"{ln['qty']} {ln.get('unit') or item['base_unit']}"))
    n = next_seq(db, "ORD")
    cur = db.execute("INSERT INTO orders(order_no,client_uuid,customer_id,salesman_id,status,notes,priority,delivery_date,created_at,updated_at)"
                     " VALUES (?,?,?,?, 'submitted',?,?,?,?,?)",
                     (f"ORD-{n:05d}", client_uuid, customer_id, user["id"], notes, priority or "normal", delivery_date, NOW(), NOW()))
    oid = cur.lastrowid
    for item_id, q, price, note in prepared:
        db.execute("INSERT INTO order_lines(order_id,item_id,qty_milli,price_paise,uom_note) VALUES (?,?,?,?,?)",
                   (oid, item_id, q, price, note))
    audit.log(db, user, "order", oid, "create", {"customer_id": customer_id, "lines": len(prepared), "priority": priority})
    return oid, True


def order_total_paise(db, order_id):
    return sum(round_half_up(D(r["qty_milli"]) * r["price_paise"] / 1000) for r in
               db.execute("SELECT qty_milli, price_paise FROM order_lines WHERE order_id=?", (order_id,)))


def _reserved(db, item_id, exclude_order_id):
    """Finished goods already promised to other approved/invoiced-but-undispatched orders."""
    return db.execute(
        "SELECT COALESCE(SUM(ol.qty_milli),0) s FROM order_lines ol JOIN orders o ON o.id=ol.order_id "
        "WHERE ol.item_id=? AND o.status IN ('approved','invoiced') AND o.id<>?", (item_id, exclude_order_id)).fetchone()["s"]


def stock_check(db, order_id):
    """Per line: required, on hand, reserved by other orders, available, shortage and batches to make."""
    out = []
    for ol in db.execute("SELECT ol.*, i.name, i.base_unit FROM order_lines ol JOIN items i ON i.id=ol.item_id "
                         "WHERE ol.order_id=?", (order_id,)).fetchall():
        on_hand, _ = stock.balance(db, ol["item_id"])
        reserved = _reserved(db, ol["item_id"], order_id)
        available = on_hand - reserved
        shortage = max(0, ol["qty_milli"] - available)
        batches = 0
        if shortage:
            bom = db.execute("SELECT yield_milli FROM boms WHERE product_id=?", (ol["item_id"],)).fetchone()
            if bom:
                batches = -(-shortage // bom["yield_milli"])
        out.append({**dict(ol), "on_hand": on_hand, "reserved": reserved, "available": available,
                    "shortage": shortage, "batches_needed": batches})
    return out


def edit_order(db, user, order_id, changes):
    """Admin edits quantity/price before approval. changes = {line_id: (qty_milli, price_paise)}. Audited."""
    o = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if o["status"] != "submitted":
        raise ServiceError("Only submitted orders can be edited")
    before = [dict(r) for r in db.execute("SELECT id,qty_milli,price_paise FROM order_lines WHERE order_id=?", (order_id,))]
    for lid, (q, price) in changes.items():
        if q <= 0 or price < 0:
            raise ServiceError("Invalid quantity or price")
        db.execute("UPDATE order_lines SET qty_milli=?, price_paise=? WHERE id=? AND order_id=?", (q, price, lid, order_id))
    db.execute("UPDATE orders SET updated_at=? WHERE id=?", (NOW(), order_id))
    audit.log(db, user, "order", order_id, "edit", {"before": before, "after": {str(k): v for k, v in changes.items()}})


def approve_order(db, user, order_id, allow_shortage=False, allow_credit_breach=True):
    o = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if o["status"] != "submitted":
        raise ServiceError("Only submitted orders can be approved")
    short = [c for c in stock_check(db, order_id) if c["shortage"]]
    if short and not allow_shortage:
        raise ServiceError("Stock does not cover this order: " + "; ".join(
            f"{c['name']} short by {fmt_qty(c['shortage'])}" for c in short) +
            ". Reduce the quantity, or tick 'approve despite shortage' to back-order it.")

    # Optional Credit Limit verification
    cust = db.execute("SELECT * FROM customers WHERE id=?", (o["customer_id"],)).fetchone()
    if cust and cust["credit_limit_paise"] > 0 and not allow_credit_breach:
        recs, _ = receivables(db)
        out_bal = sum(r["outstanding"] for r in recs if r["invoice"]["customer_id"] == o["customer_id"])
        tot_order = order_total_paise(db, order_id)
        if out_bal + tot_order > cust["credit_limit_paise"]:
            raise ServiceError(f"Credit limit exceeded: Outstanding Rs {out_bal/100:.2f} + Order Rs {tot_order/100:.2f} exceeds limit Rs {cust['credit_limit_paise']/100:.2f}")

    db.execute("UPDATE orders SET status='approved', updated_at=? WHERE id=?", (NOW(), order_id))
    audit.log(db, user, "order", order_id, "approve", {"shortage": [c["shortage"] for c in short]})


def reject_order(db, user, order_id, reason):
    o = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if o["status"] not in ("submitted", "approved"):
        raise ServiceError("This order can no longer be rejected")
    db.execute("UPDATE orders SET status='rejected', reject_reason=?, updated_at=? WHERE id=?", (reason, NOW(), order_id))
    audit.log(db, user, "order", order_id, "reject", {"reason": reason})


def cancel_order(db, user, order_id, reason=""):
    o = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not o or o["status"] in ("dispatched", "cancelled"):
        raise ServiceError("This order cannot be cancelled")
    db.execute("UPDATE orders SET status='cancelled', cancel_reason=?, cancelled_at=?, updated_at=? WHERE id=?",
               (reason, NOW(), NOW(), order_id))
    audit.log(db, user, "order", order_id, "cancel", {"reason": reason})


# ---------------------------------------------------------------- GST
def compute_line_tax(taxable_paise: int, gst_bp: int, intra: bool):
    """Tax is computed per line on the taxable value, rounded half-up to the paisa.
    Intra-state: CGST and SGST are each half the rate. Inter-state: IGST at the full rate."""
    if intra:
        half = round_half_up(D(taxable_paise) * gst_bp / 20000)
        return half, half, 0
    return 0, 0, round_half_up(D(taxable_paise) * gst_bp / 10000)


def create_invoice(db, user, order_id, date=None):
    date = date or today()
    o = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if o["status"] != "approved":
        raise ServiceError("Only an approved order can be invoiced")
    cust = db.execute("SELECT * FROM customers WHERE id=?", (o["customer_id"],)).fetchone()
    intra = cust["state_code"] == setting(db, "factory_state_code")
    fy = fy_of(date)
    n = next_seq(db, f"INV-{fy}")
    inv_no = f"INV/{fy}/{n:04d}"
    lines, tot = [], [0, 0, 0, 0, 0]
    for ol in db.execute("SELECT ol.*, i.name, i.hsn, i.gst_bp FROM order_lines ol JOIN items i ON i.id=ol.item_id "
                         "WHERE ol.order_id=?", (order_id,)).fetchall():
        taxable = round_half_up(D(ol["qty_milli"]) * ol["price_paise"] / 1000)
        cg, sg, ig = compute_line_tax(taxable, ol["gst_bp"], intra)
        lines.append((ol, taxable, cg, sg, ig))
        for k, v in enumerate((taxable, cg, sg, ig, taxable + cg + sg + ig)):
            tot[k] += v
    cur = db.execute(
        "INSERT INTO invoices(invoice_no,fy,date,order_id,customer_id,place_of_supply,supply_type,taxable_paise,cgst_paise,"
        "sgst_paise,igst_paise,total_paise,status,created_by,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'posted',?,?)",
        (inv_no, fy, date, order_id, o["customer_id"], f"{cust['state_code']}-{cust['state_name']}",
         "intra" if intra else "inter", *tot, user["id"], NOW()))
    iid = cur.lastrowid
    for ol, taxable, cg, sg, ig in lines:
        db.execute("INSERT INTO invoice_lines(invoice_id,item_id,description,hsn,qty_milli,rate_paise,taxable_paise,gst_bp,"
                   "cgst_paise,sgst_paise,igst_paise,total_paise) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                   (iid, ol["item_id"], ol["name"], ol["hsn"], ol["qty_milli"], ol["price_paise"], taxable, ol["gst_bp"],
                    cg, sg, ig, taxable + cg + sg + ig))
    db.execute("UPDATE orders SET status='invoiced', updated_at=? WHERE id=?", (NOW(), order_id))
    audit.log(db, user, "invoice", iid, "create", {"invoice_no": inv_no, "total_paise": tot[4], "supply": "intra" if intra else "inter"})
    return iid


def dispatch(db, user, invoice_id, date=None):
    """Dispatch reduces finished-goods stock. Fails (and posts nothing) if stock is short or QA blocked."""
    date = date or today()
    inv = db.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
    if inv["status"] != "posted":
        raise ServiceError("Cancelled invoices cannot be dispatched")
    if inv["dispatched_on"]:
        raise ServiceError("Already dispatched")
    lines = db.execute("SELECT * FROM invoice_lines WHERE invoice_id=?", (invoice_id,)).fetchall()
    for ln in lines:
        from . import quality
        ok, reason = quality.is_batch_dispatchable(db, ln["item_id"])
        if not ok:
            raise ServiceError(f"Dispatch blocked by Quality Control: {reason}")
    for ln in lines:
        stock.post(db, item_id=ln["item_id"], qty_milli=-ln["qty_milli"], move_type="dispatch", source_type="invoice",
                   source_id=invoice_id, user=user, date=date)
    db.execute("UPDATE invoices SET dispatched_on=? WHERE id=?", (date, invoice_id))
    db.execute("UPDATE orders SET status='dispatched', updated_at=? WHERE id=?", (NOW(), inv["order_id"]))
    audit.log(db, user, "invoice", invoice_id, "dispatch", {"date": date})


def cancel_invoice(db, user, invoice_id, reason, date=None):
    """Posted invoices are never deleted: a credit note reverses them (and returns stock if dispatched)."""
    date = date or today()
    if not reason or not reason.strip():
        raise ServiceError("A reason is required")
    inv = db.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
    if inv["status"] != "posted":
        raise ServiceError("Invoice already cancelled")
    n = next_seq(db, f"CN-{fy_of(date)}")
    cur = db.execute(
        "INSERT INTO credit_notes(note_no,invoice_id,date,reason,taxable_paise,cgst_paise,sgst_paise,igst_paise,total_paise,created_by)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (f"CN/{fy_of(date)}/{n:04d}", invoice_id, date, reason, inv["taxable_paise"], inv["cgst_paise"], inv["sgst_paise"],
         inv["igst_paise"], inv["total_paise"], user["id"]))
    cn_id = cur.lastrowid
    if inv["dispatched_on"]:   # bring the goods back at the value they left at
        for r in db.execute("SELECT item_id, SUM(qty_milli) q, SUM(value_paise) v FROM stock_ledger "
                            "WHERE source_type='invoice' AND source_id=? AND move_type='dispatch' GROUP BY item_id", (invoice_id,)):
            stock.post(db, item_id=r["item_id"], qty_milli=-r["q"], value_paise=-r["v"], move_type="sales_return",
                       source_type="credit_note", source_id=cn_id, user=user, date=date, note=f"Credit note for {inv['invoice_no']}")
    db.execute("UPDATE invoices SET status='cancelled' WHERE id=?", (invoice_id,))
    if inv["order_id"]:
        db.execute("UPDATE orders SET status='approved', updated_at=? WHERE id=?", (NOW(), inv["order_id"]))
    audit.log(db, user, "invoice", invoice_id, "cancel", {"credit_note_id": cn_id, "reason": reason})
    return cn_id


# ---------------------------------------------------------------- payments
def record_payment(db, user, customer_id, amount_paise, date=None, mode="", reference="", invoice_id=None):
    date = date or today()
    if amount_paise <= 0:
        raise ServiceError("Payment must be positive")
    if invoice_id:
        inv = db.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
        if not inv or inv["customer_id"] != customer_id or inv["status"] != "posted":
            raise ServiceError("Choose a posted invoice of this customer")
    cur = db.execute("INSERT INTO payments(customer_id,invoice_id,date,amount_paise,mode,reference,created_by) VALUES (?,?,?,?,?,?,?)",
                     (customer_id, invoice_id, date, amount_paise, mode, reference, user["id"]))
    audit.log(db, user, "payment", cur.lastrowid, "create", {"amount_paise": amount_paise, "invoice_id": invoice_id})
    return cur.lastrowid


def receivables(db, as_of=None):
    """Outstanding per posted invoice. Payments tagged to an invoice reduce it directly; untagged payments
    (or ones tagged to a since-cancelled invoice) are applied oldest-invoice-first (FIFO)."""
    as_of = as_of or today()
    invoices = db.execute("SELECT i.*, c.name customer FROM invoices i JOIN customers c ON c.id=i.customer_id "
                          "WHERE i.status='posted' AND i.date<=? ORDER BY i.date, i.id", (as_of,)).fetchall()
    rows = {i["id"]: {"invoice": dict(i), "paid": 0} for i in invoices}
    pool = {}
    for p in db.execute("SELECT p.*, i.status inv_status FROM payments p LEFT JOIN invoices i ON i.id=p.invoice_id "
                        "WHERE p.date<=?", (as_of,)):
        if p["invoice_id"] and p["inv_status"] == "posted" and p["invoice_id"] in rows:
            rows[p["invoice_id"]]["paid"] += p["amount_paise"]
        else:
            pool[p["customer_id"]] = pool.get(p["customer_id"], 0) + p["amount_paise"]
    asof = dt.date.fromisoformat(as_of)
    out = []
    for r in rows.values():
        inv = r["invoice"]
        due = inv["total_paise"] - r["paid"]
        if due > 0 and pool.get(inv["customer_id"], 0) > 0:
            use = min(due, pool[inv["customer_id"]])
            r["paid"] += use
            pool[inv["customer_id"]] -= use
        r["outstanding"] = inv["total_paise"] - r["paid"]
        r["age_days"] = (asof - dt.date.fromisoformat(inv["date"])).days
        out.append(r)
    advances = {cid: v for cid, v in pool.items() if v > 0}
    return out, advances
