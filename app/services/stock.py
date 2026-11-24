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


def fefo_batches(db, item_id):
    """Returns batches of an item with remaining stock sorted First-Expired-First-Out (FEFO)."""
    rows = db.execute(
        """SELECT batch_no, expiry, COALESCE(SUM(qty_milli), 0) remaining_milli,
                  COALESCE(SUM(value_paise), 0) val_paise
           FROM stock_ledger
           WHERE item_id=? AND batch_no IS NOT NULL AND batch_no != ''
           GROUP BY batch_no, expiry
           HAVING remaining_milli > 0
           ORDER BY CASE WHEN expiry IS NULL OR expiry = '' THEN '9999-12-31' ELSE expiry END ASC, date ASC""",
        (item_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def stock_analytics(db, as_of=None):
    """Identifies critical inventory, overstock, expiring materials, and valuation breakdown."""
    items = db.execute("SELECT * FROM items WHERE active=1 ORDER BY kind DESC, name").fetchall()
    critical = []
    overstock = []
    total_val = 0
    by_kind = {"raw": 0, "packaging": 0, "finished": 0}

    for item in items:
        q, v = balance(db, item["id"], upto=as_of)
        total_val += v
        by_kind[item["kind"]] = by_kind.get(item["kind"], 0) + v

        rop = item["reorder_level_milli"] or 0
        safety = item["safety_stock_milli"] or 0
        max_lvl = item["max_stock_milli"] or 0

        if rop > 0 and q <= rop:
            critical.append({**dict(item), "qty_milli": q, "val_paise": v, "is_safety": safety > 0 and q <= safety})
        if max_lvl > 0 and q > max_lvl:
            overstock.append({**dict(item), "qty_milli": q, "val_paise": v, "excess_milli": q - max_lvl})

    # Expiring lots in next 60 days
    now_date = as_of or dt.date.today().isoformat()
    horizon = (dt.date.fromisoformat(now_date) + dt.timedelta(days=60)).isoformat()
    expiring = db.execute(
        """SELECT l.item_id, i.name item_name, i.kind, i.base_unit, l.batch_no, l.expiry,
                  COALESCE(SUM(l.qty_milli), 0) remaining_milli
           FROM stock_ledger l
           JOIN items i ON i.id=l.item_id
           WHERE l.expiry IS NOT NULL AND l.expiry != '' AND l.expiry <= ?
           GROUP BY l.item_id, l.batch_no, l.expiry
           HAVING remaining_milli > 0
           ORDER BY l.expiry ASC""",
        (horizon,),
    ).fetchall()

    return {
        "total_valuation_paise": total_val,
        "valuation_by_kind": by_kind,
        "critical_items": critical,
        "overstock_items": overstock,
        "expiring_batches": [dict(e) for e in expiring],
    }
