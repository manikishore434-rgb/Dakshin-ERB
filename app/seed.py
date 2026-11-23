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
    for u, name, role in [("salesman_a", "Salesman A", "salesman"), ("salesman_b", "Salesman B", "salesman"),
                          ("admin", "Factory Admin", "admin"), ("production", "Production Supervisor", "production"),
                          ("accountant", "Accountant / Auditor", "accountant"), ("owner", "Owner", "owner")]:
        db.execute("INSERT INTO users(username,password_hash,full_name,role) VALUES (?,?,?,?)", (u, pw, name, role))
    uid = {r["username"]: r["id"] for r in db.execute("SELECT id, username FROM users")}
    for k, v in {"company_name": "Sri Murugan Snacks (demo)", "company_address": "Industrial Estate, Tiruchirappalli, Tamil Nadu",
                 "company_gstin": "33AAAAA0000A1Z5", "factory_state_code": "33", "factory_state_name": "Tamil Nadu",
                 "variance_tolerance_bp": "300"}.items():
        db.execute("INSERT INTO settings(key,value) VALUES (?,?)", (k, v))

    def item(code, name, kind, unit, **kw):
        cols = {"hsn": None, "gst_bp": 0, "price_paise": None, "carton_size": None, "pack_role": None,
                "reorder_level_milli": 0, "shelf_life_days": None, **kw}
        cur = db.execute("INSERT INTO items(code,name,kind,base_unit,hsn,gst_bp,price_paise,carton_size,pack_role,"
                         "reorder_level_milli,shelf_life_days) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         (code, name, kind, unit, *[cols[k] for k in ("hsn", "gst_bp", "price_paise", "carton_size",
                                                                      "pack_role", "reorder_level_milli", "shelf_life_days")]))
        return cur.lastrowid

    flour = item("RM-FLOUR", "Flour", "raw", "kg", reorder_level_milli=to_milli(50))
    oil = item("RM-OIL", "Cooking oil", "raw", "l", reorder_level_milli=to_milli(10))
    spice = item("RM-SPICE", "Salt and spice mix", "raw", "kg", reorder_level_milli=to_milli(2))
    pouch = item("PK-POUCH200", "200 g pouch", "packaging", "piece", pack_role="per_packet", reorder_level_milli=to_milli(200))
    carton = item("PK-CARTON", "Carton (holds 20 packets)", "packaging", "piece", pack_role="per_carton", reorder_level_milli=to_milli(10))
    # HSN 2106 90 99 (namkeen/savoury preparations). The benchmark tells us to assume 5% GST.
    murukku = item("FG-MUR200", "Murukku 200 g", "finished", "packet", hsn="21069099", gst_bp=500,
                   price_paise=to_paise(50), carton_size=20, shelf_life_days=90)
    cur = db.execute("INSERT INTO boms(product_id,yield_milli,notes) VALUES (?,?,?)", (murukku, to_milli(200), "1 batch = 200 packets"))
    bom = cur.lastrowid
    for iid, q in [(flour, 40), (oil, 10), (spice, "1.2"), (pouch, 200), (carton, 10)]:
        db.execute("INSERT INTO bom_lines(bom_id,item_id,qty_milli) VALUES (?,?,?)", (bom, iid, to_milli(q)))

    db.execute("INSERT INTO customers(name,type,gstin,state_code,state_name,address,phone,salesman_id) VALUES (?,?,?,?,?,?,?,?)",
               ("Retailer A", "retailer", "33BBBBB1111B1Z5", "33", "Tamil Nadu", "Trichy", "9000000001", uid["salesman_a"]))
    db.execute("INSERT INTO customers(name,type,gstin,state_code,state_name,address,phone,salesman_id) VALUES (?,?,?,?,?,?,?,?)",
               ("Distributor B", "distributor", "29CCCCC2222C1Z5", "29", "Karnataka", "Bengaluru", "9000000002", uid["salesman_b"]))
    db.execute("INSERT INTO suppliers(name,gstin,phone) VALUES (?,?,?)", ("Sri Lakshmi Flour Mills", "33DDDDD3333D1Z5", "9000000003"))

    admin = {"id": uid["admin"], "username": "admin"}
    # opening stock (rate = the 'Rate' column of the benchmark; flour opens at 42). Finished goods open at an ASSUMED Rs 30/packet.
    for it, q, rate in [(flour, 100, 42), (oil, 30, 140), (spice, 5, 200), (pouch, 500, "2.50"), (carton, 30, 15), (murukku, 50, 30)]:
        qm = to_milli(q)
        stock.post(db, item_id=it, qty_milli=qm, value_paise=round_half_up(D(qm) * to_paise(rate) / 1000), move_type="opening",
                   source_type="opening", source_id=None, user=admin, date=opening_date, note="Opening balance")
    db.commit()
