"""Material Requirements Planning (MRP) Engine.

Analyzes open sales demand, production schedules, BOM recipes, current inventory,
open purchase orders, and safety stocks to calculate raw material deficits and suggested POs.
"""
import datetime as dt
import math
from decimal import Decimal

from ..util import D, ServiceError, round_half_up, to_milli, to_paise, today
from . import procurement, production, stock


def run_mrp(db):
    """Executes the MRP calculation on current database state.
    Returns a dict with:
      - 'demand_orders': list of approved/invoiced undispatched sales orders
      - 'finished_goods_demand': aggregated demand per finished product
      - 'production_suggestions': batches needed to fulfill orders
      - 'material_requirements': detailed calculation per raw & packaging material
      - 'shortages': list of materials with net deficit > 0
      - 'suggested_pos': grouped suggested purchase orders by supplier
    """
    # 1. Unfulfilled Sales Demand
    orders = db.execute(
        """SELECT o.id, o.order_no, o.customer_id, c.name customer_name, o.created_at,
                  ol.item_id, ol.qty_milli, i.name item_name, i.code item_code, i.base_unit
           FROM orders o
           JOIN customers c ON c.id=o.customer_id
           JOIN order_lines ol ON ol.order_id=o.id
           JOIN items i ON i.id=ol.item_id
           WHERE o.status IN ('approved', 'invoiced')
           ORDER BY o.id"""
    ).fetchall()

    fg_demand = {}  # item_id -> total_qty_milli
    for o in orders:
        fg_demand[o["item_id"]] = fg_demand.get(o["item_id"], 0) + o["qty_milli"]

    # 2. Finished Goods Production Needs
    production_suggestions = []
    bom_demand_materials = {}  # material_item_id -> gross_needed_milli

    for fg_id, demanded_milli in fg_demand.items():
        fg_item = db.execute("SELECT * FROM items WHERE id=?", (fg_id,)).fetchone()
        on_hand, _ = stock.balance(db, fg_id)
        # Reserved by orders is the demand itself
        net_fg_deficit = max(0, demanded_milli - on_hand)

        bom = db.execute("SELECT * FROM boms WHERE product_id=?", (fg_id,)).fetchone()
        batches_needed = 0
        if bom and bom["yield_milli"] > 0:
            if net_fg_deficit > 0:
                batches_needed = math.ceil(net_fg_deficit / bom["yield_milli"])
            total_planned_batches = math.ceil(demanded_milli / bom["yield_milli"]) if demanded_milli > 0 else 0
        else:
            total_planned_batches = 0

        production_suggestions.append({
            "product": dict(fg_item),
            "demanded_milli": demanded_milli,
            "on_hand_milli": on_hand,
            "net_deficit_milli": net_fg_deficit,
            "batches_needed": batches_needed,
            "batch_yield_milli": bom["yield_milli"] if bom else 0,
        })

        # Explode BOM for the total required batches
        if bom:
            lines = db.execute("SELECT * FROM bom_lines WHERE bom_id=?", (bom["id"],)).fetchall()
            for bl in lines:
                needed = bl["qty_milli"] * (batches_needed if batches_needed > 0 else total_planned_batches)
                bom_demand_materials[bl["item_id"]] = bom_demand_materials.get(bl["item_id"], 0) + needed

    # 3. Material Requirements Calculation
    all_raw_pack = db.execute(
        "SELECT * FROM items WHERE kind IN ('raw', 'packaging') AND active=1 ORDER BY kind DESC, name"
    ).fetchall()

    material_requirements = []
    shortages = []
    suggested_pos_map = {}  # supplier_id -> list of suggested item purchases

    for mat in all_raw_pack:
        mid = mat["id"]
        gross_req = bom_demand_materials.get(mid, 0)
        on_hand, _ = stock.balance(db, mid)

        # Inbound from open purchase orders
        open_po_qty = db.execute(
            """SELECT COALESCE(SUM(pol.qty_milli - pol.received_qty_milli), 0) s
               FROM purchase_order_lines pol
               JOIN purchase_orders po ON po.id=pol.po_id
               WHERE pol.item_id=? AND po.status IN ('approved', 'partially_received')""",
            (mid,),
        ).fetchone()["s"]

        safety_stock = mat["safety_stock_milli"] or 0
        reorder_level = mat["reorder_level_milli"] or 0
        min_stock = mat["min_stock_milli"] or 0

        # Effective inventory available = on_hand + open_po - gross_req
        effective_balance = (on_hand + open_po_qty) - gross_req
        net_deficit = 0
        if effective_balance < safety_stock:
            net_deficit = safety_stock - effective_balance

        suggested_buy = 0
        if net_deficit > 0:
            suggested_buy = max(net_deficit, reorder_level, min_stock)

        # Find preferred/last supplier and last purchase rate
        last_pur = db.execute(
            """SELECT pl.rate, pl.amount_paise, pl.qty_milli, p.supplier_id, s.name supplier_name, s.lead_time_days
               FROM purchase_lines pl
               JOIN purchases p ON p.id=pl.purchase_id
               LEFT JOIN suppliers s ON s.id=p.supplier_id
               WHERE pl.item_id=? ORDER BY p.date DESC, p.id DESC LIMIT 1""",
            (mid,),
        ).fetchone()

        supplier_id = None
        supplier_name = "Default Supplier"
        est_rate_paise = 0
        lead_time = mat["lead_time_days"] or 3

        if last_pur:
            supplier_id = last_pur["supplier_id"]
            supplier_name = last_pur["supplier_name"] or "Default Supplier"
            lead_time = last_pur["lead_time_days"] or lead_time
            if last_pur["qty_milli"] > 0:
                est_rate_paise = round_half_up(D(last_pur["amount_paise"]) * 1000 / last_pur["qty_milli"])
        else:
            # Fallback supplier
            supp = db.execute("SELECT * FROM suppliers WHERE active=1 ORDER BY id LIMIT 1").fetchone()
            if supp:
                supplier_id = supp["id"]
                supplier_name = supp["name"]
                lead_time = supp["lead_time_days"] or lead_time

        item_mrp = {
            "item": dict(mat),
            "gross_req_milli": gross_req,
            "on_hand_milli": on_hand,
            "open_po_milli": open_po_qty,
            "safety_stock_milli": safety_stock,
            "effective_balance_milli": effective_balance,
            "net_deficit_milli": net_deficit,
            "suggested_buy_milli": suggested_buy,
            "supplier_id": supplier_id,
            "supplier_name": supplier_name,
            "lead_time_days": lead_time,
            "est_rate_paise": est_rate_paise,
            "est_cost_paise": round_half_up(D(suggested_buy) * est_rate_paise / 1000) if est_rate_paise else 0,
        }
        material_requirements.append(item_mrp)

        if net_deficit > 0:
            shortages.append(item_mrp)
            if supplier_id:
                suggested_pos_map.setdefault(supplier_id, {
                    "supplier_id": supplier_id,
                    "supplier_name": supplier_name,
                    "lead_time_days": lead_time,
                    "lines": [],
                    "total_est_cost_paise": 0,
                })
                suggested_pos_map[supplier_id]["lines"].append(item_mrp)
                suggested_pos_map[supplier_id]["total_est_cost_paise"] += item_mrp["est_cost_paise"]

    return {
        "demand_orders": [dict(o) for o in orders],
        "production_suggestions": production_suggestions,
        "material_requirements": material_requirements,
        "shortages": shortages,
        "suggested_pos": list(suggested_pos_map.values()),
    }


def create_suggested_pos_action(db, user):
    """Converts MRP shortage calculations directly into Draft Purchase Orders."""
    mrp = run_mrp(db)
    created_po_ids = []
    for sp in mrp["suggested_pos"]:
        lines = []
        for l in sp["lines"]:
            rate = l["est_rate_paise"] or to_paise(50)  # default nominal if no prior purchase
            lines.append({
                "item_id": l["item"]["id"],
                "qty_milli": l["suggested_buy_milli"],
                "rate_paise": rate,
            })
        if lines:
            target_date = (dt.date.today() + dt.timedelta(days=sp["lead_time_days"])).isoformat()
            po_id = procurement.create_purchase_order(
                db,
                user,
                supplier_id=sp["supplier_id"],
                order_date=today(),
                lines=lines,
                notes=f"Auto-generated via MRP for material deficit (Lead time: {sp['lead_time_days']} days)",
                expected_delivery=target_date,
            )
            created_po_ids.append(po_id)
    return created_po_ids
