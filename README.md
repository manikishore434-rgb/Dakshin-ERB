# DakshinERP: Intelligent Order-to-Audit Food Manufacturing OS

> **Centre for Digital Infrastructure, National Institute of Technology, Tiruchirappalli (NIT-T)**  
> *Winter Internship Shortlisting Task: Order-to-Audit System for a Small Food Manufacturer*

DakshinERP is a production-grade, full-stack Enterprise Resource Planning (ERP) platform architected specifically for small-scale packaged food manufacturers (murukku, mixture, banana chips, sweets). It unifies field sales order collection, recipe-based batch manufacturing (Bill of Materials), stock ledger accounting, GST billing, and auditor-ready reporting into one seamless, zero-drift operating system.

---

## 🚀 Quick Start & Run Commands

### 1. Local Run (Single Command)
```bash
# 1. Activate environment and install dependencies
pip install -r requirements.txt

# 2. Launch application server (Auto-initializes SQLite DB and master data)
python run.py
```
Access the application at: **`http://localhost:5000`**

### 2. Containerized Deployment (Docker Compose)
```bash
docker compose up --build
```

### 3. Automated Benchmark Verification (Section 5)
```bash
python -m app.benchmark
```
*Executes all 9 steps of the mandatory NIT Tiruchirappalli benchmark in-memory and validates 14 checkpoints.*

### 4. Automated Test Suite
```bash
python -m unittest discover -s tests -t .
```
*Runs 24 comprehensive unit tests covering decimal precision, ledger balance integrity, tax calculations, and HTTP workflows.*

---

## 👥 Test Personas & User Logins

All test accounts share the password: **`demo123`**

| Role | Username | Device Persona | Primary Responsibilities |
|---|---|---|---|
| **Salesman (Intra-state)** | `salesman_a` | Mobile phone | Field order entry for Retailer A (TN), offline caching, GPS visit log |
| **Salesman (Inter-state)** | `salesman_b` | Mobile phone | Field order entry for Distributor B (Karnataka), shortage alerts |
| **Factory Admin** | `admin` | Desktop | Order verification, stock reservation, GST invoices, dispatch, payments |
| **Production Supervisor**| `production` | Floor tablet/PC| Raw material receipts, batch runs against BOM, output & wastage recording |
| **Accountant / Auditor** | `accountant` | Desktop (Audit)| Sales register, GSTR-1/3B summary, stock ledger, aging, Tally Prime XML |
| **Executive Owner** | `owner` | Any device | Cockpit KPIs: orders today, unit cost per packet, yield flags, outstanding |

---

## 🏛️ Business Architecture & Dual-Loop Mechanics

DakshinERP ties the physical food factory floor to the financial ledger by harmonizing two core operational loops that intersect at **Finished Goods Stock**:

```
                       SALES LOOP (Order-to-Cash)
   [Salesman Mobile] ──> Order Placed
                              │
   [Admin Verification] ──> Stock Check (Available vs Reserved)
                              │
   [GST Billing Engine] ──> Tax Invoice (CGST+SGST or IGST) ──> Receivables Ledger
                              │
   [Dispatch Desk] ────────> Physical Dispatch ──┐
                                                 │
                                                 ▼
                                     ┌───────────────────────┐
                                     │ FINISHED GOODS STOCK  │
                                     │  (Zero-Drift Ledger)  │
                                     └───────────────────────┘
                                                 ▲
                                                 │
   [Raw Material Store] ───> Purchase Receipt ───┤
                                                 │
   [Batch Creation] ───────> Standard BOM Expand │
                                                 │
   [Floor Execution] ──────> Material Issue & Consumption
                                                 │
   [Output & Wastage] ─────> Good Packets Added ─┘
                     PRODUCTION LOOP (Recipe-to-Stock)
```

1. **Sales Loop:** Field salesman places order $\to$ Admin verifies stock against available inventory $\to$ System raises GST-compliant tax invoice $\to$ Dispatch decrements finished-goods stock ledger $\to$ Payment collection tracks customer receivables and aging.
2. **Production Loop:** Purchase inward increases raw stock $\to$ Raw materials issued against BOM recipe $\to$ Actual output & scrap recorded $\to$ Finished packets increment stock ledger $\to$ Variance and unit cost per packet computed.

---

## 📊 Section 5 Mandatory Benchmark Scenario Verification

Every submission must execute the exact Section 5 benchmark scenario end-to-end. DakshinERP achieves **100% PASS** on all 14 mandatory checks:

| # | Check Item | NIT Expected Value | DakshinERP System Result | Status |
|---|---|---|---|:---:|
| 1 | **Flour closing balance** | 120 kg (100 + 60 − 40) | **120.0 kg** | ✅ **PASS** |
| 2 | **Oil closing balance** | 19.5 L (30 − 10.5) | **19.5 L** | ✅ **PASS** |
| 3 | **Pouches closing balance** | 306 pcs (500 − 194) | **306 pcs** | ✅ **PASS** |
| 4 | **Finished goods after run** | 238 pkts (50 + 188) | **238 pkts** | ✅ **PASS** |
| 5 | **Finished goods after dispatch** | 88 pkts (238 − 150) | **88 pkts** | ✅ **PASS** |
| 6 | **Yield variance** | 188 vs 200 expected (−6.00%) | **−6.00% (Flagged &gt; 3%)** | ✅ **PASS** |
| 7 | **Oil consumption variance** | 10.5 L vs 10.0 L (+5.00%) | **+5.00% (Flagged &gt; 3%)** | ✅ **PASS** |
| 8 | **Retailer A taxable value** | ₹7,500.00 | **₹7,500.00** | ✅ **PASS** |
| 9 | **Retailer A CGST / SGST (2.5% each)**| ₹187.50 / ₹187.50 | **₹187.50 / ₹187.50** | ✅ **PASS** |
| 10 | **Retailer A invoice total** | ₹7,875.00 | **₹7,875.00** | ✅ **PASS** |
| 11 | **Retailer A outstanding balance** | ₹3,875.00 (7,875 − 4,000) | **₹3,875.00** | ✅ **PASS** |
| 12 | **Distributor B shortage check** | Shortage of 32 packets | **Short by 32 pkts (Make 1 batch)** | ✅ **PASS** |
| 13 | **Distributor B tax structure** | IGST 5.0% applies (Karnataka)| **IGST ₹300.00 on ₹6,000.00** | ✅ **PASS** |
| 14 | **Distributor B dispatch guard** | Blocked on negative stock | **Dispatch Strictly Blocked** | ✅ **PASS** |

### Cost per Packet Economics (Murukku 200g)
* **Raw Material & Packaging Costs:**
  * Flour: 40 kg @ weighted-average ₹43.125/kg = **₹1,725.00**
  * Cooking Oil: 10.5 L @ ₹140.00/L = **₹1,470.00**
  * Spice Mix: 1.2 kg @ ₹200.00/kg = **₹240.00**
  * 200g Pouches: 194 pcs (188 good + 6 damaged) @ ₹2.50 = **₹485.00**
  * Packaging Cartons: 9 pcs @ ₹15.00 = **₹135.00**
  * *Material Subtotal:* **₹4,055.00**
* **Direct Production Overheads:**
  * Labour: **₹1,200.00**
  * Power & Gas: **₹600.00**
  * *Overheads Subtotal:* **₹1,800.00**
* **Total Run Cost:** ₹4,055.00 + ₹1,800.00 = **₹5,855.00**
* **Final Cost per Packet:** ₹5,855.00 ÷ 188 good packets = **₹31.14 per packet**
* **Gross Margin:** Benchmark selling price ₹50.00 − ₹31.14 = **₹18.86 per packet (37.7% margin)**

---

## 🎯 Feature Coverage Against Section 6 Tiers

### 1. Must Have (Core Engine) — 100% Completed
- [x] **Role-Based Access Control:** Strict server-side decorators (`@login_required`) for 5 distinct roles.
- [x] **Master Data Catalogs:** Items, BOM recipes, Customers, Suppliers, Customer-Specific Pricing.
- [x] **Mobile-Friendly Field Ordering:** Fast order creation, product search, touch steppers, price list binding.
- [x] **Admin Verification & Stock Check:** Real-time visibility into on-hand, reserved, and shortage quantities before order approval.
- [x] **GST Tax Invoices as PDF:** ReportLab-generated tax invoice with HSN, GSTIN, place of supply, and amount in words.
- [x] **Automated Stock Ledger Production Runs:** Starts run, issues materials, completes output, credits finished goods.
- [x] **Planned vs Actual Consumption & Yield:** Real-time variance computation with configurable threshold alerts.
- [x] **Stock Reconciliation & Ledger:** Full traceability where opening + receipts − issues/sales ± adjustments = closing.
- [x] **Sales & Stock Reports:** Date-filterable with CSV, Excel (.xlsx), and PDF exports.

### 2. Should Have — 100% Completed
- [x] **Purchases & Supplier Records:** Inward receipts updating weighted-average unit valuation and batch tracking.
- [x] **Payments, Outstanding & Ageing:** Payment collection against specific invoices with 0-30, 31-60, 60+ days aging buckets.
- [x] **Unit Costing with Overheads:** Run-specific overhead absorption and monthly shared overhead pools.
- [x] **GST Summary Report:** Pre-formatted reports mapping directly to GSTR-3B Table 3.1(a) and GSTR-1 Table 12 HSN tables.
- [x] **Variance Tolerance Alerts:** Automatic dashboard flags and audit warnings whenever variance exceeds 3%.
- [x] **Executive Owner Dashboard:** Real-time cockpit featuring KPI analytics cards and pipeline visual funnel.

### 3. Stretch Goals Implemented
- [x] **Offline Order Capture & Auto-Sync:** Service worker + `localStorage` queue with client-generated UUID idempotency.
- [x] **Batch & Expiry Date Tracking:** Inward materials and completed finished goods carry batch numbers and expiry dates.
- [x] **Reorder Safety Stock Alerts:** Automatic warnings when on-hand stock breaches safety thresholds.
- [x] **Production Planning from Pending Shortages:** System computes required batches (e.g. "make 1 batch to cover shortage").
- [x] **GPS Sales Visit Log:** Browser geolocation capture with timestamp and OpenStreetMap verification links.
- [x] **Tally Prime Compatible XML Export:** Voucher-oriented XML generator for posted sales invoices.
- [x] **Bilingual Interface (English / தமிழ்):** Language toggle for shared navigation and key terminology.

---

## 🛠️ Technical Stack & Architectural Justification

1. **Python 3.10+ / Flask:**
   * Delivers ultra-fast server-rendered HTML pages that load instantaneously even on 2G/3G field connections.
   * Business logic lives in clean, decoupled service modules (`app/services/`) that can be tested headless without web framework dependencies.
2. **SQLite with Strict Foreign Keys & ACID Transactions:**
   * Eliminates complex external database dependencies. Stock balances are **never** stored as static mutable fields; they are strictly derived from `SUM(stock_ledger)`.
   * Atomic transactions (`with tx(db):`) guarantee that a failed production run or invoice never leaves orphaned records.
3. **Paisa & Milli-Unit Integer Arithmetic:**
   * Money is stored in integer **paise** (₹1 = 100 paise) and weights/volumes in integer **milli-units** (1 kg = 1,000 milli-units).
   * Prevents floating-point rounding drift across multi-line tax and inventory calculations.
4. **ReportLab & OpenPyXL:**
   * Generates vector PDF tax invoices and native binary Excel spreadsheets on the server without headless browser overhead.

---

## 📁 Repository Directory Structure

```
dakshin-erp/
├── app/
│   ├── services/           # Core Decoupled Business Logic
│   │   ├── stock.py        # Ledger balance, movements, valuation engine
│   │   ├── production.py   # BOM recipe expansion, variance, costing
│   │   ├── sales.py        # Order lifecycle, GST calculation, dispatch
│   │   ├── reports.py      # GSTR-1/3B, stock summary, ageing, Tally XML
│   │   └── invoice_pdf.py  # ReportLab vector PDF generator
│   ├── views/              # Role-Based HTTP Blueprints
│   │   ├── auth.py         # Login, logout, role switcher, bilingual toggle
│   │   ├── sales.py        # Salesman mobile order taking & GPS check-in
│   │   ├── admin.py        # Verification, billing, dispatch, master data
│   │   ├── production.py   # Shop floor batch runs & receipts
│   │   └── reports.py      # Executive dashboard, auditor reports, benchmark UI
│   ├── static/             # Assets, CSS Design System, Service Worker
│   │   ├── style.css       # Enterprise dark/light responsive CSS system
│   │   ├── order.js        # Offline order taking & background sync engine
│   │   ├── sw.js           # PWA offline cache service worker
│   │   └── manifest.json   # PWA web app manifest
│   ├── templates/          # Jinja2 Enterprise Layouts
│   │   ├── base.html       # Responsive app shell with sidebar & mobile nav
│   │   ├── benchmark.html  # Section 5 interactive compliance dashboard
│   │   ├── login.html      # 1-Click persona login portal
│   │   ├── admin/          # Orders, invoices, payments, master data
│   │   ├── prod/           # Runs, recipe execution, receipts
│   │   ├── reports/        # Executive dashboard, report views
│   │   └── sales/          # Field order creation, orders, sales, GPS
│   ├── benchmark.py        # Headless Section 5 benchmark test script
│   ├── db.py               # SQLite schema with foreign keys and indexes
│   ├── seed.py             # Section 5 starting master data seeder
│   └── util.py             # Formatting, currency, and date helpers
├── tests/                  # Automated Test Suite (24 unit tests)
│   ├── test_benchmark.py   # Benchmark end-to-end unit test
│   ├── test_rules.py       # Stock rules, tax rounding, and HTTP flows
│   ├── test_stock.py       # Zero-drift ledger balance tests
│   └── test_tax.py         # Intra/inter-state GST half-up rounding tests
├── data/                   # SQLite database storage (oto.db)
├── Dockerfile              # Production Docker container image
├── docker-compose.yml      # Multi-container orchestration
├── DESIGN.md               # 2-Page Architectural Design & ER Diagram Note
├── README.md               # Complete System Documentation
├── requirements.txt        # Python dependency manifest
└── run.py                  # Single-command server entry point
```
