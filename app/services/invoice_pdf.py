import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..db import setting
from ..util import amount_in_words, money, qty


def invoice_pdf(db, invoice_id) -> bytes:
    inv = db.execute("SELECT i.*, c.name cname, c.gstin cgstin, c.address caddr FROM invoices i "
                     "JOIN customers c ON c.id=i.customer_id WHERE i.id=?", (invoice_id,)).fetchone()
    lines = db.execute("SELECT * FROM invoice_lines WHERE invoice_id=?", (invoice_id,)).fetchall()
    st = getSampleStyleSheet()
    small = st["BodyText"].clone("s", fontSize=8, leading=10)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
                            title=f"Tax Invoice {inv['invoice_no']}")
    P = lambda t, s=small: Paragraph(escape(str(t)), s)
    story = [Paragraph(escape(setting(db, "company_name")), st["Title"]),
             P(setting(db, "company_address") + "   GSTIN: " + setting(db, "company_gstin") + "   State: " +
               setting(db, "factory_state_name") + " (" + setting(db, "factory_state_code") + ")"),
             Spacer(1, 4), Paragraph("<b>TAX INVOICE</b>" + ("  -  CANCELLED (credit note issued)" if inv["status"] == "cancelled" else ""), st["Heading2"])]
    meta = Table([[P(f"Invoice no: {inv['invoice_no']}"), P(f"Date: {inv['date']}"), P(f"Financial year: {inv['fy']}")],
                  [P(f"Bill to: {inv['cname']}"), P(f"GSTIN: {inv['cgstin'] or 'Unregistered'}"), P(f"Place of supply: {inv['place_of_supply']}")],
                  [P(inv["caddr"] or ""), P(f"Supply: {'Intra-state (CGST+SGST)' if inv['supply_type'] == 'intra' else 'Inter-state (IGST)'}"), P("")]],
                 colWidths=[70 * mm, 55 * mm, 57 * mm])
    meta.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.black), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [meta, Spacer(1, 6)]
    intra = inv["supply_type"] == "intra"
    head = ["#", "Description", "HSN", "Qty (pkts)", "Rate", "Taxable", "GST %"] + (["CGST", "SGST"] if intra else ["IGST"]) + ["Total"]
    data = [[P(h, small.clone("h", fontName="Helvetica-Bold")) for h in head]]
    for n, l in enumerate(lines, 1):
        row = [n, l["description"], l["hsn"], qty(l["qty_milli"]), money(l["rate_paise"]), money(l["taxable_paise"]), f"{l['gst_bp'] / 100:g}%"]
        row += [money(l["cgst_paise"]), money(l["sgst_paise"])] if intra else [money(l["igst_paise"])]
        row.append(money(l["total_paise"]))
        data.append([P(c) for c in row])
    tot = ["", "Total", "", "", "", money(inv["taxable_paise"]), ""] + ([money(inv["cgst_paise"]), money(inv["sgst_paise"])] if intra else [money(inv["igst_paise"])]) + [money(inv["total_paise"])]
    data.append([P(c, small.clone("b", fontName="Helvetica-Bold")) for c in tot])
    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey)]))
    story += [t, Spacer(1, 6), P("Amount in words: " + amount_in_words(inv["total_paise"])),
              Spacer(1, 4), P("All amounts in Indian Rupees (Rs). Rounding: tax is computed per line and rounded half-up to the paisa. "
                              "This is a computer-generated demo invoice.")]
    doc.build(story)
    return buf.getvalue()
