"""Ledger-based stock. Every movement is a row in stock_ledger tied to a source document.

Valuation: perpetual WEIGHTED AVERAGE. A receipt carries its own value; an issue is valued at
(current value / current qty) * qty issued, so the ledger value always reconciles with the quantity.
"""
import datetime as dt

from ..util import D, ServiceError, round_half_up, qty as fmt_qty

RECEIPT_TYPES = ("opening", "purchase", "production_output", "sales_return")
ISSUE_TYPES = ("production_issue", "dispatch")
ADJ_TYPES = ("adjustment", "reversal")


class InsufficientStock(ServiceError):
    def __init__(self, item_name, needed_milli, available_milli, unit=""):
        self.item_name, self.needed, self.available = item_name, needed_milli, available_milli
        self.shortage = needed_milli - available_milli
        super().__init__(f"Insufficient stock of {item_name}: need {fmt_qty(needed_milli)} {unit}, "
                         f"available {fmt_qty(available_milli)} {unit} (short by {fmt_qty(self.shortage)})")


def balance(db, item_id, upto=None):
    sql = "SELECT COALESCE(SUM(qty_milli),0) q, COALESCE(SUM(value_paise),0) v FROM stock_ledger WHERE item_id=?"
    args = [item_id]
    if upto:
        sql += " AND date<=?"
        args.append(upto)
    r = db.execute(sql, args).fetchone()
    return r["q"], r["v"]


def post(db, *, item_id, qty_milli, move_type, source_type, source_id, user, date, value_paise=None,
         batch_no=None, expiry=None, note=None):
    """Append one movement. Returns (qty_milli, value_paise) as stored."""
    if qty_milli == 0:
        return 0, 0
    item = db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    bal_q, bal_v = balance(db, item_id)
    if qty_milli < 0:
        if bal_q + qty_milli < 0:
            raise InsufficientStock(item["name"], -qty_milli, bal_q, item["base_unit"])
        if value_paise is None:
            # weighted-average cost of what leaves; exact when the last unit leaves
            value_paise = -bal_v if -qty_milli == bal_q else -round_half_up(D(bal_v) * (-qty_milli) / D(bal_q))
    elif value_paise is None:
        value_paise = round_half_up(D(bal_v) * qty_milli / D(bal_q)) if bal_q > 0 else 0
    db.execute(
        "INSERT INTO stock_ledger(date,ts,item_id,qty_milli,value_paise,move_type,source_type,source_id,batch_no,expiry,note,user_id)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (date, dt.datetime.now().isoformat(timespec="seconds"), item_id, qty_milli, value_paise, move_type,
         source_type, source_id, batch_no, expiry, note, user["id"] if user else None))
    return qty_milli, value_paise


def adjust(db, user, item_id, qty_milli, reason, date):
    """Manual stock adjustment (damage, count correction). Reason is mandatory and audited."""
    from .. import audit
    if not reason or not reason.strip():
        raise ServiceError("A reason is required for a stock adjustment")
    post(db, item_id=item_id, qty_milli=qty_milli, move_type="adjustment", source_type="adjustment",
         source_id=None, user=user, date=date, note=reason.strip())
    audit.log(db, user, "stock", item_id, "adjustment", {"qty_milli": qty_milli, "reason": reason})


def wac_rate_paise(db, item_id):
    """Current weighted-average rate in paise per base unit (Decimal) or None."""
    q, v = balance(db, item_id)
    return D(v) * 1000 / D(q) if q > 0 else None
