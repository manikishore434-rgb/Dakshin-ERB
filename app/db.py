"""SQLite access + schema. Stock balances are NEVER stored: they are SUM(stock_ledger)."""
import sqlite3
from contextlib import contextmanager

from flask import current_app, g

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
  full_name TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('salesman','admin','production','accountant','owner')),
  active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS items(
  id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('raw','packaging','finished')),
  base_unit TEXT NOT NULL CHECK(base_unit IN ('kg','l','piece','packet')),
  hsn TEXT, gst_bp INTEGER NOT NULL DEFAULT 0,           -- GST rate in basis points (500 = 5%)
  price_paise INTEGER,                                    -- default selling price (finished goods)
  carton_size INTEGER,                                    -- packets per carton (finished goods)
  pack_role TEXT CHECK(pack_role IN ('per_packet','per_carton')),  -- how packaging is consumed
  reorder_level_milli INTEGER NOT NULL DEFAULT 0, shelf_life_days INTEGER,
  active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS customers(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, type TEXT NOT NULL CHECK(type IN ('retailer','distributor')),
  gstin TEXT, state_code TEXT NOT NULL, state_name TEXT NOT NULL, address TEXT, phone TEXT,
  salesman_id INTEGER REFERENCES users(id));
CREATE TABLE IF NOT EXISTS customer_prices(
  customer_id INTEGER NOT NULL REFERENCES customers(id), item_id INTEGER NOT NULL REFERENCES items(id),
  price_paise INTEGER NOT NULL, PRIMARY KEY(customer_id,item_id));
CREATE TABLE IF NOT EXISTS suppliers(id INTEGER PRIMARY KEY, name TEXT NOT NULL, gstin TEXT, phone TEXT);
CREATE TABLE IF NOT EXISTS purchases(
  id INTEGER PRIMARY KEY, purchase_no TEXT UNIQUE NOT NULL, supplier_id INTEGER REFERENCES suppliers(id),
  date TEXT NOT NULL, supplier_invoice_no TEXT, created_by INTEGER REFERENCES users(id), created_at TEXT);
CREATE TABLE IF NOT EXISTS purchase_lines(
  id INTEGER PRIMARY KEY, purchase_id INTEGER NOT NULL REFERENCES purchases(id),
  item_id INTEGER NOT NULL REFERENCES items(id), qty_milli INTEGER NOT NULL,
  rate TEXT NOT NULL,                      -- rupees per base unit, decimal string
  amount_paise INTEGER NOT NULL, batch_no TEXT, expiry TEXT);
CREATE TABLE IF NOT EXISTS boms(
  id INTEGER PRIMARY KEY, product_id INTEGER UNIQUE NOT NULL REFERENCES items(id),
  yield_milli INTEGER NOT NULL, notes TEXT);
CREATE TABLE IF NOT EXISTS bom_lines(
  bom_id INTEGER NOT NULL REFERENCES boms(id), item_id INTEGER NOT NULL REFERENCES items(id),
  qty_milli INTEGER NOT NULL, PRIMARY KEY(bom_id,item_id));
CREATE TABLE IF NOT EXISTS stock_ledger(
  id INTEGER PRIMARY KEY, date TEXT NOT NULL, ts TEXT NOT NULL,
  item_id INTEGER NOT NULL REFERENCES items(id),
  qty_milli INTEGER NOT NULL, value_paise INTEGER NOT NULL,
  move_type TEXT NOT NULL CHECK(move_type IN
    ('opening','purchase','production_issue','production_output','dispatch','sales_return','adjustment','reversal')),
  source_type TEXT NOT NULL, source_id INTEGER, batch_no TEXT, expiry TEXT, note TEXT,
  user_id INTEGER REFERENCES users(id));
CREATE INDEX IF NOT EXISTS ix_ledger_item_date ON stock_ledger(item_id, date);
CREATE INDEX IF NOT EXISTS ix_ledger_source ON stock_ledger(source_type, source_id);
CREATE TABLE IF NOT EXISTS orders(
  id INTEGER PRIMARY KEY, order_no TEXT UNIQUE NOT NULL, client_uuid TEXT UNIQUE,
  customer_id INTEGER NOT NULL REFERENCES customers(id), salesman_id INTEGER NOT NULL REFERENCES users(id),
  status TEXT NOT NULL CHECK(status IN ('submitted','approved','rejected','invoiced','dispatched','cancelled')),
  notes TEXT, reject_reason TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS order_lines(
  id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id),
  item_id INTEGER NOT NULL REFERENCES items(id), qty_milli INTEGER NOT NULL,
  price_paise INTEGER NOT NULL, uom_note TEXT);
CREATE TABLE IF NOT EXISTS invoices(
  id INTEGER PRIMARY KEY, invoice_no TEXT UNIQUE NOT NULL, fy TEXT NOT NULL, date TEXT NOT NULL,
  order_id INTEGER REFERENCES orders(id), customer_id INTEGER NOT NULL REFERENCES customers(id),
  place_of_supply TEXT NOT NULL, supply_type TEXT NOT NULL CHECK(supply_type IN ('intra','inter')),
  taxable_paise INTEGER NOT NULL, cgst_paise INTEGER NOT NULL, sgst_paise INTEGER NOT NULL,
  igst_paise INTEGER NOT NULL, total_paise INTEGER NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('posted','cancelled')), dispatched_on TEXT,
  created_by INTEGER REFERENCES users(id), created_at TEXT);
CREATE TABLE IF NOT EXISTS invoice_lines(
  id INTEGER PRIMARY KEY, invoice_id INTEGER NOT NULL REFERENCES invoices(id),
  item_id INTEGER NOT NULL REFERENCES items(id), description TEXT, hsn TEXT,
  qty_milli INTEGER NOT NULL, rate_paise INTEGER NOT NULL, taxable_paise INTEGER NOT NULL,
  gst_bp INTEGER NOT NULL, cgst_paise INTEGER NOT NULL, sgst_paise INTEGER NOT NULL,
  igst_paise INTEGER NOT NULL, total_paise INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS doc_seq(key TEXT PRIMARY KEY, last INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS credit_notes(
  id INTEGER PRIMARY KEY, note_no TEXT UNIQUE NOT NULL, invoice_id INTEGER NOT NULL REFERENCES invoices(id),
  date TEXT NOT NULL, reason TEXT, taxable_paise INTEGER NOT NULL, cgst_paise INTEGER NOT NULL,
  sgst_paise INTEGER NOT NULL, igst_paise INTEGER NOT NULL, total_paise INTEGER NOT NULL,
  created_by INTEGER REFERENCES users(id));
CREATE TABLE IF NOT EXISTS payments(
  id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers(id),
  invoice_id INTEGER REFERENCES invoices(id), date TEXT NOT NULL, amount_paise INTEGER NOT NULL CHECK(amount_paise>0),
  mode TEXT, reference TEXT, created_by INTEGER REFERENCES users(id));
CREATE TABLE IF NOT EXISTS production_runs(
  id INTEGER PRIMARY KEY, run_no TEXT UNIQUE NOT NULL, product_id INTEGER NOT NULL REFERENCES items(id),
  date TEXT NOT NULL, batches_milli INTEGER NOT NULL, expected_milli INTEGER NOT NULL,
  actual_milli INTEGER NOT NULL DEFAULT 0, damaged_milli INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL CHECK(status IN ('open','completed','cancelled')),
  batch_no TEXT, expiry TEXT, notes TEXT, created_by INTEGER REFERENCES users(id), created_at TEXT);
CREATE TABLE IF NOT EXISTS run_lines(
  id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES production_runs(id),
  item_id INTEGER NOT NULL REFERENCES items(id), planned_milli INTEGER NOT NULL,
  actual_milli INTEGER NOT NULL DEFAULT 0, actual_value_paise INTEGER NOT NULL DEFAULT 0,
  UNIQUE(run_id,item_id));
CREATE TABLE IF NOT EXISTS run_overheads(
  id INTEGER PRIMARY KEY, run_id INTEGER REFERENCES production_runs(id),  -- NULL = monthly pool
  month TEXT NOT NULL, kind TEXT NOT NULL, amount_paise INTEGER NOT NULL, note TEXT, date TEXT NOT NULL,
  created_by INTEGER REFERENCES users(id));
CREATE TABLE IF NOT EXISTS salesman_visits(
  id INTEGER PRIMARY KEY, salesman_id INTEGER NOT NULL REFERENCES users(id), customer_id INTEGER REFERENCES customers(id),
  visited_at TEXT NOT NULL, latitude REAL NOT NULL, longitude REAL NOT NULL, note TEXT);
CREATE TABLE IF NOT EXISTS audit_log(
  id INTEGER PRIMARY KEY, ts TEXT NOT NULL, user_id INTEGER, username TEXT, entity TEXT NOT NULL,
  entity_id INTEGER, action TEXT NOT NULL, detail TEXT);
"""


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn):
    conn.executescript(SCHEMA)
    conn.commit()


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@contextmanager
def tx(db):
    """Commit on success, roll back on any exception (so a failed action leaves nothing behind)."""
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise


def setting(db, key, default=None):
    r = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r["value"] if r else default


def next_seq(db, key):
    r = db.execute("SELECT last FROM doc_seq WHERE key=?", (key,)).fetchone()
    n = (r["last"] if r else 0) + 1
    db.execute("INSERT INTO doc_seq(key,last) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET last=excluded.last", (key, n))
    return n
