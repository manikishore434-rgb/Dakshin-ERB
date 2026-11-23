"""Small non-HTTP helpers shared by the views and the benchmark (purchase posting)."""
import datetime as dt

from . import audit
from .db import next_seq
from .services import stock
from .units import to_base_milli
from .util import D, ServiceError, round_half_up, today


def record_purchase(db, user, supplier_id, date, supplier_invoice_no, lines):
    """lines = [(item_id, qty, unit, rate_per_base_unit_in_rupees[, batch_no, expiry])].
    Receipt value = qty x rate (rounded once per line); stock goes up with that value."""
    date = date or today()
    if not lines:
        raise ServiceError("Add at least one line")
    n = next_seq(db, "PUR")
    cur = db.execute("INSERT INTO purchases(purchase_no,supplier_id,date,supplier_invoice_no,created_by,created_at) VALUES (?,?,?,?,?,?)",
                     (f"PUR-{n:04d}", supplier_id, date, supplier_invoice_no, user["id"], dt.datetime.now().isoformat(timespec="seconds")))
    pid = cur.lastrowid
    for ln in lines:
        item_id, q, unit, rate = ln[:4]
        batch, expiry = (ln[4], ln[5]) if len(ln) > 5 else (None, None)
        item = db.execute("SELECT * FROM items WHERE id=? AND kind IN ('raw','packaging')", (item_id,)).fetchone()
        if not item:
            raise ServiceError("Unknown raw-material / packaging item")
        qm = to_base_milli(q, unit, item)
        if qm <= 0 or D(rate) < 0:
            raise ServiceError("Quantity must be positive and rate cannot be negative")
        amount = round_half_up(D(qm) * D(rate) * 100 / 1000)
        db.execute("INSERT INTO purchase_lines(purchase_id,item_id,qty_milli,rate,amount_paise,batch_no,expiry) VALUES (?,?,?,?,?,?,?)",
                   (pid, item_id, qm, str(rate), amount, batch, expiry))
        stock.post(db, item_id=item_id, qty_milli=qm, value_paise=amount, move_type="purchase", source_type="purchase",
                   source_id=pid, user=user, date=date, batch_no=batch, expiry=expiry)
    audit.log(db, user, "purchase", pid, "create", {"lines": len(lines)})
    return pid
