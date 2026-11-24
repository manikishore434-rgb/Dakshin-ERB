# Comprehensive Demo Walkthrough Guide: SnackFlow ERP

> **SnackFlow ERP**  
> *Smart Manufacturing, Sales, Inventory, Finance and Audit Intelligence System*  
> **Tagline:** *"From Order to Audit. Every Transaction Connected."*  
> **Originating Benchmark:** Centre for Digital Infrastructure, National Institute of Technology, Tiruchirappalli (NIT-T)  
> **Application URL:** `http://localhost:5000`  
> **Default Password:** `demo123` for all users

---

## 👥 Demo Personas & Fast Switcher

All accounts use the password: **`demo123`**. You can also switch instantly using the **Switch Persona** selector in the bottom-left of the navigation sidebar.

| Role | Username | Best For Demonstrating |
|---|---|---|
| **Executive Owner** | `owner` | Smart Factory Control Tower, Simulators, AI Assistant, Profitability |
| **Factory Admin** | `admin` | Order verification, GST invoicing, Production planning, Dispatches |
| **Production Supervisor** | `production` | Material receipts, Batch runs (BOM), QC inspections, Wastage tracking |
| **Salesman (Intra-state)** | `salesman_a` | Mobile field order entry for Retailer A (Tamil Nadu), GPS visit log |
| **Salesman (Inter-state)** | `salesman_b` | Field order for Distributor B (Karnataka), shortage warning |
| **Accountant / Auditor** | `accountant` | GSTR-1/3B summaries, Tally Prime XML, Audit Readiness, Traceability |

---

## ⏱️ Walkthrough Schedule & Demonstration Script

---

### PART 1: The Mandatory NIT Tiruchirappalli Section 5 Benchmark (Minutes 0:00 – 4:00)

#### Step 1: Raw Material Inward Purchase (Production Supervisor)
1. **Login as:** `production`
2. **Navigation:** Sidebar $\to$ **Purchases** $\to$ **+ New Purchase (GRN)**.
3. **Data Entry:**
   * Supplier: `Sri Lakshmi Flour Mills`
   * Invoice / Bill No: `FL-001`
   * Line 1 Item: `Flour (kg)`
   * Quantity: `60` | Unit: `kg` | Rate: `₹45.00`
4. **Click:** **Save Material Receipt**.
5. **Key Talking Point:**
   > *"We record 60 kg of flour purchased at ₹45/kg. The system immediately calculates our perpetual weighted average cost: 100 kg opening at ₹42 + 60 kg at ₹45 yields exactly ₹43.125/kg."*

#### Step 2 & 3: Production Run, BOM Consumption & Variance Alert
1. **Navigation:** Sidebar $\to$ **Production** $\to$ **+ Start New Run**.
2. **Data Entry:**
   * Product: `Murukku 200 g` | Batch Count: `1`
   * Observe standard BOM recipe pre-filled: 40 kg flour, 10 L oil, 1.2 kg spice mix.
   * Modify Cooking Oil Issued: Change from `10.0` to `10.5` L (+0.5 L over standard).
3. **Click:** **Start Production Run & Deduct Raw Materials**.
4. **On Run Detail Page $\to$ Record Output:**
   * Good Finished Packets: `188`
   * Damaged Pouches / Scrap: `6`
   * Packaging Cartons Used: `9`
5. **Click:** **Save Output & Update Stock Ledger**.
6. **Key Talking Point:**
   > *"The system immediately detects and highlights two variances exceeding our 3% tolerance threshold: Yield variance of −6.00% (188 good vs 200 standard) and Cooking Oil consumption variance of +5.00% (10.5 L vs 10 L). The immutable stock ledger automatically credits 188 finished packets and deducts 194 pouches (188 good + 6 damaged) and 9 cartons."*

#### Step 4: Mobile Field Order Entry (Salesman A)
1. **Login as:** `salesman_a` (or use Persona Switcher).
2. **Screen:** Mobile New Field Order.
3. **Data Entry:**
   * Customer: `Retailer A (retailer, Tamil Nadu)`
   * Line Item: `Murukku 200 g` | Quantity: `150` packets
   * Notice dynamic pre-tax total: `₹7,500.00` (150 pkts × ₹50.00).
4. **Click:** **Submit Order to Factory Desk**.
5. **Key Talking Point:**
   > *"Salesman A enters the field order with touch controls. The application supports offline local storage queueing and GPS location logging."*

#### Step 5: Admin Stock Verification, GST Invoicing & Dispatch
1. **Login as:** `admin`
2. **Navigation:** Sidebar $\to$ **Orders** $\to$ Open order for `Retailer A`.
3. **Verification:**
   * Stock Status: *On-Hand: 238 pkts | Reserved: 0 | Available: 238 pkts*. Status: **Fully Covered**.
4. **Actions:**
   * Click **Authorize & Approve Order**.
   * Click **Generate GST Tax Invoice**.
   * Inspect the invoice breakdown: Intra-state supply (`33, Tamil Nadu`) $\implies$ CGST (2.5%) = `₹187.50`, SGST (2.5%) = `₹187.50`, Total = `₹7,875.00`.
   * Click **Download Official GST Invoice PDF** (clean vector PDF with HSN, GSTIN, and amount in words).
   * Click **Record Dispatch (Deduct Stock)**.
5. **Key Talking Point:**
   > *"Admin verifies stock availability in real-time. Upon dispatch, finished goods stock decrements from 238 down to 88 packets."*

#### Step 6: Out-of-State Order & Negative Stock Dispatch Guard (Salesman B)
1. **Login as:** `salesman_b`
2. **Action:** Place order for `Distributor B (distributor, Karnataka)` for `120` packets of `Murukku 200 g`.
3. **Switch to:** `admin` $\to$ Open the order.
4. **Key Verification:**
   * The system alerts: **SHORT by 32 pkts** (Available 88 vs Required 120 pkts).
   * Suggests: *"Requires 1 more batch to fulfill."*
   * Shows interstate tax calculation: **IGST 5.0% = ₹300.00** on ₹6,000.00.
   * Attempt dispatch: Physical dispatch button is **strictly blocked** to prevent negative inventory!

#### Step 7 & 8: Payment Collection & Unit Costing Economics
1. **Navigation:** Sidebar $\to$ **Payments** $\to$ **+ Record Payment**.
   * Customer: `Retailer A` | Invoice: `INV/...` | Amount: `4000.00` | Mode: `UPI`
   * Click **Save Receipt**.
   * Outstanding balance updates instantly to exactly **₹3,875.00** (₹7,875.00 − ₹4,000.00).
2. **Navigation:** Open production run in **Production** $\to$ Add Direct Overheads:
   * Direct Labour: `₹1,200.00` | Power/Gas: `₹600.00`
   * Review Cost per Packet Card:
     * Material: ₹4,055.00 + Overheads: ₹1,800.00 = Total ₹5,855.00.
     * **Cost per Packet:** `₹5,855.00 ÷ 188 pkts = ₹31.14 per packet`.
     * **Gross Profit Margin:** `₹50.00 − ₹31.14 = ₹18.86 per packet (37.7% margin)`.

#### Step 9: 1-Click NIT Benchmark Verification
1. Click the top-bar badge **NIT Benchmark: 14/14 PASS** (or visit `/reports/benchmark`).
2. Show all 14 checkpoints validated live with green checkmarks!

---

### PART 2: Advanced Intelligence Modules (Minutes 4:00 – 10:00)

#### 1. Smart Factory Control Tower (`/intel/control-tower`)
* **Login as:** `owner`
* **Showcase:**
  * Interactive business workflow funnel from Order to Audit.
  * Real-time metrics: Orders today, gross margin %, pending dispatches, inventory health score, unfulfilled orders, active critical alerts.
  * Rapid shortcuts into Production Planning, Reorder Predictor, and Traceability.

#### 2. Order-to-Production Planning (`/intel/planner`)
* **Showcase:**
  * Open the pending shortage for Distributor B (short by 32 packets).
  * System calculates production gap and explodes the BOM: Flour needed, Oil needed, Pouches needed.
  * Shows material availability vs shortage and estimated batch cost.
  * Click **Save Production Plan** $\to$ Changes status from `proposed` to `approved` and queues the shop floor batch.

#### 3. Inventory Health Intelligence (`/intel/inventory-health`)
* **Showcase:**
  * Explainable 0-100 Health Score broken into 4 dimensions:
    1. Shortage & Fill Rate (30 pts)
    2. Stockout Risk & Runway (25 pts)
    3. Overstock & Dead Stock (25 pts)
    4. Expiry Risk (20 pts)
  * Item-by-item breakdown showing stock velocity (Fast, Steady, Slow, Dead) and runway days.

#### 4. Smart Reorder Predictor (`/intel/reorder-predictor`)
* **Showcase:**
  * Daily burn rate analysis based on historical production and open orders.
  * Shows Reorder Point (ROP), safety stock, and recommended reorder quantity.
  * 1-Click action to convert approved recommendations into Purchase Requisitions.

#### 5. Advanced Batch, FEFO & QR Verification (`/intel/batches`)
* **Showcase:**
  * Live list of all active raw material and finished goods batches with expiry dates.
  * Click **Batch Card & QR Code** for any batch:
    * Displays a printable batch passport with batch metadata, QC status, and scannable QR code.
  * Open `/intel/batch-verify/<batch_no>`:
    * Mobile-ready instant verification interface displaying product authenticity, manufacturing date, and expiry validation.

#### 6. Material Wastage & Root Cause Analysis (`/intel/wastage` & `/intel/rca`)
* **Showcase:**
  * Material wastage ranking: Highest scrap materials and cost of waste in rupees.
  * Click into **Root Cause Analysis (RCA)**:
    * Automated diagnostic rules correlate the oil variance (+5.00%) and yield deficit (-6.00%) to operational parameters (e.g. moisture content, fryer temperature, pouch sealing pressure).

#### 7. Product Profitability & Profit Leakage (`/intel/profitability` & `/intel/profit-leakage`)
* **Showcase:**
  * Packet-level unit economics breakdown showing pre-tax revenue, raw materials, packaging, labour, power, and net margin per packet.
  * Profit Leakage detector flags hidden costs: Damaged pouches, excess oil absorption, overdue customer credit interest loss.

#### 8. Business Simulators (`/intel/simulator/what-if` & `/intel/simulator/continuity`)
* **Showcase:**
  * **What-If Simulator:** Dynamically adjust sliders for Flour price (+15%), Cooking Oil (+20%), or Selling Price (+₹5.00). System models pro-forma monthly profit changes in real-time with zero risk to live ledger data.
  * **Business Continuity Simulator:** Stress-tests supplier shutdown or 10-day power outage scenarios.

#### 9. Deterministic AI Business Assistant (`/intel/ai-assistant`)
* **Showcase:**
  * Ask natural language business queries:
    * *"What is our inventory health score?"*
    * *"Which raw materials need reordering?"*
    * *"What is the cost per packet of Murukku?"*
    * *"Show overdue customer receivables."*
  * Delivers exact, deterministic responses backed directly by database queries.

#### 10. Audit Readiness, Traceability & Recalls (`/intel/audit-readiness` & `/intel/traceability`)
* **Showcase:**
  * **6-Pillar Audit Readiness Scorecard:** Ledger integrity, GST matching, voucher verification, document compliance.
  * **End-to-End Traceability Search:** Enter batch `BATCH-202611-0001` or invoice `INV/2026-27/0001` $\to$ View complete graph linking supplier PO, GRN, production run, finished batch, customer invoice, and payment receipt.
  * **Document Vault:** Centralized repository for FSSAI licenses, lab test certificates, and GST returns.
  * **Download Audit Package:** One-click generation of a consolidated ZIP containing GST summaries, stock ledger Excel sheets, and audit verification certificates.
  * **Daily Closing:** Formal end-of-day statutory sign-off reconciling cash, invoices, dispatches, and ledger movements.
