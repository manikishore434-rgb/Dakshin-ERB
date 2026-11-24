"""SQLite access + schema. Stock balances are NEVER stored: they are SUM(stock_ledger)."""
import sqlite3
from contextlib import contextmanager

from flask import current_app, g

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  full_name TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('salesman','admin','production','accountant','owner')),
  active INTEGER NOT NULL DEFAULT 1,
  email TEXT,
  phone TEXT,
  created_at TEXT);

CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS items(
  id INTEGER PRIMARY KEY,
  code TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('raw','packaging','finished')),
  base_unit TEXT NOT NULL CHECK(base_unit IN ('kg','l','piece','packet')),
  hsn TEXT,
  gst_bp INTEGER NOT NULL DEFAULT 0,                       -- GST rate in basis points (500 = 5%)
  price_paise INTEGER,                                    -- default selling price (finished goods)
  carton_size INTEGER,                                    -- packets per carton (finished goods)
  pack_role TEXT CHECK(pack_role IN ('per_packet','per_carton')),  -- how packaging is consumed
  reorder_level_milli INTEGER NOT NULL DEFAULT 0,
  shelf_life_days INTEGER,
  category TEXT,
  min_stock_milli INTEGER NOT NULL DEFAULT 0,
  max_stock_milli INTEGER NOT NULL DEFAULT 0,
  safety_stock_milli INTEGER NOT NULL DEFAULT 0,
  standard_cost_paise INTEGER NOT NULL DEFAULT 0,
  lead_time_days INTEGER NOT NULL DEFAULT 3,
  active INTEGER NOT NULL DEFAULT 1);

CREATE TABLE IF NOT EXISTS customers(
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  type TEXT NOT NULL CHECK(type IN ('retailer','distributor')),
  gstin TEXT,
  state_code TEXT NOT NULL,
  state_name TEXT NOT NULL,
  address TEXT,
  phone TEXT,
  email TEXT,
  contact_person TEXT,
  credit_limit_paise INTEGER NOT NULL DEFAULT 5000000,
  payment_terms_days INTEGER NOT NULL DEFAULT 30,
  salesman_id INTEGER REFERENCES users(id),
  active INTEGER NOT NULL DEFAULT 1);

CREATE TABLE IF NOT EXISTS customer_prices(
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  item_id INTEGER NOT NULL REFERENCES items(id),
  price_paise INTEGER NOT NULL,
  PRIMARY KEY(customer_id, item_id));

CREATE TABLE IF NOT EXISTS suppliers(
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  gstin TEXT,
  phone TEXT,
  email TEXT,
  address TEXT,
  contact_person TEXT,
  lead_time_days INTEGER NOT NULL DEFAULT 7,
  rating REAL NOT NULL DEFAULT 5.0,
  payment_terms_days INTEGER NOT NULL DEFAULT 30,
  active INTEGER NOT NULL DEFAULT 1);

CREATE TABLE IF NOT EXISTS purchase_orders(
  id INTEGER PRIMARY KEY,
  po_no TEXT UNIQUE NOT NULL,
  supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
  status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','approved','partially_received','received','cancelled')),
  order_date TEXT NOT NULL,
  expected_delivery TEXT,
  total_amount_paise INTEGER NOT NULL DEFAULT 0,
  notes TEXT,
  created_by INTEGER REFERENCES users(id),
  approved_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS purchase_order_lines(
  id INTEGER PRIMARY KEY,
  po_id INTEGER NOT NULL REFERENCES purchase_orders(id),
  item_id INTEGER NOT NULL REFERENCES items(id),
  qty_milli INTEGER NOT NULL,
  rate_paise INTEGER NOT NULL,
  amount_paise INTEGER NOT NULL,
  received_qty_milli INTEGER NOT NULL DEFAULT 0);

CREATE TABLE IF NOT EXISTS purchases(
  id INTEGER PRIMARY KEY,
  purchase_no TEXT UNIQUE NOT NULL,
  supplier_id INTEGER REFERENCES suppliers(id),
  date TEXT NOT NULL,
  supplier_invoice_no TEXT,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT,
  po_id INTEGER REFERENCES purchase_orders(id),
  status TEXT NOT NULL DEFAULT 'completed',
  grn_no TEXT,
  payment_status TEXT NOT NULL DEFAULT 'unpaid' CHECK(payment_status IN ('unpaid','partial','paid')),
  paid_paise INTEGER NOT NULL DEFAULT 0,
  notes TEXT);

CREATE TABLE IF NOT EXISTS purchase_lines(
  id INTEGER PRIMARY KEY,
  purchase_id INTEGER NOT NULL REFERENCES purchases(id),
  item_id INTEGER NOT NULL REFERENCES items(id),
  qty_milli INTEGER NOT NULL,
  rate TEXT NOT NULL,                                     -- rupees per base unit, decimal string
  amount_paise INTEGER NOT NULL,
  batch_no TEXT,
  expiry TEXT);

CREATE TABLE IF NOT EXISTS supplier_payments(
  id INTEGER PRIMARY KEY,
  supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
  purchase_id INTEGER REFERENCES purchases(id),
  po_id INTEGER REFERENCES purchase_orders(id),
  date TEXT NOT NULL,
  amount_paise INTEGER NOT NULL CHECK(amount_paise > 0),
  mode TEXT,
  reference TEXT,
  notes TEXT,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT);

CREATE TABLE IF NOT EXISTS boms(
  id INTEGER PRIMARY KEY,
  product_id INTEGER UNIQUE NOT NULL REFERENCES items(id),
  yield_milli INTEGER NOT NULL,
  notes TEXT);

CREATE TABLE IF NOT EXISTS bom_lines(
  bom_id INTEGER NOT NULL REFERENCES boms(id),
  item_id INTEGER NOT NULL REFERENCES items(id),
  qty_milli INTEGER NOT NULL,
  PRIMARY KEY(bom_id, item_id));

CREATE TABLE IF NOT EXISTS stock_ledger(
  id INTEGER PRIMARY KEY,
  date TEXT NOT NULL,
  ts TEXT NOT NULL,
  item_id INTEGER NOT NULL REFERENCES items(id),
  qty_milli INTEGER NOT NULL,
  value_paise INTEGER NOT NULL,
  move_type TEXT NOT NULL CHECK(move_type IN
    ('opening','purchase','production_issue','production_output','dispatch','sales_return','adjustment','reversal','scrap')),
  source_type TEXT NOT NULL,
  source_id INTEGER,
  batch_no TEXT,
  lot_no TEXT,
  expiry TEXT,
  quality_status TEXT NOT NULL DEFAULT 'approved',
  note TEXT,
  user_id INTEGER REFERENCES users(id));

CREATE INDEX IF NOT EXISTS ix_ledger_item_date ON stock_ledger(item_id, date);
CREATE INDEX IF NOT EXISTS ix_ledger_source ON stock_ledger(source_type, source_id);

CREATE TABLE IF NOT EXISTS orders(
  id INTEGER PRIMARY KEY,
  order_no TEXT UNIQUE NOT NULL,
  client_uuid TEXT UNIQUE,
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  salesman_id INTEGER NOT NULL REFERENCES users(id),
  status TEXT NOT NULL CHECK(status IN ('submitted','approved','rejected','invoiced','dispatched','cancelled')),
  priority TEXT NOT NULL DEFAULT 'normal' CHECK(priority IN ('urgent','high','normal','low')),
  delivery_date TEXT,
  dispatched_at TEXT,
  cancelled_at TEXT,
  cancel_reason TEXT,
  notes TEXT,
  reject_reason TEXT,
  lost_sale_recorded INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS order_lines(
  id INTEGER PRIMARY KEY,
  order_id INTEGER NOT NULL REFERENCES orders(id),
  item_id INTEGER NOT NULL REFERENCES items(id),
  qty_milli INTEGER NOT NULL,
  price_paise INTEGER NOT NULL,
  uom_note TEXT);

CREATE TABLE IF NOT EXISTS invoices(
  id INTEGER PRIMARY KEY,
  invoice_no TEXT UNIQUE NOT NULL,
  fy TEXT NOT NULL,
  date TEXT NOT NULL,
  order_id INTEGER REFERENCES orders(id),
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  place_of_supply TEXT NOT NULL,
  supply_type TEXT NOT NULL CHECK(supply_type IN ('intra','inter')),
  taxable_paise INTEGER NOT NULL,
  cgst_paise INTEGER NOT NULL,
  sgst_paise INTEGER NOT NULL,
  igst_paise INTEGER NOT NULL,
  total_paise INTEGER NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('posted','cancelled')),
  dispatched_on TEXT,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT);

CREATE TABLE IF NOT EXISTS invoice_lines(
  id INTEGER PRIMARY KEY,
  invoice_id INTEGER NOT NULL REFERENCES invoices(id),
  item_id INTEGER NOT NULL REFERENCES items(id),
  description TEXT,
  hsn TEXT,
  qty_milli INTEGER NOT NULL,
  rate_paise INTEGER NOT NULL,
  taxable_paise INTEGER NOT NULL,
  gst_bp INTEGER NOT NULL,
  cgst_paise INTEGER NOT NULL,
  sgst_paise INTEGER NOT NULL,
  igst_paise INTEGER NOT NULL,
  total_paise INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS doc_seq(key TEXT PRIMARY KEY, last INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS credit_notes(
  id INTEGER PRIMARY KEY,
  note_no TEXT UNIQUE NOT NULL,
  invoice_id INTEGER NOT NULL REFERENCES invoices(id),
  date TEXT NOT NULL,
  reason TEXT,
  taxable_paise INTEGER NOT NULL,
  cgst_paise INTEGER NOT NULL,
  sgst_paise INTEGER NOT NULL,
  igst_paise INTEGER NOT NULL,
  total_paise INTEGER NOT NULL,
  created_by INTEGER REFERENCES users(id));

CREATE TABLE IF NOT EXISTS payments(
  id INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  invoice_id INTEGER REFERENCES invoices(id),
  date TEXT NOT NULL,
  amount_paise INTEGER NOT NULL CHECK(amount_paise > 0),
  mode TEXT,
  reference TEXT,
  created_by INTEGER REFERENCES users(id));

CREATE TABLE IF NOT EXISTS production_runs(
  id INTEGER PRIMARY KEY,
  run_no TEXT UNIQUE NOT NULL,
  product_id INTEGER NOT NULL REFERENCES items(id),
  date TEXT NOT NULL,
  batches_milli INTEGER NOT NULL,
  expected_milli INTEGER NOT NULL,
  actual_milli INTEGER NOT NULL DEFAULT 0,
  damaged_milli INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL CHECK(status IN ('open','completed','cancelled')),
  batch_no TEXT,
  expiry TEXT,
  quality_status TEXT NOT NULL DEFAULT 'pending',
  qa_status TEXT DEFAULT 'pending',
  quality_inspection_id INTEGER,
  machine_overhead_paise INTEGER NOT NULL DEFAULT 0,
  scheduled_date TEXT,
  notes TEXT,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT);

CREATE TABLE IF NOT EXISTS run_lines(
  id INTEGER PRIMARY KEY,
  run_id INTEGER NOT NULL REFERENCES production_runs(id),
  item_id INTEGER NOT NULL REFERENCES items(id),
  planned_milli INTEGER NOT NULL,
  actual_milli INTEGER NOT NULL DEFAULT 0,
  actual_value_paise INTEGER NOT NULL DEFAULT 0,
  UNIQUE(run_id, item_id));

CREATE TABLE IF NOT EXISTS run_overheads(
  id INTEGER PRIMARY KEY,
  run_id INTEGER REFERENCES production_runs(id),            -- NULL = monthly pool
  month TEXT NOT NULL,
  kind TEXT NOT NULL,
  amount_paise INTEGER NOT NULL,
  note TEXT,
  date TEXT NOT NULL,
  created_by INTEGER REFERENCES users(id));

CREATE TABLE IF NOT EXISTS salesman_visits(
  id INTEGER PRIMARY KEY,
  salesman_id INTEGER NOT NULL REFERENCES users(id),
  customer_id INTEGER REFERENCES customers(id),
  visited_at TEXT NOT NULL,
  latitude REAL NOT NULL,
  longitude REAL NOT NULL,
  note TEXT);

CREATE TABLE IF NOT EXISTS audit_log(
  id INTEGER PRIMARY KEY,
  ts TEXT NOT NULL,
  user_id INTEGER,
  username TEXT,
  entity TEXT NOT NULL,
  entity_id INTEGER,
  action TEXT NOT NULL,
  detail TEXT,
  prev_value TEXT,
  new_value TEXT);

CREATE TABLE IF NOT EXISTS production_plans (
  id INTEGER PRIMARY KEY,
  plan_no TEXT UNIQUE NOT NULL,
  date TEXT NOT NULL,
  product_id INTEGER NOT NULL REFERENCES items(id),
  batches_milli INTEGER NOT NULL,
  target_qty_milli INTEGER NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('draft', 'approved', 'scheduled', 'converted', 'cancelled')),
  order_id INTEGER REFERENCES orders(id),
  notes TEXT,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS quality_inspections (
  id INTEGER PRIMARY KEY,
  inspection_no TEXT UNIQUE NOT NULL,
  inspection_type TEXT DEFAULT 'finished_goods',
  target_type TEXT,
  target_id INTEGER,
  item_id INTEGER REFERENCES items(id),
  batch_no TEXT,
  reference_type TEXT,
  reference_id INTEGER,
  inspected_by INTEGER REFERENCES users(id),
  inspector_id INTEGER REFERENCES users(id),
  inspected_at TEXT,
  inspection_date TEXT,
  date TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  sample_size TEXT,
  parameters_json TEXT,
  defect_category TEXT,
  defect_description TEXT,
  corrective_action TEXT,
  moisture_pct REAL,
  seal_integrity TEXT,
  aroma_taste TEXT,
  weight_check TEXT,
  defects_count INTEGER DEFAULT 0,
  remarks TEXT,
  notes TEXT,
  created_at TEXT);

CREATE TABLE IF NOT EXISTS lost_sales (
  id INTEGER PRIMARY KEY,
  date TEXT NOT NULL,
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  item_id INTEGER NOT NULL REFERENCES items(id),
  qty_milli INTEGER NOT NULL,
  lost_amount_paise INTEGER NOT NULL,
  reason TEXT NOT NULL CHECK(reason IN ('stock_shortage', 'production_shortage', 'delivery_constraint', 'customer_cancellation', 'pricing', 'other')),
  salesman_id INTEGER REFERENCES users(id),
  follow_up_status TEXT NOT NULL DEFAULT 'open' CHECK(follow_up_status IN ('open', 'contacted', 'recovered', 'closed')),
  notes TEXT,
  created_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY,
  category TEXT NOT NULL CHECK(category IN ('inventory', 'production', 'quality', 'sales', 'purchase', 'supplier', 'finance', 'audit', 'expiry')),
  severity TEXT NOT NULL CHECK(severity IN ('critical', 'high', 'medium', 'low')),
  title TEXT NOT NULL,
  message TEXT NOT NULL,
  entity_type TEXT,
  entity_id INTEGER,
  status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'acknowledged', 'resolved')),
  assigned_to INTEGER REFERENCES users(id),
  action_url TEXT,
  created_at TEXT NOT NULL,
  resolved_at TEXT);

CREATE TABLE IF NOT EXISTS system_alerts(
  id INTEGER PRIMARY KEY,
  alert_key TEXT UNIQUE,
  category TEXT NOT NULL,
  severity TEXT NOT NULL CHECK(severity IN ('critical','high','medium','low')),
  title TEXT NOT NULL,
  message TEXT NOT NULL,
  entity_type TEXT,
  entity_id INTEGER,
  action_url TEXT,
  status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','acknowledged','resolved')),
  created_at TEXT NOT NULL,
  resolved_at TEXT,
  resolved_by INTEGER REFERENCES users(id));

CREATE TABLE IF NOT EXISTS business_recommendations(
  id INTEGER PRIMARY KEY,
  rec_key TEXT UNIQUE,
  title TEXT NOT NULL,
  category TEXT NOT NULL,
  priority TEXT NOT NULL CHECK(priority IN ('critical','high','medium','low')),
  problem TEXT NOT NULL,
  evidence TEXT NOT NULL,
  suggested_action TEXT NOT NULL,
  estimated_impact TEXT,
  action_url TEXT,
  status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','applied','dismissed')),
  created_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  category TEXT NOT NULL CHECK(category IN ('purchase', 'supplier', 'invoice', 'production', 'batch', 'quality', 'audit', 'compliance', 'other')),
  entity_type TEXT,
  entity_id INTEGER,
  filename TEXT NOT NULL,
  stored_filename TEXT NOT NULL,
  mime_type TEXT,
  file_size INTEGER,
  uploaded_by INTEGER REFERENCES users(id),
  notes TEXT,
  created_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS recalls (
  id INTEGER PRIMARY KEY,
  recall_no TEXT UNIQUE NOT NULL,
  batch_no TEXT NOT NULL,
  product_id INTEGER NOT NULL REFERENCES items(id),
  date TEXT NOT NULL,
  reason TEXT NOT NULL,
  severity TEXT NOT NULL CHECK(severity IN ('critical', 'major', 'minor')),
  affected_qty_milli INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'initiated' CHECK(status IN ('initiated', 'in_progress', 'completed', 'cancelled')),
  actions_taken TEXT,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS daily_closings (
  id INTEGER PRIMARY KEY,
  closing_date TEXT UNIQUE NOT NULL,
  closed_by INTEGER REFERENCES users(id),
  closed_at TEXT NOT NULL,
  summary_json TEXT NOT NULL,
  notes TEXT);
"""


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate_columns(conn):
    """Safely apply column additions to existing tables if upgrading an older database."""
    migrations = [
        ("users", "email TEXT"),
        ("users", "phone TEXT"),
        ("users", "created_at TEXT"),
        ("items", "category TEXT"),
        ("items", "min_stock_milli INTEGER NOT NULL DEFAULT 0"),
        ("items", "max_stock_milli INTEGER NOT NULL DEFAULT 0"),
        ("items", "safety_stock_milli INTEGER NOT NULL DEFAULT 0"),
        ("items", "standard_cost_paise INTEGER NOT NULL DEFAULT 0"),
        ("items", "lead_time_days INTEGER NOT NULL DEFAULT 3"),
        ("customers", "email TEXT"),
        ("customers", "contact_person TEXT"),
        ("customers", "credit_limit_paise INTEGER NOT NULL DEFAULT 5000000"),
        ("customers", "payment_terms_days INTEGER NOT NULL DEFAULT 30"),
        ("customers", "active INTEGER NOT NULL DEFAULT 1"),
        ("suppliers", "email TEXT"),
        ("suppliers", "address TEXT"),
        ("suppliers", "contact_person TEXT"),
        ("suppliers", "lead_time_days INTEGER NOT NULL DEFAULT 7"),
        ("suppliers", "rating REAL NOT NULL DEFAULT 5.0"),
        ("suppliers", "payment_terms_days INTEGER NOT NULL DEFAULT 30"),
        ("suppliers", "active INTEGER NOT NULL DEFAULT 1"),
        ("purchases", "po_id INTEGER REFERENCES purchase_orders(id)"),
        ("purchases", "status TEXT NOT NULL DEFAULT 'completed'"),
        ("purchases", "grn_no TEXT"),
        ("purchases", "payment_status TEXT NOT NULL DEFAULT 'unpaid'"),
        ("purchases", "paid_paise INTEGER NOT NULL DEFAULT 0"),
        ("purchases", "notes TEXT"),
        ("stock_ledger", "lot_no TEXT"),
        ("stock_ledger", "quality_status TEXT NOT NULL DEFAULT 'approved'"),
        ("orders", "priority TEXT NOT NULL DEFAULT 'normal'"),
        ("orders", "delivery_date TEXT"),
        ("orders", "dispatched_at TEXT"),
        ("orders", "cancelled_at TEXT"),
        ("orders", "cancel_reason TEXT"),
        ("orders", "lost_sale_recorded INTEGER DEFAULT 0"),
        ("production_runs", "quality_status TEXT NOT NULL DEFAULT 'pending'"),
        ("production_runs", "qa_status TEXT DEFAULT 'pending'"),
        ("production_runs", "quality_inspection_id INTEGER"),
        ("production_runs", "machine_overhead_paise INTEGER NOT NULL DEFAULT 0"),
        ("production_runs", "scheduled_date TEXT"),
        ("quality_inspections", "inspection_type TEXT DEFAULT 'finished_goods'"),
        ("quality_inspections", "target_type TEXT"),
        ("quality_inspections", "target_id INTEGER"),
        ("quality_inspections", "item_id INTEGER REFERENCES items(id)"),
        ("quality_inspections", "reference_type TEXT"),
        ("quality_inspections", "reference_id INTEGER"),
        ("quality_inspections", "inspected_by INTEGER REFERENCES users(id)"),
        ("quality_inspections", "inspector_id INTEGER REFERENCES users(id)"),
        ("quality_inspections", "inspected_at TEXT"),
        ("quality_inspections", "inspection_date TEXT"),
        ("quality_inspections", "sample_size TEXT"),
        ("quality_inspections", "parameters_json TEXT"),
        ("quality_inspections", "defect_category TEXT"),
        ("quality_inspections", "defect_description TEXT"),
        ("quality_inspections", "corrective_action TEXT"),
        ("quality_inspections", "moisture_pct REAL"),
        ("quality_inspections", "seal_integrity TEXT"),
        ("quality_inspections", "aroma_taste TEXT"),
        ("quality_inspections", "weight_check TEXT"),
        ("quality_inspections", "defects_count INTEGER DEFAULT 0"),
        ("quality_inspections", "remarks TEXT"),
        ("quality_inspections", "notes TEXT"),
        ("audit_log", "prev_value TEXT"),
        ("audit_log", "new_value TEXT"),
    ]
    for table, col_def in migrations:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
        except sqlite3.OperationalError:
            pass


def init_db(conn):
    conn.executescript(SCHEMA)
    _migrate_columns(conn)
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
