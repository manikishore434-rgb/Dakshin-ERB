"""Auditor reports. Each report returns {'title', 'sections': [{'name','columns','rows','totals'}]}.
columns = [(label, kind)] with kind in text|date|money|qty|int|pct. Money = paise ints, qty = milli ints,
so HTML shows formatted values and CSV/Excel get true numbers."""
import csv
import io
from decimal import Decimal

from ..util import D, money, qty as fmt_qty, today
from . import production, sales, stock

RECEIPTS = ",".join(f"'{t}'" for t in stock.RECEIPT_TYPES)
ISSUES = ",".join(f"'{t}'" for t in stock.ISSUE_TYPES)
ADJ = ",".join(f"'{t}'" for t in stock.ADJ_TYPES)


def _range(p):
    first = today()[:8] + "01"
    return p.get("from") or first, p.get("to") or today()


def _totals(rows, cols, sum_idx):
    t = [None] * len(cols)
    t[0] = "Total"
    for i in sum_idx:
        t[i] = sum(r[i] or 0 for r in rows)
    return t


def sales_register(db, p):
    f, t = _range(p)
    rows = [[r["date"], r["no"], r["typ"], r["customer"], r["gstin"] or "Unregistered", r["pos"], r["taxable"], r["cgst"],
             r["sgst"], r["igst"], r["total"], r["status"]] for r in db.execute(
        """SELECT i.date, i.invoice_no no, 'Invoice' typ, c.name customer, c.gstin, i.place_of_supply pos, i.taxable_paise taxable,
                  i.cgst_paise cgst, i.sgst_paise sgst, i.igst_paise igst, i.total_paise total, i.status
           FROM invoices i JOIN customers c ON c.id=i.customer_id WHERE i.date BETWEEN :f AND :t
           UNION ALL
           SELECT n.date, n.note_no, 'Credit note', c.name, c.gstin, i.place_of_supply, -n.taxable_paise, -n.cgst_paise,
                  -n.sgst_paise, -n.igst_paise, -n.total_paise, 'credit note for ' || i.invoice_no
           FROM credit_notes n JOIN invoices i ON i.id=n.invoice_id JOIN customers c ON c.id=i.customer_id
           WHERE n.date BETWEEN :f AND :t ORDER BY 1, 2""", {"f": f, "t": t})]
    cols = [("Date", "date"), ("Document", "text"), ("Type", "text"), ("Customer", "text"), ("GSTIN", "text"),
            ("Place of supply", "text"), ("Taxable", "money"), ("CGST", "money"), ("SGST", "money"), ("IGST", "money"),
            ("Total", "money"), ("Status", "text")]
    return {"title": f"Sales register {f} to {t} (cancelled invoices are offset by their credit notes in the totals)",
            "sections": [{"name": "Invoices and credit notes", "columns": cols, "rows": rows, "totals": _totals(rows, cols, range(6, 11))}]}


def customer_sales(db, p):
    f, t = _range(p)
    rows = [[r["name"], r["n"], r["taxable"], r["tax"], r["total"]] for r in db.execute(
        """SELECT c.name, COUNT(*) n, SUM(i.taxable_paise) taxable, SUM(i.cgst_paise+i.sgst_paise+i.igst_paise) tax,
                  SUM(i.total_paise) total FROM invoices i JOIN customers c ON c.id=i.customer_id
           WHERE i.status='posted' AND i.date BETWEEN ? AND ? GROUP BY c.id ORDER BY total DESC""", (f, t))]
    cols = [("Customer", "text"), ("Invoices", "int"), ("Taxable", "money"), ("Tax", "money"), ("Total", "money")]
    return {"title": f"Customer-wise sales {f} to {t}",
            "sections": [{"name": "Customer-wise", "columns": cols, "rows": rows, "totals": _totals(rows, cols, range(1, 5))}]}


def product_sales(db, p):
    f, t = _range(p)
    rows = [[r["name"], r["hsn"], r["q"], r["taxable"], r["total"]] for r in db.execute(
        """SELECT l.description name, l.hsn, SUM(l.qty_milli) q, SUM(l.taxable_paise) taxable, SUM(l.total_paise) total
           FROM invoice_lines l JOIN invoices i ON i.id=l.invoice_id
           WHERE i.status='posted' AND i.date BETWEEN ? AND ? GROUP BY l.item_id ORDER BY total DESC""", (f, t))]
    cols = [("Product", "text"), ("HSN", "text"), ("Quantity", "qty"), ("Taxable", "money"), ("Total", "money")]
    return {"title": f"Product-wise sales {f} to {t}",
            "sections": [{"name": "Product-wise", "columns": cols, "rows": rows, "totals": _totals(rows, cols, (2, 3, 4))}]}


def gst_summary(db, p):
    """Outward supplies in the shape of GSTR-1 (rate-wise, HSN summary, B2B) and GSTR-3B table 3.1(a). Credit notes are netted."""
    f, t = _range(p)
    q = """SELECT l.gst_bp bp, l.hsn, l.description d, i.supply_type st, i.invoice_no no, i.date date, c.gstin gstin,
                  i.place_of_supply pos, {s}*l.qty_milli q, {s}*l.taxable_paise tx, {s}*l.cgst_paise cg, {s}*l.sgst_paise sg,
                  {s}*l.igst_paise ig, {s}*l.total_paise tot
           FROM invoice_lines l JOIN invoices i ON i.id=l.invoice_id JOIN customers c ON c.id=i.customer_id """
    src = [dict(r) for r in db.execute(q.format(s=1) + "WHERE i.status='posted' AND i.date BETWEEN ? AND ?", (f, t))]
    cn = [dict(r) for r in db.execute(  # credit notes reverse the original lines
        q.format(s=-1).replace("i.date date", "n.date date").replace("i.invoice_no no", "n.note_no no") +
        "JOIN credit_notes n ON n.invoice_id=i.id WHERE n.date BETWEEN ? AND ?", (f, t))]
    allrows = src + cn
    by_rate = {}
    for r in allrows:
        a = by_rate.setdefault(r["bp"], [0, 0, 0, 0])
        for k, key in enumerate(("tx", "ig", "cg", "sg")):
            a[k] += r[key]
    rate_rows = [[f"{D(bp) / 100}%", *v, sum(v) - v[0] + 0] for bp, v in sorted(by_rate.items())]
    rate_rows = [[lbl, tx, ig, cg, sg, ig + cg + sg] for lbl, tx, ig, cg, sg, _ in rate_rows]
    rc = [("Rate", "text"), ("Taxable value", "money"), ("IGST", "money"), ("CGST", "money"), ("SGST", "money"), ("Total tax", "money")]
    hsn = {}
    for r in allrows:
        a = hsn.setdefault((r["hsn"], r["d"]), [0, 0, 0, 0, 0])
        for k, key in enumerate(("q", "tx", "ig", "cg", "sg")):
            a[k] += r[key]
    hsn_rows = [[h, d, "PAC (packets)", *v] for (h, d), v in sorted(hsn.items())]
    hc = [("HSN", "text"), ("Description", "text"), ("UQC", "text"), ("Quantity", "qty"), ("Taxable value", "money"),
          ("IGST", "money"), ("CGST", "money"), ("SGST", "money")]
    b2b = [[r["gstin"], r["no"], r["date"], r["pos"], f"{D(r['bp']) / 100}%", r["tx"], r["ig"], r["cg"], r["sg"], r["tot"]]
           for r in sorted(allrows, key=lambda r: (r["date"], r["no"])) if r["gstin"]]
    bc = [("Recipient GSTIN", "text"), ("Invoice / note", "text"), ("Date", "date"), ("Place of supply", "text"), ("Rate", "text"),
          ("Taxable value", "money"), ("IGST", "money"), ("CGST", "money"), ("SGST", "money"), ("Line total", "money")]
    tot = [sum(r[i] for r in rate_rows) for i in range(1, 6)]
    t31 = [["(a) Outward taxable supplies (other than zero rated, nil rated, exempted)", *tot[:1], *tot[1:4]]]
    tc = [("GSTR-3B table 3.1", "text"), ("Taxable value", "money"), ("Integrated tax", "money"), ("Central tax", "money"), ("State/UT tax", "money")]
    return {"title": f"GST summary of outward supplies {f} to {t}", "sections": [
        {"name": "GSTR-3B 3.1(a) totals", "columns": tc, "rows": t31, "totals": None},
        {"name": "Rate-wise (GSTR-1 table 4/7 basis)", "columns": rc, "rows": rate_rows, "totals": _totals(rate_rows, rc, range(1, 6))},
        {"name": "HSN-wise summary (GSTR-1 table 12)", "columns": hc, "rows": hsn_rows, "totals": _totals(hsn_rows, hc, range(3, 8))},
        {"name": "B2B invoice-wise (GSTR-1 table 4A)", "columns": bc, "rows": b2b, "totals": _totals(b2b, bc, range(5, 10))}]}


def purchase_register(db, p):
    f, t = _range(p)
    rows = [[r["date"], r["purchase_no"], r["supplier"] or "-", r["supplier_invoice_no"] or "", r["name"], r["qty_milli"],
             r["base_unit"], r["rate"], r["amount_paise"], r["batch_no"] or "", r["expiry"] or ""] for r in db.execute(
        """SELECT p.date, p.purchase_no, s.name supplier, p.supplier_invoice_no, i.name, l.qty_milli, i.base_unit, l.rate,
                  l.amount_paise, l.batch_no, l.expiry FROM purchases p JOIN purchase_lines l ON l.purchase_id=p.id
           JOIN items i ON i.id=l.item_id LEFT JOIN suppliers s ON s.id=p.supplier_id
           WHERE p.date BETWEEN ? AND ? ORDER BY p.date, p.id""", (f, t))]
    cols = [("Date", "date"), ("Purchase no", "text"), ("Supplier", "text"), ("Supplier invoice", "text"), ("Item", "text"),
            ("Quantity", "qty"), ("Unit", "text"), ("Rate (Rs/unit)", "text"), ("Amount", "money"), ("Batch", "text"), ("Expiry", "date")]
    return {"title": f"Purchase register {f} to {t}",
            "sections": [{"name": "Purchases", "columns": cols, "rows": rows, "totals": _totals(rows, cols, (8,))}]}


def stock_summary(db, p):
    f, t = _range(p)
    kind = p.get("kind")
    rows = []
    for r in db.execute(f"""
        SELECT i.name, i.kind, i.base_unit,
          COALESCE(SUM(CASE WHEN l.date < :f THEN l.qty_milli END),0) opening,
          COALESCE(SUM(CASE WHEN l.date BETWEEN :f AND :t AND l.move_type IN ({RECEIPTS}) THEN l.qty_milli END),0) receipts,
          COALESCE(SUM(CASE WHEN l.date BETWEEN :f AND :t AND l.move_type IN ({ISSUES}) THEN -l.qty_milli END),0) issues,
          COALESCE(SUM(CASE WHEN l.date BETWEEN :f AND :t AND l.move_type IN ({ADJ}) THEN l.qty_milli END),0) adj,
          COALESCE(SUM(CASE WHEN l.date <= :t THEN l.qty_milli END),0) closing,
          COALESCE(SUM(CASE WHEN l.date <= :t THEN l.value_paise END),0) value
        FROM items i LEFT JOIN stock_ledger l ON l.item_id=i.id WHERE i.active=1 AND (:kind IS NULL OR i.kind=:kind)
        GROUP BY i.id ORDER BY i.kind DESC, i.name""", {"f": f, "t": t, "kind": kind}):
        assert r["opening"] + r["receipts"] - r["issues"] + r["adj"] == r["closing"]
        rows.append([r["name"], r["kind"], r["base_unit"], r["opening"], r["receipts"], r["issues"], r["adj"], r["closing"], r["value"]])
    cols = [("Item", "text"), ("Type", "text"), ("Unit", "text"), ("Opening", "qty"), ("Receipts", "qty"), ("Issues / sales", "qty"),
            ("Adjustments", "qty"), ("Closing", "qty"), ("Value (wtd avg)", "money")]
    tot = [None] * len(cols)
    tot[0], tot[8] = "Total value", sum(r[8] for r in rows)
    return {"title": f"Stock summary {f} to {t}  (opening + receipts - issues +/- adjustments = closing)",
            "sections": [{"name": "Raw, packaging and finished goods", "columns": cols, "rows": rows, "totals": tot}]}


def _source_label(db, cache, st, sid):
    key = (st, sid)
    if key not in cache:
        table = {"purchase": ("purchases", "purchase_no"), "production_run": ("production_runs", "run_no"),
                 "invoice": ("invoices", "invoice_no"), "credit_note": ("credit_notes", "note_no")}.get(st)
        r = db.execute(f"SELECT {table[1]} v FROM {table[0]} WHERE id=?", (sid,)).fetchone() if table and sid else None
        cache[key] = r["v"] if r else st.replace("_", " ").title()
    return cache[key]


def stock_ledger(db, p):
    f, t = _range(p)
    item_id = int(p["item_id"]) if p.get("item_id") else None
    items = db.execute("SELECT * FROM items WHERE active=1 AND (? IS NULL OR id=?) ORDER BY kind DESC, name", (item_id, item_id)).fetchall()
    cols = [("Date", "date"), ("Movement", "text"), ("Source document", "text"), ("Batch", "text"), ("In", "qty"),
            ("Out", "qty"), ("Balance", "qty"), ("Value", "money"), ("Note", "text")]
    cache, sections = {}, []
    for it in items:
        opening = db.execute("SELECT COALESCE(SUM(qty_milli),0) q FROM stock_ledger WHERE item_id=? AND date<?", (it["id"], f)).fetchone()["q"]
        bal = opening
        rows = [[f, "Opening balance", "", "", None, None, bal, None, ""]]
        for r in db.execute("SELECT * FROM stock_ledger WHERE item_id=? AND date BETWEEN ? AND ? ORDER BY date, id", (it["id"], f, t)):
            bal += r["qty_milli"]
            rows.append([r["date"], r["move_type"].replace("_", " "), _source_label(db, cache, r["source_type"], r["source_id"]),
                         r["batch_no"] or "", r["qty_milli"] if r["qty_milli"] > 0 else None,
                         -r["qty_milli"] if r["qty_milli"] < 0 else None, bal, r["value_paise"], r["note"] or ""])
        if len(rows) > 1 or item_id:
            sections.append({"name": f"{it['name']} ({it['base_unit']})", "columns": cols, "rows": rows, "totals": None})
    return {"title": f"Stock ledger {f} to {t}", "sections": sections}


def production_report(db, p):
    f, t = _range(p)
    runs = db.execute("SELECT id FROM production_runs WHERE status='completed' AND date BETWEEN ? AND ? ORDER BY date, id", (f, t)).fetchall()
    rc = [("Run", "text"), ("Date", "date"), ("Product", "text"), ("Batches", "qty"), ("Expected", "qty"), ("Actual good", "qty"),
          ("Yield var %", "pct"), ("Flag", "text"), ("Wastage (damaged)", "qty"), ("Materials", "money"), ("Overheads", "money"),
          ("Cost / packet", "money"), ("Price", "money"), ("Margin / packet", "money")]
    lc = [("Run", "text"), ("Item", "text"), ("Unit", "text"), ("Planned", "qty"), ("Actual", "qty"), ("Variance %", "pct"), ("Flag", "text"), ("Value", "money")]
    run_rows, line_rows = [], []
    for r in runs:
        s = production.run_summary(db, r["id"])
        run = s["run"]
        run_rows.append([run["run_no"], run["date"], run["product_name"], run["batches_milli"], run["expected_milli"], run["actual_milli"],
                         s["yield_var_pct"], "VARIANCE" if s["yield_flag"] else "ok", run["damaged_milli"], s["material_paise"],
                         s["direct_overhead_paise"] + s["allocated_overhead_paise"], s["cost_per_packet_paise"], run["price_paise"],
                         s["margin_per_packet_paise"]])
        for l in s["lines"]:
            line_rows.append([run["run_no"], l["name"], l["base_unit"], l["planned_milli"], l["actual_milli"], l["var_pct"],
                              "VARIANCE" if l["flag"] else "ok", l["actual_value_paise"]])
    tol = production.tolerance_bp(db) / 100
    return {"title": f"Production report {f} to {t} (variance tolerance {tol}%)", "sections": [
        {"name": "Runs: yield, wastage and cost", "columns": rc, "rows": run_rows, "totals": None},
        {"name": "Planned vs actual consumption", "columns": lc, "rows": line_rows, "totals": None}]}


def outstanding(db, p):
    f, t = _range(p)
    recs, advances = sales.receivables(db, t)
    cust = {}
    for r in recs:
        if r["outstanding"] <= 0:
            continue
        inv = r["invoice"]
        a = cust.setdefault(inv["customer"], [0, 0, 0, 0, 0, 0])
        b = 1 if r["age_days"] <= 30 else 2 if r["age_days"] <= 60 else 3 if r["age_days"] <= 90 else 4
        a[b] += r["outstanding"]
        a[0] += r["outstanding"]
    crows = [[k, *v] for k, v in sorted(cust.items())]
    cc = [("Customer", "text"), ("Outstanding", "money"), ("0-30 days", "money"), ("31-60 days", "money"), ("61-90 days", "money"), ("90+ days", "money")]
    irows = [[r["invoice"]["customer"], r["invoice"]["invoice_no"], r["invoice"]["date"], r["invoice"]["total_paise"], r["paid"],
              r["outstanding"], r["age_days"]] for r in recs if r["outstanding"] > 0]
    ic = [("Customer", "text"), ("Invoice", "text"), ("Date", "date"), ("Invoice value", "money"), ("Received", "money"),
          ("Outstanding", "money"), ("Age (days)", "int")]
    return {"title": f"Receivables outstanding as on {t}", "sections": [
        {"name": "Customer-wise with ageing", "columns": cc, "rows": crows, "totals": _totals(crows, cc, range(1, 6))},
        {"name": "Invoice-wise", "columns": ic, "rows": irows, "totals": _totals(irows, ic, (3, 4, 5))}]}


def collections(db, p):
    f, t = _range(p)
    rows = [[r["date"], r["name"], r["invoice_no"] or "(on account)", r["mode"] or "", r["reference"] or "", r["amount_paise"]] for r in db.execute(
        """SELECT p.date, c.name, i.invoice_no, p.mode, p.reference, p.amount_paise FROM payments p
           JOIN customers c ON c.id=p.customer_id LEFT JOIN invoices i ON i.id=p.invoice_id
           WHERE p.date BETWEEN ? AND ? ORDER BY p.date, p.id""", (f, t))]
    cols = [("Date", "date"), ("Customer", "text"), ("Against", "text"), ("Mode", "text"), ("Reference", "text"), ("Amount", "money")]
    return {"title": f"Payments and collections {f} to {t}",
            "sections": [{"name": "Receipts", "columns": cols, "rows": rows, "totals": _totals(rows, cols, (5,))}]}


def audit_trail(db, p):
    f, t = _range(p)
    rows = [[r["ts"], r["username"], r["entity"], r["entity_id"], r["action"], r["detail"] or ""] for r in db.execute(
        "SELECT * FROM audit_log WHERE substr(ts,1,10) BETWEEN ? AND ? ORDER BY id", (f, t))]
    cols = [("Time", "text"), ("User", "text"), ("Entity", "text"), ("Id", "int"), ("Action", "text"), ("Detail", "text")]
    return {"title": f"Audit trail {f} to {t}", "sections": [{"name": "Edits, cancellations and postings", "columns": cols, "rows": rows, "totals": None}]}


def mrp_report(db, p):
    from . import mrp
    res = mrp.run_mrp(db)
    req_cols = [("Item", "text"), ("Kind", "text"), ("Gross Req", "qty"), ("On Hand", "qty"), ("Open POs", "qty"),
                ("Safety Stock", "qty"), ("Deficit", "qty"), ("Suggested Buy", "qty"), ("Supplier", "text"), ("Est Cost", "money")]
    req_rows = [[r["item"]["name"], r["item"]["kind"], r["gross_req_milli"], r["on_hand_milli"], r["open_po_milli"],
                 r["safety_stock_milli"], r["net_deficit_milli"], r["suggested_buy_milli"], r["supplier_name"], r["est_cost_paise"]]
                for r in res["material_requirements"]]
    prod_cols = [("Product", "text"), ("Demand (pkts)", "qty"), ("On Hand", "qty"), ("Deficit", "qty"), ("Batches Needed", "int")]
    prod_rows = [[ps["product"]["name"], ps["demanded_milli"], ps["on_hand_milli"], ps["net_deficit_milli"], ps["batches_needed"]]
                 for ps in res["production_suggestions"]]
    return {"title": "Material Requirements Planning (MRP) Analysis", "sections": [
        {"name": "Raw & Packaging Material Requirements", "columns": req_cols, "rows": req_rows, "totals": _totals(req_rows, req_cols, (9,))},
        {"name": "Finished Goods Production Requirements", "columns": prod_cols, "rows": prod_rows, "totals": None}]}


def quality_report(db, p):
    from . import quality
    f, t = _range(p)
    inspections = db.execute(
        """SELECT qi.*, i.name item_name, u.full_name inspector
           FROM quality_inspections qi
           JOIN items i ON i.id=qi.item_id
           LEFT JOIN users u ON u.id=qi.inspected_by
           WHERE substr(qi.inspected_at,1,10) BETWEEN ? AND ?
           ORDER BY qi.id DESC""", (f, t)).fetchall()
    cols = [("Inspection No", "text"), ("Type", "text"), ("Status", "text"), ("Item", "text"), ("Batch", "text"),
            ("Sample Size", "text"), ("Defect", "text"), ("Inspector", "text"), ("Date", "text")]
    rows = [[r["inspection_no"], r["inspection_type"], r["status"].upper(), r["item_name"], r["batch_no"] or "-",
             r["sample_size"] or "-", r["defect_category"] or "None", r["inspector"] or "System", r["inspected_at"][:10]]
            for r in inspections]
    return {"title": f"Quality Management & Inspection Report {f} to {t}", "sections": [
        {"name": "Inspections Log", "columns": cols, "rows": rows, "totals": None}]}


def supplier_payables_report(db, p):
    from . import procurement
    t = p.get("to") or today()
    data = procurement.supplier_payables(db, t)
    cols = [("Supplier", "text"), ("GSTIN", "text"), ("Phone", "text"), ("Total Purchases", "money"),
            ("Paid Amount", "money"), ("Outstanding Dues", "money")]
    rows = [[d["supplier"]["name"], d["supplier"]["gstin"] or "-", d["supplier"]["phone"] or "-",
             d["total_purchases_paise"], d["total_paid_paise"], d["outstanding_paise"]]
            for d in data]
    return {"title": f"Supplier Payables & Dues as of {t}", "sections": [
        {"name": "Supplier Ledger Summary", "columns": cols, "rows": rows, "totals": _totals(rows, cols, (3, 4, 5))}]}


def profitability_report(db, p):
    from . import profitability
    prod_data = profitability.calculate_product_profitability(db)
    cust_data = profitability.calculate_customer_profitability(db)

    p_cols = [("Product", "text"), ("Units Sold", "qty"), ("Revenue", "money"), ("Unit Cost", "money"),
              ("COGS", "money"), ("Gross Profit", "money"), ("Gross Margin %", "pct")]
    p_rows = [[r["product"]["name"], r["units_sold_milli"], r["net_revenue_paise"], r["unit_cost_paise"],
               r["cogs_paise"], r["gross_profit_paise"], r["gross_margin_pct"]]
              for r in prod_data]

    c_cols = [("Customer", "text"), ("Revenue", "money"), ("COGS", "money"), ("Gross Profit", "money"),
              ("Margin %", "pct"), ("Outstanding", "money")]
    c_rows = [[r["customer"]["name"], r["revenue_paise"], r["cogs_paise"], r["gross_profit_paise"],
               r["margin_pct"], r["outstanding_paise"]]
              for r in cust_data]

    return {"title": "Profitability & Margin Intelligence Report", "sections": [
        {"name": "Product Unit Economics & Gross Margins", "columns": p_cols, "rows": p_rows, "totals": _totals(p_rows, p_cols, (2, 4, 5))},
        {"name": "Customer Contribution & Margins", "columns": c_cols, "rows": c_rows, "totals": _totals(c_rows, c_cols, (1, 2, 3, 5))}]}


REPORTS = {   # slug: (title, function, roles allowed)
    "sales-register": ("Sales register", sales_register, ("admin", "accountant", "owner")),
    "customer-sales": ("Customer-wise sales", customer_sales, ("admin", "accountant", "owner")),
    "product-sales": ("Product-wise sales", product_sales, ("admin", "accountant", "owner")),
    "gst-summary": ("GST summary (GSTR-1 / 3B)", gst_summary, ("admin", "accountant", "owner")),
    "purchase-register": ("Purchase register", purchase_register, ("admin", "accountant", "owner", "production")),
    "stock-summary": ("Stock summary", stock_summary, ("admin", "accountant", "owner", "production")),
    "stock-ledger": ("Stock ledger", stock_ledger, ("admin", "accountant", "owner", "production")),
    "production": ("Production: planned vs actual, yield, cost", production_report, ("admin", "accountant", "owner", "production")),
    "outstanding": ("Outstanding and ageing", outstanding, ("admin", "accountant", "owner")),
    "collections": ("Payments and collections", collections, ("admin", "accountant", "owner")),
    "audit": ("Audit trail", audit_trail, ("admin", "accountant", "owner")),
    "mrp": ("Material Requirements Planning (MRP)", mrp_report, ("admin", "accountant", "owner", "production")),
    "quality": ("Quality & Inspections", quality_report, ("admin", "accountant", "owner", "production")),
    "supplier-payables": ("Supplier payables & dues", supplier_payables_report, ("admin", "accountant", "owner")),
    "profitability": ("Profitability & Unit Margins", profitability_report, ("admin", "accountant", "owner")),
}


# ---------------------------------------------------------------- rendering
def display(kind, v):
    if v is None:
        return ""
    return {"money": lambda: money(v), "qty": lambda: fmt_qty(v), "pct": lambda: f"{v}%"}.get(kind, lambda: str(v))()


def export_value(kind, v):
    if v is None:
        return None
    if kind == "money":
        return Decimal(int(v)) / 100
    if kind == "qty":
        return Decimal(int(v)) / 1000
    return v


def to_csv(rep) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([rep["title"]])
    for s in rep["sections"]:
        w.writerow([])
        w.writerow([s["name"]])
        w.writerow([c[0] for c in s["columns"]])
        for r in s["rows"]:
            w.writerow([export_value(c[1], v) for c, v in zip(s["columns"], r)])
        if s.get("totals"):
            w.writerow([export_value(c[1], v) for c, v in zip(s["columns"], s["totals"])])
    return out.getvalue()


def to_xlsx(rep) -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    wb.remove(wb.active)
    for s in rep["sections"] or [{"name": "Empty", "columns": [], "rows": [], "totals": None}]:
        ws = wb.create_sheet(s["name"][:28].replace("/", "-").replace(":", "-"))
        ws.append([rep["title"]])
        ws.append([c[0] for c in s["columns"]])
        for r in s["rows"] + ([s["totals"]] if s.get("totals") else []):
            ws.append([export_value(c[1], v) for c, v in zip(s["columns"], r)])
        for ri in range(3, ws.max_row + 1):
            for ci, (_, kind) in enumerate(s["columns"], 1):
                if kind in ("money",):
                    ws.cell(ri, ci).number_format = "#,##0.00"
                elif kind == "qty":
                    ws.cell(ri, ci).number_format = "#,##0.###"
        for ci, (label, _) in enumerate(s["columns"], 1):
            ws.column_dimensions[ws.cell(2, ci).column_letter].width = max(12, len(label) + 4)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def to_pdf(rep) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape
    st = getSampleStyleSheet()
    cell = st["BodyText"].clone("cell", fontSize=6.5, leading=8)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=18, rightMargin=18, topMargin=18, bottomMargin=18)
    story = [Paragraph(escape(rep["title"]), st["Heading3"])]
    for s in rep["sections"]:
        story += [Spacer(1, 6), Paragraph(escape(s["name"]), st["Heading4"])]
        data = [[Paragraph(f"<b>{escape(c[0])}</b>", cell) for c in s["columns"]]]
        for r in s["rows"] + ([s["totals"]] if s.get("totals") else []):
            data.append([Paragraph(escape(display(c[1], v)), cell) for c, v in zip(s["columns"], r)])
        t = Table(data, repeatRows=1)
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                               ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story.append(t)
    doc.build(story)
    return buf.getvalue()
