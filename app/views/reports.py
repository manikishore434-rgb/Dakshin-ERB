from flask import Blueprint, Response, g, render_template, request

from ..db import get_db
from ..services import production, reports, sales, stock
from ..util import today
from .auth import login_required

bp = Blueprint("reports", __name__)
ANY = ("admin", "accountant", "owner", "production")


@bp.route("/reports")
@login_required(*ANY)
def index():
    return render_template("reports/index.html", available={k: v[0] for k, v in reports.REPORTS.items() if g.user["role"] in v[2]})


@bp.route("/reports/<slug>")
@login_required(*ANY)
def view(slug):
    spec = reports.REPORTS.get(slug)
    if not spec or g.user["role"] not in spec[2]:
        return render_template("forbidden.html"), 403
    db = get_db()
    params = {k: v for k, v in request.args.items() if v}
    rep = spec[1](db, params)
    fmt = request.args.get("fmt", "html")
    name = f"{slug}-{params.get('from', today()[:8] + '01')}-to-{params.get('to', today())}"
    if fmt == "csv":
        return Response(reports.to_csv(rep), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename={name}.csv"})
    if fmt == "xlsx":
        return Response(reports.to_xlsx(rep), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f"attachment; filename={name}.xlsx"})
    if fmt == "pdf":
        return Response(reports.to_pdf(rep), mimetype="application/pdf", headers={"Content-Disposition": f"inline; filename={name}.pdf"})
    items = db.execute("SELECT id, name FROM items WHERE active=1 ORDER BY kind DESC, name").fetchall() if slug == "stock-ledger" else []
    return render_template("reports/view.html", rep=rep, slug=slug, title=spec[0], p=params, items=items,
                           f=params.get("from", today()[:8] + "01"), t=params.get("to", today()))


@bp.route("/dashboard")
@login_required("owner", "admin")
def dashboard():
    db = get_db()
    d = today()
    orders_today = db.execute("SELECT status, COUNT(*) n FROM orders WHERE substr(created_at,1,10)=? GROUP BY status", (d,)).fetchall()
    pending = db.execute("SELECT COUNT(*) n FROM orders WHERE status IN ('submitted','approved','invoiced')").fetchone()["n"]
    levels = []
    for i in db.execute("SELECT * FROM items WHERE active=1 ORDER BY kind DESC, name"):
        q, v = stock.balance(db, i["id"])
        levels.append({**dict(i), "qty": q, "value": v, "low": i["reorder_level_milli"] and q <= i["reorder_level_milli"]})
    runs = [production.run_summary(db, r["id"]) for r in db.execute("SELECT id FROM production_runs WHERE status='completed' ORDER BY id DESC LIMIT 10")]
    recs, advances = sales.receivables(db)
    due = {}
    for r in recs:
        if r["outstanding"] > 0:
            due[r["invoice"]["customer"]] = due.get(r["invoice"]["customer"], 0) + r["outstanding"]
    cpp = {}
    for s in runs:
        cpp.setdefault(s["run"]["product_name"], s)
    return render_template("reports/dashboard.html", orders_today=orders_today, pending=pending, levels=levels,
                           alerts=[s for s in runs if s["any_flag"]], cpp=cpp, due=sorted(due.items(), key=lambda kv: -kv[1]),
                           total_due=sum(due.values()))


@bp.route("/reports/tally-export.xml")
@login_required("admin", "accountant", "owner")
def tally_export():
    """Generate a Tally-style voucher XML export for posted sales invoices (review before importing)."""
    db = get_db()
    invoices = db.execute("SELECT i.*, c.name customer, c.gstin FROM invoices i JOIN customers c ON c.id=i.customer_id WHERE i.status='posted' ORDER BY i.date,i.id").fetchall()
    import xml.etree.ElementTree as ET
    root = ET.Element("ENVELOPE")
    header = ET.SubElement(root, "HEADER"); ET.SubElement(header, "TALLYREQUEST").text = "Import Data"
    body = ET.SubElement(root, "BODY"); data = ET.SubElement(body, "DATA"); collection = ET.SubElement(data, "IMPORTDATA")
    req = ET.SubElement(collection, "REQUESTDESC"); ET.SubElement(req, "REPORTNAME").text = "Vouchers"
    reqdata = ET.SubElement(collection, "REQUESTDATA")
    for inv in invoices:
        msg = ET.SubElement(reqdata, "TALLYMESSAGE")
        voucher = ET.SubElement(msg, "VOUCHER", VCHTYPE="Sales", ACTION="Create")
        ET.SubElement(voucher, "DATE").text = inv["date"].replace("-", "")
        ET.SubElement(voucher, "VOUCHERNUMBER").text = inv["invoice_no"]
        ET.SubElement(voucher, "PARTYNAME").text = inv["customer"]
        ET.SubElement(voucher, "REFERENCE").text = inv["invoice_no"]
        ET.SubElement(voucher, "NARRATION").text = "Order-to-Audit GST sales invoice export"
        ET.SubElement(voucher, "ISINVOICE").text = "Yes"
        for line in db.execute("SELECT * FROM invoice_lines WHERE invoice_id=?", (inv["id"],)):
            ledger = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
            ET.SubElement(ledger, "LEDGERNAME").text = inv["customer"]
            ET.SubElement(ledger, "ISDEEMEDPOSITIVE").text = "Yes"
            ET.SubElement(ledger, "AMOUNT").text = str(-line["total_paise"] / 100)
            salesentry = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
            ET.SubElement(salesentry, "LEDGERNAME").text = "Sales"
            ET.SubElement(salesentry, "ISDEEMEDPOSITIVE").text = "No"
            ET.SubElement(salesentry, "AMOUNT").text = str(line["taxable_paise"] / 100)
        for name, amount in (("CGST", inv["cgst_paise"]),("SGST", inv["sgst_paise"]),("IGST", inv["igst_paise"])):
            if amount:
                entry=ET.SubElement(voucher,"ALLLEDGERENTRIES.LIST"); ET.SubElement(entry,"LEDGERNAME").text=name
                ET.SubElement(entry,"ISDEEMEDPOSITIVE").text="No"; ET.SubElement(entry,"AMOUNT").text=str(amount/100)
    xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return Response(xml, mimetype="application/xml", headers={"Content-Disposition":"attachment; filename=order_to_audit_tally_export.xml"})


@bp.route("/benchmark")
def benchmark_view():
    import sqlite3
    from ..benchmark import run as bench_run, check as bench_check
    from ..db import init_db
    from ..seed import seed as seed_db
    test_db = sqlite3.connect(":memory:")
    test_db.row_factory = sqlite3.Row
    test_db.execute("PRAGMA foreign_keys = ON")
    init_db(test_db)
    seed_db(test_db)
    date = today()
    res = bench_run(test_db, date)
    checks = bench_check(res)
    test_db.close()
    return render_template("benchmark.html", checks=checks, res=res)

