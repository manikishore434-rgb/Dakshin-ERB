"""End-to-End Batch Traceability Service.

Traces full supply chain backwards and forwards:
RAW MATERIAL / SUPPLIER -> PRODUCTION RUN -> QUALITY INSPECTION -> FINISHED GOODS -> INVOICE -> CUSTOMER
"""
from ..util import money, qty


def trace_batch(db, query_str):
    """Searches for batch or lot numbers in production runs, purchases, or ledger.
    Returns a structured traceability graph."""
    q = (query_str or "").strip()
    if not q:
        return None

    # Check if matches a production run batch
    run = db.execute(
        """SELECT r.*, i.name product_name, i.code product_code, i.base_unit, u.full_name supervisor
           FROM production_runs r
           JOIN items i ON i.id=r.product_id
           LEFT JOIN users u ON u.id=r.created_by
           WHERE r.batch_no=? OR r.run_no=?""",
        (q, q),
    ).fetchone()

    # If not matched directly, check if it's a purchase batch/lot
    purchase_lot = None
    if not run:
        purchase_lot = db.execute(
            """SELECT pl.*, p.purchase_no, p.date purchase_date, p.grn_no, p.supplier_invoice_no,
                      s.name supplier_name, s.gstin supplier_gstin, s.phone supplier_phone,
                      i.name item_name, i.code item_code, i.base_unit
               FROM purchase_lines pl
               JOIN purchases p ON p.id=pl.purchase_id
               JOIN items i ON i.id=pl.item_id
               LEFT JOIN suppliers s ON s.id=p.supplier_id
               WHERE pl.batch_no=? OR p.purchase_no=? OR p.grn_no=?""",
            (q, q, q),
        ).fetchone()

    if not run and not purchase_lot:
        # Fuzzy match batch_no in stock_ledger
        leg = db.execute("SELECT * FROM stock_ledger WHERE batch_no LIKE ? LIMIT 1", (f"%{q}%",)).fetchone()
        if leg and leg["source_type"] == "production_run":
            run = db.execute("SELECT r.*, i.name product_name, i.code product_code, i.base_unit, u.full_name supervisor FROM production_runs r JOIN items i ON i.id=r.product_id LEFT JOIN users u ON u.id=r.created_by WHERE r.id=?", (leg["source_id"],)).fetchone()
        elif leg and leg["source_type"] == "purchase":
            purchase_lot = db.execute("SELECT pl.*, p.purchase_no, p.date purchase_date, p.grn_no, p.supplier_invoice_no, s.name supplier_name, s.gstin supplier_gstin, s.phone supplier_phone, i.name item_name, i.code item_code, i.base_unit FROM purchase_lines pl JOIN purchases p ON p.id=pl.purchase_id JOIN items i ON i.id=pl.item_id LEFT JOIN suppliers s ON s.id=p.supplier_id WHERE pl.purchase_id=? LIMIT 1", (leg["source_id"],)).fetchone()

    if not run and not purchase_lot:
        return {"found": False, "query": q}

    # If we have a production run, build the complete 5-stage trace
    if run:
        run_id = run["id"]
        # Stage 1: Raw Materials & Suppliers
        raw_issues = db.execute(
            """SELECT rl.*, i.name item_name, i.code item_code, i.base_unit, i.kind
               FROM run_lines rl
               JOIN items i ON i.id=rl.item_id
               WHERE rl.run_id=?""",
            (run_id,),
        ).fetchall()

        # Find suppliers of these raw materials
        materials_with_suppliers = []
        for rm in raw_issues:
            last_pur = db.execute(
                """SELECT p.purchase_no, p.date, p.grn_no, s.name supplier_name, s.gstin, pl.batch_no supplier_batch
                   FROM purchase_lines pl
                   JOIN purchases p ON p.id=pl.purchase_id
                   LEFT JOIN suppliers s ON s.id=p.supplier_id
                   WHERE pl.item_id=? AND p.date<=?
                   ORDER BY p.date DESC LIMIT 1""",
                (rm["item_id"], run["date"]),
            ).fetchone()
            materials_with_suppliers.append({
                "item_name": rm["item_name"],
                "item_code": rm["item_code"],
                "kind": rm["kind"],
                "planned_qty": rm["planned_milli"],
                "actual_qty": rm["actual_milli"],
                "unit": rm["base_unit"],
                "supplier_name": last_pur["supplier_name"] if last_pur else "Stock Reserve / Internal",
                "supplier_gstin": last_pur["gstin"] if last_pur else "-",
                "grn_no": last_pur["grn_no"] if last_pur else "-",
                "inward_batch": last_pur["supplier_batch"] if last_pur else "-",
                "inward_date": last_pur["date"] if last_pur else "-",
            })

        # Stage 2: Quality Inspection
        qc = db.execute(
            """SELECT qi.*, u.full_name inspector_name
               FROM quality_inspections qi
               LEFT JOIN users u ON u.id=qi.inspected_by
               WHERE qi.reference_type='production_run' AND qi.reference_id=?""",
            (run_id,),
        ).fetchone()

        # Stage 3: Finished Stock & Overheads
        overheads = db.execute(
            "SELECT * FROM run_overheads WHERE run_id=?", (run_id,)
        ).fetchall()

        # Stage 4: Sales Dispatches & Customers
        # Dispatches of this product made on or after run date
        dispatches = db.execute(
            """SELECT i.invoice_no, i.date invoice_date, i.dispatched_on,
                      c.name customer_name, c.state_name, c.phone, c.gstin customer_gstin,
                      il.qty_milli dispatched_qty, il.rate_paise, il.total_paise
               FROM invoices i
               JOIN invoice_lines il ON il.invoice_id=i.id
               JOIN customers c ON c.id=i.customer_id
               WHERE il.item_id=? AND i.status='posted' AND i.dispatched_on IS NOT NULL AND i.date>=?
               ORDER BY i.date ASC""",
            (run["product_id"], run["date"]),
        ).fetchall()

        return {
            "found": True,
            "type": "finished_batch",
            "query": q,
            "run": dict(run),
            "materials": materials_with_suppliers,
            "quality": dict(qc) if qc else None,
            "overheads": [dict(o) for o in overheads],
            "dispatches": [dict(d) for d in dispatches],
        }

    # If it's a purchase lot
    if purchase_lot:
        # Trace which production runs consumed this raw material
        runs_consumed = db.execute(
            """SELECT r.run_no, r.date run_date, r.batch_no fg_batch, r.status,
                      i.name product_name, rl.actual_milli consumed_milli, i.base_unit
               FROM run_lines rl
               JOIN production_runs r ON r.id=rl.run_id
               JOIN items i ON i.id=r.product_id
               WHERE rl.item_id=? AND r.date>=? AND rl.actual_milli > 0
               ORDER BY r.date""",
            (purchase_lot["item_id"], purchase_lot["purchase_date"]),
        ).fetchall()

        return {
            "found": True,
            "type": "raw_lot",
            "query": q,
            "lot": dict(purchase_lot),
            "runs_consumed": [dict(rc) for rc in runs_consumed],
        }

    return {"found": False, "query": q}
