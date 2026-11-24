# Dakshin ERP (SnackFlow Operating System)
### Enterprise Order-to-Audit Platform for Packaged Food Manufacturing
> *"Every Order. Every Batch. Every Rupee. Connected."*

[![NIT Benchmark](https://img.shields.io/badge/NIT%20Benchmark-14%2F14%20PASS-success?style=for-the-badge&logo=checkmarx)](http://localhost:5000/reports/benchmark)
[![Test Suite](https://img.shields.io/badge/Unit%20Tests-50%2F50%20PASS-blue?style=for-the-badge)](http://localhost:5000)
[![Architecture](https://img.shields.io/badge/Architecture-Zero--Drift%20Stock%20Ledger-7C3AED?style=for-the-badge)](DESIGN.md)
[![Theme](https://img.shields.io/badge/Design%20System-Premium%20Light%20Purple-8B5CF6?style=for-the-badge)](http://localhost:5000)
[![Compliance](https://img.shields.io/badge/GST%20Compliance-Intra%20%7C%20Inter%20State-green?style=for-the-badge)](http://localhost:5000)
[![License](https://img.shields.io/badge/Status-Production%20Ready-brightgreen?style=for-the-badge)](https://github.com/manikishore434-rgb/Dakshin-ERB.git)

---

## 📌 Executive Summary & Academic Context

**Dakshin ERP** is a full-stack, enterprise-grade manufacturing execution, inventory management, field sales, and statutory audit platform. Architected in response to the **National Institute of Technology, Tiruchirappalli (NIT-T) Winter Internship Problem Statement** (*Centre for Digital Infrastructure*), it replaces fragmented paper logs, notebook tallies, and phone orders with a single unified system where every transaction is entered once at its physical source and flows automatically into perpetual ledgers, costing engines, and audit accounts.

The core challenge resolved is linking the **Sales Loop** and the **Production Loop** at finished-goods inventory with **zero numerical drift**:
- **Sales Loop:** Field salesman mobile order $\to$ Admin price/stock verification $\to$ GST tax invoice (PDF) $\to$ Dispatch (inventory deducted) $\to$ Receivables tracking $\to$ Payment collections.
- **Production Loop:** Purchase inwarding $\to$ Raw material issue against Bill of Materials (BOM) $\to$ Production batch run $\to$ Actual output & scrap recording $\to$ Finished goods inventory addition $\to$ Planned vs actual variance alerts & cost-per-packet calculation.

---

## 🚀 Quick Start & Run Commands

### 1. Local Python Environment (Windows, macOS, Linux)
```bash
# 1. Clone repository
git clone https://github.com/manikishore434-rgb/Dakshin-ERB.git
cd Dakshin-ERB

# 2. Activate virtual environment (Windows PowerShell)
.\venv\Scripts\Activate.ps1
# On Linux/macOS: source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt gunicorn

# 4. Launch the application (Auto-seeds Section 5 benchmark data)
python run.py
```
Access the application at: **`http://localhost:5000`**

### 2. Containerized Deployment (Docker & Compose)
```bash
docker compose up --build -d
```
The application will launch with container health checks and volume-backed database persistence.

### 3. Automated Benchmark Verification (NIT Section 5 Scenario)
```bash
python -m app.benchmark
```
*Expected: **14 / 14 checks passed (100% compliance)** with zero decimal drift.*

### 4. Automated Enterprise Test Suite (50 Tests)
```bash
python -m unittest discover -s tests -v
```
*Expected: **Ran 50 tests in ~15s - OK***

---

## 🔑 Pre-Seeded Demonstration Personas

The platform comes pre-seeded with 5 distinct role-based logins (Password for all: `demo123`):

| Role Persona | Username | Default Portal | Key Capabilities |
|---|---|---|---|
| **Executive Owner** | `owner` | `/owner/suite` | Control Tower, enterprise valuation, macro variance alerts |
| **Factory Admin** | `admin` | `/admin/orders` | Order verification, GST tax invoices, payment logging, customer master |
| **Production Supervisor** | `production` | `/production/runs` | BOM material issue, batch output, packaging scrap, QA inspections |
| **Field Salesman A** | `salesman_a` | `/sales/order/new` | Mobile order entry (Retailer A), sales history, GPS visit log |
| **Field Salesman B** | `salesman_b` | `/sales/order/new` | Mobile order entry (Distributor B), shortage detection |
| **Accountant / Auditor** | `accountant` | `/reports` | 14 statutory reports, GSTR-1/3B summary, Tally Prime XML export |

> **Evaluator Tip:** Switch between roles instantly at any time using the **"Switch Persona (Demo)"** dropdown in the sidebar or via the interactive **5-Role Persona Hub** at `/roles`.

---

## 📊 Section 5 Mandatory NIT Trichy Benchmark Results

| Benchmark Checkpoint | Expected Output | Actual ERP Result | Verification Status |
|---|---|---|---|
| **Flour Closing Stock** | `120 kg` (100 + 60 − 40) | `120 kg` | **PASS** |
| **Cooking Oil Closing Stock** | `19.5 L` (30 − 10.5) | `19.5 L` | **PASS** |
| **Pouches Closing Stock** | `306` (500 − 188 − 6) | `306` | **PASS** |
| **Finished Goods Post-Run** | `238 pkts` (50 + 188) | `238 pkts` | **PASS** |
| **Finished Goods Post-Dispatch** | `88 pkts` (238 − 150) | `88 pkts` | **PASS** |
| **Production Yield Variance** | `-6.00%` (188 vs 200 expected) | `-6.00%` (Flagged) | **PASS** |
| **Oil Consumption Variance** | `+5.00%` (10.5 L vs 10.0 L BOM) | `+5.00%` (Flagged) | **PASS** |
| **Retailer A Taxable Amount** | `₹7,500.00` (150 pkts @ ₹50) | `₹7,500.00` | **PASS** |
| **Retailer A CGST & SGST** | `₹187.50 / ₹187.50` (Intra-state TN) | `₹187.50 / ₹187.50` | **PASS** |
| **Retailer A Total Invoice** | `₹7,875.00` | `₹7,875.00` | **PASS** |
| **Retailer A Outstanding Dues** | `₹3,875.00` (after ₹4,000 payment) | `₹3,875.00` | **PASS** |
| **Distributor B Shortage** | `32 pkts short` (120 ordered vs 88 stock) | `32 pkts short` | **PASS** |
| **Distributor B Tax Type** | `IGST ₹300.00` (Inter-state KA) | `IGST ₹300.00` | **PASS** |
| **Distributor B Dispatch Block** | `Blocked` (Prevent negative inventory) | `Blocked` | **PASS** |
| **Cost Per Packet with Overheads** | Material ₹4,055 + Overheads ₹1,800 | **₹31.14 / pkt (37.7% margin)** | **PASS** |

---

## 🎨 Enterprise Premium Light Purple Design System

The application features a modern SaaS interface built with the exact enterprise specifications:
- **Main Background:** `#F8F7FF`
- **Sidebar & Card Surfaces:** `#FFFFFF`
- **Primary Brand Purple:** `#7C3AED`
- **Secondary Purple:** `#8B5CF6`
- **Lavender Accents:** `#EDE5FF` & `#F3EEFF`
- **Primary Typography:** `#27213A` (Plus Jakarta Sans)
- **Secondary Text:** `#77718A`
- **Borders & Dividers:** `#E9E3F5`
- **Semantic Accents:** Success `#16A34A`, Warning `#F59E0B`, Danger `#DC2626`
- **Responsive Layout:** Adaptive desktop sidebar, tablet layouts, and mobile bottom drawer for field salesmen.

---

## 🏛️ Comprehensive Enterprise Modules

1. **Role-Based ERP & Security (RBAC):** Backend-enforced access control across Owner, Admin, Salesman, Production Supervisor, and Accountant.
2. **Sales & Field Order Management:** Fast mobile order taking, client-UUID idempotency, customer-specific pricing, and GPS visit check-ins.
3. **GST & Invoicing Engine:** Automated Place of Supply detection (Intra-state CGST+SGST vs Inter-state IGST), FY-sequenced numbering (`INV/2026-27/0001`), ReportLab PDF invoices, and credit note workflows.
4. **BOM & Production Engine:** Multi-ingredient recipe definitions, standard batch sizing, actual consumption vs BOM variance calculation with tolerance breach flags.
5. **Zero-Drift Perpetual Inventory:** 4 categories (Raw materials, Packaging, WIP, Finished goods), lot numbers, FEFO dispatch, and reorder point (ROP) monitoring.
6. **Procurement & Vendor Management:** Purchase orders, GRN material inwarding, supplier ratings, lead time tracking, and supplier outstanding payables.
7. **Costing & Profit Analysis:** Direct raw material cost, packaging cost, labor & power overhead allocation, unit cost per packet, and customer margin rankings.
8. **Statutory Auditor Workspace:** 14 monthly reports (Sales Register, Purchase Register, GSTR-1/3B summary, Stock Ledger, Variance Report, Aging Analysis, Tally Prime XML export).
9. **Advanced Business Intelligence:** Real-time MRP planner, demand forecasting, profit leakage detection, cash flow simulator, and digital audit trail.
10. **Bilingual Floor Interface:** Instant one-click language toggle between English and Tamil (தமிழ்).

---

## 📚 Complete Project Documentation

| Document | Purpose |
|---|---|
| [INSTALLATION.md](file:///C:/Users/Pradeepan/Downloads/Order-to-Audit-Enhanced/order-to-audit/INSTALLATION.md) | Local setup, virtual environment, and troubleshooting |
| [API_DOCUMENTATION.md](file:///C:/Users/Pradeepan/Downloads/Order-to-Audit-Enhanced/order-to-audit/API_DOCUMENTATION.md) | REST & Web endpoints, schemas, status codes, and query params |
| [DATABASE_SCHEMA.md](file:///C:/Users/Pradeepan/Downloads/Order-to-Audit-Enhanced/order-to-audit/DATABASE_SCHEMA.md) | Entity-relationship dictionary, integer-paisa logic, and schema |
| [ARCHITECTURE.md](file:///C:/Users/Pradeepan/Downloads/Order-to-Audit-Enhanced/order-to-audit/ARCHITECTURE.md) | Layered modular architecture, dual-loop synchronization, sequence flows |
| [DESIGN_NOTE.md](file:///C:/Users/Pradeepan/Downloads/Order-to-Audit-Enhanced/order-to-audit/DESIGN_NOTE.md) | Official 2-page design note required by NIT Trichy Section 8.3 |
| [DEPLOYMENT_GUIDE.md](file:///C:/Users/Pradeepan/Downloads/Order-to-Audit-Enhanced/order-to-audit/DEPLOYMENT_GUIDE.md) | Production deployment on Render, Docker Compose, Ubuntu Nginx, backups |
| [TESTING_REPORT.md](file:///C:/Users/Pradeepan/Downloads/Order-to-Audit-Enhanced/order-to-audit/TESTING_REPORT.md) | 50 automated tests matrix, assertions, and benchmark verification table |
| [ASSUMPTIONS_AND_LIMITATIONS.md](file:///C:/Users/Pradeepan/Downloads/Order-to-Audit-Enhanced/order-to-audit/ASSUMPTIONS_AND_LIMITATIONS.md) | Statutory assumptions, place of supply rules, and technical roadmap |

---

## 🌐 Public Repository & Publishing

- **GitHub Repository:** [https://github.com/manikishore434-rgb/Dakshin-ERB.git](https://github.com/manikishore434-rgb/Dakshin-ERB.git)
- **Originating Problem Statement:** Centre for Digital Infrastructure, National Institute of Technology, Tiruchirappalli (NIT-T).
