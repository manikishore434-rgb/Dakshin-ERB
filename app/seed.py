"""Loads the Section 5 master data (idempotent: does nothing if users already exist)."""
import datetime as dt

from werkzeug.security import generate_password_hash

from .db import init_db
from .services import stock
from .util import D, round_half_up, to_milli, to_paise

DEMO_PASSWORD = "demo123"


def seed(db, opening_date=None):
    init_db(db)
    if db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
        return
    # opening balances are dated the day before the current month starts, so the monthly stock report shows them as "opening"
    opening_date = opening_date or (dt.date.today().replace(day=1) - dt.timedelta(days=1)).isoformat()
    pw = generate_password_hash(DEMO_PASSWORD)
    for u, name, role in [
        ("salesman_a", "Salesman A", "salesman"),
        ("salesman_b", "Salesman B", "salesman"),
        ("admin", "Factory Admin", "admin"),
        ("production", "Production Supervisor", "production"),
        ("accountant", "Accountant / Auditor", "accountant"),
        ("owner", "Owner / Managing Director", "owner")
    ]:
        db.execute(
            "INSERT INTO users(username,password_hash,full_name,role,email,phone,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (u, pw, name, role, f"{u}@snackflow.local", "9876543210", dt.datetime.now().isoformat())
        )
    uid = {r["username"]: r["id"] for r in db.execute("SELECT id, username FROM users")}
    for k, v in {
        "company_name": "Sri Murugan Snacks (demo)",
        "company_address": "Industrial Estate, Tiruchirappalli, Tamil Nadu",
        "company_gstin": "33AAAAA0000A1Z5",
        "factory_state_code": "33",
        "factory_state_name": "Tamil Nadu",
        "variance_tolerance_bp": "300"
    }.items():
        db.execute("INSERT INTO settings(key,value) VALUES (?,?)", (k, v))

    def item(code, name, kind, unit, **kw):
        cols = {
            "hsn": None, "gst_bp": 0, "price_paise": None, "carton_size": None, "pack_role": None,
            "reorder_level_milli": 0, "shelf_life_days": None, "category": "General",
            "min_stock_milli": 0, "max_stock_milli": 0, "safety_stock_milli": 0, "lead_time_days": 3,
            "standard_cost_paise": 0, **kw
        }
        cur = db.execute(
            "INSERT INTO items(code,name,kind,base_unit,hsn,gst_bp,price_paise,carton_size,pack_role,"
            "reorder_level_milli,shelf_life_days,category,min_stock_milli,max_stock_milli,safety_stock_milli,lead_time_days,standard_cost_paise) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (code, name, kind, unit, *[cols[k] for k in (
                "hsn", "gst_bp", "price_paise", "carton_size", "pack_role", "reorder_level_milli",
                "shelf_life_days", "category", "min_stock_milli", "max_stock_milli", "safety_stock_milli",
                "lead_time_days", "standard_cost_paise"
            )])
        )
        return cur.lastrowid

    flour = item("RM-FLOUR", "Flour", "raw", "kg", category="Flours & Grains", reorder_level_milli=to_milli(50),
                 min_stock_milli=to_milli(40), max_stock_milli=to_milli(300), safety_stock_milli=to_milli(30), lead_time_days=3)
    oil = item("RM-OIL", "Cooking oil", "raw", "l", category="Oils & Fats", reorder_level_milli=to_milli(10),
               min_stock_milli=to_milli(10), max_stock_milli=to_milli(100), safety_stock_milli=to_milli(10), lead_time_days=2)
    spice = item("RM-SPICE", "Salt and spice mix", "raw", "kg", category="Seasonings & Spices", reorder_level_milli=to_milli(2),
                 min_stock_milli=to_milli(2), max_stock_milli=to_milli(20), safety_stock_milli=to_milli(2), lead_time_days=5)
    pouch = item("PK-POUCH200", "200 g pouch", "packaging", "piece", pack_role="per_packet", category="Packaging Materials",
                 reorder_level_milli=to_milli(200), min_stock_milli=to_milli(200), max_stock_milli=to_milli(2000), safety_stock_milli=to_milli(100), lead_time_days=7)
    carton = item("PK-CARTON", "Carton (holds 20 packets)", "packaging", "piece", pack_role="per_carton", category="Packaging Materials",
                  reorder_level_milli=to_milli(10), min_stock_milli=to_milli(10), max_stock_milli=to_milli(100), safety_stock_milli=to_milli(5), lead_time_days=4)
    # HSN 2106 90 99 (namkeen/savoury preparations). Benchmark: 5% GST.
    murukku = item("FG-MUR200", "Murukku 200 g", "finished", "packet", hsn="21069099", gst_bp=500,
                   price_paise=to_paise(50), carton_size=20, shelf_life_days=90, category="Packaged Snacks",
                   reorder_level_milli=to_milli(50), min_stock_milli=to_milli(50), max_stock_milli=to_milli(500), safety_stock_milli=to_milli(20), lead_time_days=1)

    cur = db.execute("INSERT INTO boms(product_id,yield_milli,notes) VALUES (?,?,?)", (murukku, to_milli(200), "1 batch = 200 packets"))
    bom = cur.lastrowid
    for iid, q in [(flour, 40), (oil, 10), (spice, "1.2"), (pouch, 200), (carton, 10)]:
        db.execute("INSERT INTO bom_lines(bom_id,item_id,qty_milli) VALUES (?,?,?)", (bom, iid, to_milli(q)))

    db.execute(
        "INSERT INTO customers(name,type,gstin,state_code,state_name,address,phone,salesman_id,email,contact_person,credit_limit_paise,payment_terms_days) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        ("Retailer A", "retailer", "33BBBBB1111B1Z5", "33", "Tamil Nadu", "Shop 12, West Boulevard Rd, Trichy", "9000000001",
         uid["salesman_a"], "retailer_a@snackflow.local", "Senthil Kumar", to_paise(50000), 15)
    )
    db.execute(
        "INSERT INTO customers(name,type,gstin,state_code,state_name,address,phone,salesman_id,email,contact_person,credit_limit_paise,payment_terms_days) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        ("Distributor B", "distributor", "29CCCCC2222C1Z5", "29", "Karnataka", "Plot 45, Peenya Industrial Area, Bengaluru", "9000000002",
         uid["salesman_b"], "distributor_b@snackflow.local", "Ramesh Rao", to_paise(150000), 30)
    )
    db.execute(
        "INSERT INTO suppliers(name,gstin,phone,email,address,contact_person,lead_time_days,rating,payment_terms_days) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        ("Sri Lakshmi Flour Mills", "33DDDDD3333D1Z5", "9000000003", "orders@lakshmiflour.local", "Mill Road, Dindigul, Tamil Nadu", "Murugesan", 3, 4.8, 30)
    )

    admin = {"id": uid["admin"], "username": "admin"}
    # opening stock (rate = the 'Rate' column of the benchmark; flour opens at 42). Finished goods open at an ASSUMED Rs 30/packet.
    for it, q, rate in [(flour, 100, 42), (oil, 30, 140), (spice, 5, 200), (pouch, 500, "2.50"), (carton, 30, 15), (murukku, 50, 30)]:
        qm = to_milli(q)
        stock.post(db, item_id=it, qty_milli=qm, value_paise=round_half_up(D(qm) * to_paise(rate) / 1000), move_type="opening",
                   source_type="opening", source_id=None, user=admin, date=opening_date, note="Opening balance")

    if db.execute("SELECT COUNT(*) n FROM alerts").fetchone()["n"] == 0:
        now_ts = dt.datetime.now().isoformat(timespec="seconds")
        db.execute("INSERT INTO alerts(category, severity, title, message, status, created_at) "
                   "VALUES ('inventory', 'medium', 'Stock Buffer Watch: Cooking Oil', 'Cooking oil runway approaching safety replenishment threshold.', 'open', ?)", (now_ts,))
        db.execute("INSERT INTO alerts(category, severity, title, message, status, created_at) "
                   "VALUES ('finance', 'high', 'Overdue Credit Alert: Distributor B', 'Outstanding balance requires follow-up per credit policy.', 'open', ?)", (now_ts,))
        db.execute("INSERT INTO alerts(category, severity, title, message, status, created_at) "
                   "VALUES ('quality', 'low', 'Periodic Scale Calibration', 'Production packing line digital scale calibration due.', 'open', ?)", (now_ts,))

    db.commit()
