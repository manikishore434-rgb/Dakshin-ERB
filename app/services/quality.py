"""Quality Management Module (QA/QC).

Inspects incoming raw materials, in-process production, and finished goods batches.
Enforces dispatch blocking for rejected or quarantined batches.
"""
import datetime as dt
import json

from .. import audit
from ..db import next_seq
from ..util import ServiceError, today

NOW = lambda: dt.datetime.now().isoformat(timespec="seconds")


def list_inspections(db, status=None, insp_type=None):
    sql = """SELECT qi.*, i.name item_name, i.code item_code, i.base_unit, u.full_name inspector_name
             FROM quality_inspections qi
             JOIN items i ON i.id=qi.item_id
             LEFT JOIN users u ON u.id=qi.inspected_by
             WHERE 1=1"""
    args = []
    if status:
        sql += " AND qi.status=?"
        args.append(status)
    if insp_type:
        sql += " AND qi.inspection_type=?"
        args.append(insp_type)
    sql += " ORDER BY qi.id DESC"
    return [dict(r) for r in db.execute(sql, args)]


def get_inspection(db, inspection_id):
    r = db.execute(
        """SELECT qi.*, i.name item_name, i.code item_code, i.base_unit, u.full_name inspector_name
           FROM quality_inspections qi
           JOIN items i ON i.id=qi.item_id
           LEFT JOIN users u ON u.id=qi.inspected_by
           WHERE qi.id=?""",
        (inspection_id,),
    ).fetchone()
    return dict(r) if r else None


def create_inspection(db, user, inspection_type, item_id, reference_type, reference_id,
                      batch_no="", sample_size="", parameters=None, notes=""):
    """Creates a new quality inspection in pending status."""
    if inspection_type not in ("incoming_rm", "in_process", "finished_goods"):
        raise ServiceError("Invalid inspection type")
    item = db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    if not item:
        raise ServiceError("Item not found")

    n = next_seq(db, "QC")
    insp_no = f"QC-{n:05d}"
    params_json = json.dumps(parameters or {})

    cur = db.execute(
        "INSERT INTO quality_inspections(inspection_no, inspection_type, status, item_id, batch_no, "
        "reference_type, reference_id, inspected_by, inspected_at, sample_size, parameters_json, notes) "
        "VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (insp_no, inspection_type, item_id, batch_no, reference_type, reference_id,
         user["id"] if user else None, NOW(), sample_size, params_json, notes),
    )
    insp_id = cur.lastrowid

    # If it's a production run, tie the inspection id to it
    if reference_type == "production_run":
        db.execute(
            "UPDATE production_runs SET quality_inspection_id=?, quality_status='pending' WHERE id=?",
            (insp_id, reference_id),
        )

    audit.log(db, user, "quality_inspection", insp_id, "create", {"inspection_no": insp_no, "type": inspection_type})
    return insp_id


def record_verdict(db, user, inspection_id, status, defect_category="", defect_description="", corrective_action="", notes=""):
    """Records the final quality verdict: approved, rejected, or quarantine."""
    if status not in ("approved", "rejected", "quarantine", "pending"):
        raise ServiceError("Invalid quality status")

    qi = db.execute("SELECT * FROM quality_inspections WHERE id=?", (inspection_id,)).fetchone()
    if not qi:
        raise ServiceError("Inspection not found")

    db.execute(
        "UPDATE quality_inspections SET status=?, defect_category=?, defect_description=?, "
        "corrective_action=?, notes=notes || ' | ' || ?, inspected_by=?, inspected_at=? WHERE id=?",
        (status, defect_category, defect_description, corrective_action, notes, user["id"] if user else None, NOW(), inspection_id),
    )

    # Sync back to reference entity
    if qi["reference_type"] == "production_run":
        db.execute(
            "UPDATE production_runs SET quality_status=? WHERE id=?",
            (status, qi["reference_id"]),
        )
    elif qi["reference_type"] == "purchase":
        # Tag quality status on stock ledger entries
        db.execute(
            "UPDATE stock_ledger SET quality_status=? WHERE source_type='purchase' AND source_id=?",
            (status, qi["reference_id"]),
        )

    audit.log(db, user, "quality_inspection", inspection_id, "verdict", {"status": status, "defect": defect_category})


def is_batch_dispatchable(db, item_id, batch_no=None):
    """Checks whether finished product or batch has cleared QA inspection.
    Returns (dispatchable: bool, reason: str)."""
    # If no batch number is provided, check overall recent inspections
    query = "SELECT * FROM quality_inspections WHERE item_id=?"
    args = [item_id]
    if batch_no:
        query += " AND batch_no=?"
        args.append(batch_no)
    query += " ORDER BY id DESC LIMIT 1"

    qi = db.execute(query, args).fetchone()
    if qi:
        if qi["status"] == "rejected":
            return False, f"Batch {qi['batch_no'] or ''} has been REJECTED by QA ({qi['defect_category'] or 'Quality defect'}). Dispatch blocked!"
        if qi["status"] == "quarantine":
            return False, f"Batch {qi['batch_no'] or ''} is in QUARANTINE hold. Dispatch blocked until released!"

    # Check production run status directly
    if batch_no:
        run = db.execute("SELECT * FROM production_runs WHERE batch_no=?", (batch_no,)).fetchone()
        if run and run["quality_status"] in ("rejected", "quarantine"):
            return False, f"Production Batch {batch_no} is {run['quality_status'].upper()} by Quality Control. Dispatch blocked!"

    return True, "Batch is approved for dispatch"


def quality_summary(db):
    """Aggregates quality statistics for dashboards and reports."""
    total = db.execute("SELECT COUNT(*) n FROM quality_inspections").fetchone()["n"]
    approved = db.execute("SELECT COUNT(*) n FROM quality_inspections WHERE status='approved'").fetchone()["n"]
    rejected = db.execute("SELECT COUNT(*) n FROM quality_inspections WHERE status='rejected'").fetchone()["n"]
    quarantine = db.execute("SELECT COUNT(*) n FROM quality_inspections WHERE status='quarantine'").fetchone()["n"]
    pending = db.execute("SELECT COUNT(*) n FROM quality_inspections WHERE status='pending'").fetchone()["n"]

    pass_rate = round((approved / total * 100), 1) if total > 0 else 100.0

    defects = db.execute(
        """SELECT defect_category, COUNT(*) count
           FROM quality_inspections
           WHERE defect_category IS NOT NULL AND defect_category != ''
           GROUP BY defect_category ORDER BY count DESC"""
    ).fetchall()

    return {
        "total": total,
        "approved": approved,
        "rejected": rejected,
        "quarantine": quarantine,
        "pending": pending,
        "pass_rate_pct": pass_rate,
        "defects": [dict(d) for d in defects],
    }
