"""BOM-driven production: runs, planned-vs-actual consumption, yield variance and costing."""
import datetime as dt
import math
from decimal import Decimal

from .. import audit
from ..db import next_seq, setting
from ..util import D, ServiceError, beyond_tolerance, pct, round_half_up, today
from . import stock


def tolerance_bp(db) -> int:
    return int(setting(db, "variance_tolerance_bp", "300"))


def get_bom(db, product_id):
    bom = db.execute("SELECT * FROM boms WHERE product_id=?", (product_id,)).fetchone()
    if not bom:
        raise ServiceError("No BOM defined for this product")
    lines = db.execute(
        "SELECT bl.item_id, bl.qty_milli, i.name, i.kind, i.base_unit FROM bom_lines bl "
        "JOIN items i ON i.id=bl.item_id WHERE bl.bom_id=? ORDER BY i.kind DESC, i.name", (bom["id"],)).fetchall()
    return bom, lines


def start_run(db, user, product_id, batches, issues, date=None, notes=""):
    """Create a run and issue raw materials. issues = {item_id: qty_milli actually issued}."""
    date = date or today()
    bom, lines = get_bom(db, product_id)
    product = db.execute("SELECT * FROM items WHERE id=?", (product_id,)).fetchone()
    batches_milli = round_half_up(D(batches) * 1000)
    if batches_milli <= 0:
        raise ServiceError("Number of batches must be positive")
    expected = round_half_up(D(bom["yield_milli"]) * batches_milli / 1000)
    n = next_seq(db, "RUN")
    run_no = f"RUN-{n:04d}"
    expiry = None
    if product["shelf_life_days"]:
        expiry = (dt.date.fromisoformat(date) + dt.timedelta(days=product["shelf_life_days"])).isoformat()
    cur = db.execute(
        "INSERT INTO production_runs(run_no,product_id,date,batches_milli,expected_milli,status,batch_no,expiry,notes,created_by,created_at)"
        " VALUES (?,?,?,?,?,'open',?,?,?,?,?)",
        (run_no, product_id, date, batches_milli, expected, f"{product['code']}-{date.replace('-', '')}-{n:02d}", expiry,
         notes, user["id"], dt.datetime.now().isoformat(timespec="seconds")))
    run_id = cur.lastrowid
    for bl in lines:
        planned = round_half_up(D(bl["qty_milli"]) * batches_milli / 1000)
        db.execute("INSERT INTO run_lines(run_id,item_id,planned_milli) VALUES (?,?,?)", (run_id, bl["item_id"], planned))
    audit.log(db, user, "production_run", run_id, "start", {"run_no": run_no, "batches_milli": batches_milli})
    issue_materials(db, user, run_id, issues, date)
    return run_id


def issue_materials(db, user, run_id, issues, date=None):
    """Issue raw materials to an open run (stock goes down, valued at weighted average)."""
    date = date or today()
    run = db.execute("SELECT * FROM production_runs WHERE id=?", (run_id,)).fetchone()
    if not run or run["status"] != "open":
        raise ServiceError("Materials can only be issued to an open run")
    for item_id, q in issues.items():
        if q <= 0:
            continue
        rl = db.execute("SELECT * FROM run_lines WHERE run_id=? AND item_id=?", (run_id, item_id)).fetchone()
        if not rl:
            raise ServiceError("Item is not part of this product's BOM")
        _, v = stock.post(db, item_id=item_id, qty_milli=-q, move_type="production_issue", source_type="production_run",
                          source_id=run_id, user=user, date=date, batch_no=run["batch_no"])
        db.execute("UPDATE run_lines SET actual_milli=actual_milli+?, actual_value_paise=actual_value_paise+? WHERE id=?",
                   (q, -v, rl["id"]))
    audit.log(db, user, "production_run", run_id, "issue", {str(k): v for k, v in issues.items()})


def complete_run(db, user, run_id, good_milli, damaged_milli=0, packaging=None, date=None):
    """Record actual output. Packaging consumption defaults: per_packet items = good+damaged,
    per_carton items = ceil(good / carton_size). Finished goods stock goes up automatically."""
    date = date or today()
    packaging = packaging or {}
    run = db.execute("SELECT * FROM production_runs WHERE id=?", (run_id,)).fetchone()
    if not run or run["status"] != "open":
        raise ServiceError("Only an open run can be completed")
    if good_milli < 0 or damaged_milli < 0:
        raise ServiceError("Quantities cannot be negative")
    product = db.execute("SELECT * FROM items WHERE id=?", (run["product_id"],)).fetchone()
    rows = db.execute("SELECT rl.*, i.kind, i.pack_role FROM run_lines rl JOIN items i ON i.id=rl.item_id "
                      "WHERE rl.run_id=?", (run_id,)).fetchall()
    for rl in rows:
        if rl["kind"] != "packaging":
            continue
        if rl["item_id"] in packaging and packaging[rl["item_id"]] is not None:
            q = packaging[rl["item_id"]]
        elif rl["pack_role"] == "per_packet":
            q = good_milli + damaged_milli
        elif rl["pack_role"] == "per_carton" and product["carton_size"]:
            q = math.ceil(good_milli / 1000 / product["carton_size"]) * 1000
        else:
            q = rl["planned_milli"]
        if q > 0:
            _, v = stock.post(db, item_id=rl["item_id"], qty_milli=-q, move_type="production_issue",
                              source_type="production_run", source_id=run_id, user=user, date=date,
                              batch_no=run["batch_no"])
            db.execute("UPDATE run_lines SET actual_milli=actual_milli+?, actual_value_paise=actual_value_paise+? WHERE id=?",
                       (q, -v, rl["id"]))
    material_value = db.execute("SELECT COALESCE(SUM(actual_value_paise),0) s FROM run_lines WHERE run_id=?",
                                (run_id,)).fetchone()["s"]
    stock.post(db, item_id=run["product_id"], qty_milli=good_milli, move_type="production_output",
               source_type="production_run", source_id=run_id, user=user, date=date,
               value_paise=material_value, batch_no=run["batch_no"], expiry=run["expiry"])
    db.execute("UPDATE production_runs SET actual_milli=?, damaged_milli=?, status='completed' WHERE id=?",
               (good_milli, damaged_milli, run_id))
    audit.log(db, user, "production_run", run_id, "complete",
              {"good_milli": good_milli, "damaged_milli": damaged_milli, "material_value_paise": material_value})


def cancel_run(db, user, run_id, reason):
    """Cancel a run by posting reversing ledger rows (history is kept, nothing is deleted)."""
    if not reason or not reason.strip():
        raise ServiceError("A reason is required to cancel a run")
    run = db.execute("SELECT * FROM production_runs WHERE id=?", (run_id,)).fetchone()
    if not run or run["status"] == "cancelled":
        raise ServiceError("Run not found or already cancelled")
    rows = db.execute("SELECT * FROM stock_ledger WHERE source_type='production_run' AND source_id=? "
                      "AND move_type IN ('production_issue','production_output')", (run_id,)).fetchall()
    # reverse outputs first so a dispatched batch blocks the cancellation with a clear message
    for r in sorted(rows, key=lambda r: r["qty_milli"] < 0):
        stock.post(db, item_id=r["item_id"], qty_milli=-r["qty_milli"], value_paise=-r["value_paise"],
                   move_type="reversal", source_type="production_run", source_id=run_id, user=user,
                   date=today(), batch_no=r["batch_no"], note=f"Cancel {run['run_no']}: {reason}")
    db.execute("UPDATE production_runs SET status='cancelled' WHERE id=?", (run_id,))
    audit.log(db, user, "production_run", run_id, "cancel", {"reason": reason})


def add_overhead(db, user, run_id, kind, amount_paise, note="", date=None):
    """run_id=None puts the amount in the monthly pool, which is allocated to runs by good packets."""
    date = date or today()
    if amount_paise <= 0:
        raise ServiceError("Overhead amount must be positive")
    if run_id is not None and not db.execute("SELECT 1 FROM production_runs WHERE id=?", (run_id,)).fetchone():
        raise ServiceError("Run not found")
    cur = db.execute("INSERT INTO run_overheads(run_id,month,kind,amount_paise,note,date,created_by) VALUES (?,?,?,?,?,?,?)",
                     (run_id, date[:7], kind, amount_paise, note, date, user["id"]))
    audit.log(db, user, "run_overhead", cur.lastrowid,
              "add", {"run_id": run_id, "kind": kind, "amount_paise": amount_paise})


def run_summary(db, run_id):
    """Everything about one run: planned vs actual, variance flags, and cost per packet."""
    run = db.execute("SELECT r.*, i.name product_name, i.price_paise FROM production_runs r "
                     "JOIN items i ON i.id=r.product_id WHERE r.id=?", (run_id,)).fetchone()
    tol = tolerance_bp(db)
    lines = []
    for rl in db.execute("SELECT rl.*, i.name, i.kind, i.base_unit FROM run_lines rl JOIN items i ON i.id=rl.item_id "
                         "WHERE rl.run_id=? ORDER BY i.kind DESC, i.name", (run_id,)).fetchall():
        lines.append({**dict(rl), "var_pct": pct(rl["planned_milli"], rl["actual_milli"]),
                      "flag": run["status"] != "open" and beyond_tolerance(rl["planned_milli"], rl["actual_milli"], tol)})
    done = run["status"] == "completed"
    yield_flag = done and beyond_tolerance(run["expected_milli"], run["actual_milli"], tol)
    material = sum(l["actual_value_paise"] for l in lines)
    direct = db.execute("SELECT COALESCE(SUM(amount_paise),0) s FROM run_overheads WHERE run_id=?", (run_id,)).fetchone()["s"]
    allocated = 0
    if done:
        pool = db.execute("SELECT COALESCE(SUM(amount_paise),0) s FROM run_overheads WHERE run_id IS NULL AND month=?",
                          (run["date"][:7],)).fetchone()["s"]
        month_good = db.execute("SELECT COALESCE(SUM(actual_milli),0) s FROM production_runs WHERE status='completed' AND date LIKE ?",
                                (run["date"][:7] + "%",)).fetchone()["s"]
        if pool and month_good:
            allocated = round_half_up(D(pool) * run["actual_milli"] / D(month_good))
    overhead = direct + allocated
    total = material + overhead
    good_packets = D(run["actual_milli"]) / 1000
    cpp = round_half_up(D(total) / good_packets) if done and good_packets > 0 else None   # paise per good packet
    return {
        "run": dict(run), "lines": lines, "tolerance_bp": tol, "done": done,
        "yield_var_pct": pct(run["expected_milli"], run["actual_milli"]) if done else None, "yield_flag": yield_flag,
        "material_paise": material, "direct_overhead_paise": direct, "allocated_overhead_paise": allocated,
        "total_cost_paise": total, "cost_per_packet_paise": cpp,
        "margin_per_packet_paise": (run["price_paise"] - cpp) if cpp is not None and run["price_paise"] else None,
        "margin_pct": ((D(run["price_paise"] - cpp) * 100 / D(run["price_paise"])).quantize(Decimal("0.1"))
                       if cpp is not None and run["price_paise"] else None),
        "any_flag": yield_flag or any(l["flag"] for l in lines),
    }
