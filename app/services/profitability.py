"""Profitability Intelligence Service.

Calculates real product, batch, and customer profitability from actual
invoice revenue, actual production material consumption, and logged overheads.
No invented financial values.
"""
from decimal import Decimal

from ..util import D, money, qty, round_half_up, today
from . import production, sales


def calculate_product_profitability(db):
    """Calculates revenue, material cost, overheads, gross profit, and margin % per finished product."""
    products = db.execute("SELECT * FROM items WHERE kind='finished' AND active=1 ORDER BY name").fetchall()
    results = []

    for p in products:
        pid = p["id"]

        # 1. Total Invoiced Revenue (Posted Invoices minus Credit Notes)
        inv_data = db.execute(
            """SELECT COALESCE(SUM(il.taxable_paise), 0) rev_taxable,
                      COALESCE(SUM(il.qty_milli), 0) sold_milli
               FROM invoice_lines il
               JOIN invoices i ON i.id=il.invoice_id
               WHERE il.item_id=? AND i.status='posted'""",
            (pid,),
        ).fetchone()

        # Credit note returns
        cn_data = db.execute(
            """SELECT COALESCE(SUM(il.taxable_paise), 0) cn_taxable,
                      COALESCE(SUM(il.qty_milli), 0) ret_milli
               FROM invoice_lines il
               JOIN credit_notes cn ON cn.invoice_id=il.invoice_id
               WHERE il.item_id=?""",
            (pid,),
        ).fetchone()

        net_rev = inv_data["rev_taxable"] - cn_data["cn_taxable"]
        net_sold_qty = inv_data["sold_milli"] - cn_data["ret_milli"]

        # 2. Production Costs across all completed runs for this product
        runs = db.execute("SELECT id FROM production_runs WHERE product_id=? AND status='completed'", (pid,)).fetchall()
        tot_material_cost = 0
        tot_overhead_cost = 0
        tot_labour_cost = 0
        tot_energy_cost = 0
        tot_good_produced = 0
        tot_damaged_packets = 0

        for r in runs:
            s = production.run_summary(db, r["id"])
            tot_material_cost += s["material_paise"]
            tot_overhead_cost += (s["direct_overhead_paise"] + s["allocated_overhead_paise"])
            tot_good_produced += s["run"]["actual_milli"]
            tot_damaged_packets += s["run"]["damaged_milli"]

            # Break down overheads
            oh_breakdown = db.execute(
                "SELECT kind, SUM(amount_paise) s FROM run_overheads WHERE run_id=? GROUP BY kind", (r["id"],)
            ).fetchall()
            for oh in oh_breakdown:
                if oh["kind"] == "labour":
                    tot_labour_cost += oh["s"]
                elif oh["kind"] in ("power_gas", "energy", "electricity"):
                    tot_energy_cost += oh["s"]

        total_mfg_cost = tot_material_cost + tot_overhead_cost
        unit_cost_paise = round_half_up(D(total_mfg_cost) * 1000 / tot_good_produced) if tot_good_produced > 0 else 0

        # Cost of Goods Sold (COGS) for units actually sold
        cogs_paise = round_half_up(D(unit_cost_paise) * net_sold_qty / 1000) if unit_cost_paise > 0 else 0
        gross_profit_paise = net_rev - cogs_paise
        gross_margin_pct = (
            round((Decimal(gross_profit_paise) * 100 / Decimal(net_rev)), 1)
            if net_rev > 0 else (p["price_paise"] - unit_cost_paise) * 100 // p["price_paise"] if (p["price_paise"] and unit_cost_paise) else 0.0
        )

        results.append({
            "product": dict(p),
            "net_revenue_paise": net_rev,
            "units_sold_milli": net_sold_qty,
            "units_produced_milli": tot_good_produced,
            "units_damaged_milli": tot_damaged_packets,
            "unit_cost_paise": unit_cost_paise,
            "unit_price_paise": p["price_paise"] or 0,
            "unit_margin_paise": (p["price_paise"] or 0) - unit_cost_paise,
            "total_material_paise": tot_material_cost,
            "total_labour_paise": tot_labour_cost,
            "total_energy_paise": tot_energy_cost,
            "total_overhead_paise": tot_overhead_cost,
            "total_mfg_cost_paise": total_mfg_cost,
            "cogs_paise": cogs_paise,
            "gross_profit_paise": gross_profit_paise,
            "gross_margin_pct": gross_margin_pct,
        })

    return results


def calculate_customer_profitability(db):
    """Calculates profitability, volume, and payment behavior per customer."""
    customers = db.execute("SELECT * FROM customers ORDER BY name").fetchall()
    prod_costs = {p["product"]["id"]: p["unit_cost_paise"] for p in calculate_product_profitability(db)}
    results = []

    for c in customers:
        cid = c["id"]
        inv_lines = db.execute(
            """SELECT il.item_id, il.qty_milli, il.taxable_paise, il.total_paise, i.date
               FROM invoice_lines il
               JOIN invoices i ON i.id=il.invoice_id
               WHERE i.customer_id=? AND i.status='posted'""",
            (cid,),
        ).fetchall()

        total_rev = sum(l["taxable_paise"] for l in inv_lines)
        total_cogs = sum(
            round_half_up(D(prod_costs.get(l["item_id"], 0)) * l["qty_milli"] / 1000)
            for l in inv_lines
        )
        gross_profit = total_rev - total_cogs
        margin_pct = round((Decimal(gross_profit) * 100 / Decimal(total_rev)), 1) if total_rev > 0 else 0.0

        # Outstanding balance
        recs, _ = sales.receivables(db)
        cust_outstanding = sum(r["outstanding"] for r in recs if r["invoice"]["customer_id"] == cid)

        results.append({
            "customer": dict(c),
            "revenue_paise": total_rev,
            "cogs_paise": total_cogs,
            "gross_profit_paise": gross_profit,
            "margin_pct": margin_pct,
            "outstanding_paise": cust_outstanding,
            "invoice_count": len(set(l["date"] for l in inv_lines)),
        })

    return sorted(results, key=lambda x: -x["revenue_paise"])
