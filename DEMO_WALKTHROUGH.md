# Demo Video Walkthrough Guide: Section 5 Benchmark Scenario

> **Target Duration:** 6 – 8 Minutes  
> **Application URL:** `http://localhost:5000`  
> **Default Password:** `demo123` for all users

This script provides the exact minute-by-minute walkthrough to record your submission demo video, showcasing the mandatory Section 5 benchmark from the mobile salesman, floor supervisor, factory admin, and auditor perspectives.

---

## ⏱️ Video Timeline & Step-by-Step Script

### Minute 0:00 – 0:45 | Introduction & Architecture Overview
* **Action:** Start on the Login Screen (`http://localhost:5000/login`).
* **Visuals:** Highlight the **DakshinERP** branding, NIT Tiruchirappalli subtitle, and the 1-Click Persona Login selector.
* **Talking Points:**
  * "Welcome to DakshinERP, an intelligent Order-to-Audit Operating System designed for small-scale South Indian packaged food manufacturers."
  * "The core challenge is bridging two operational loops: the **Sales Loop** (Order $\to$ Verification $\to$ GST Invoice $\to$ Dispatch $\to$ Receivables) and the **Production Loop** (Purchases $\to$ BOM Issue $\to$ Output $\to$ Stock $\to$ Costing). Both meet at the immutable Finished Goods Stock Ledger."

---

### Minute 0:45 – 1:30 | Step 1: Raw Material Purchase (Production Supervisor)
* **Login as:** `production` (Click *Production Supervisor* on login page)
* **Navigation:** Click **Material Receipts** in the sidebar.
* **Input Actions:**
  * Supplier: Select `Sri Lakshmi Flour Mills`
  * Supplier Invoice: `FL-001`
  * Line 1 Item: `Flour (kg)`
  * Qty: `60` | Unit: `kg` | Rate: `45`
  * Click **Save Material Receipt**.
* **Talking Points:**
  * "We record the inward purchase of 60 kg of flour at ₹45/kg. This establishes our perpetual weighted-average inventory valuation: 100 kg opening at ₹42 plus 60 kg at ₹45 yields an exact weighted average rate of ₹43.125/kg."

---

### Minute 1:30 – 2:30 | Step 2 & 3: Production Run, BOM Issue & Yield Variance
* **Navigation:** Click **Batch Runs (BOM)** $\to$ **+ Start New Run**.
* **Input Actions:**
  * Product: `Murukku 200 g` | Batches: `1`
  * Observe pre-filled BOM: Standard recipe shows 40 kg flour, 10 L oil, 1.2 kg spices.
  * Adjust Oil Issued: Change Cooking Oil from `10` to `10.5` L (+0.5 L over standard).
  * Click **Start Production Run & Deduct Raw Materials**.
* **On the Run Detail Page:**
  * Scroll to **Record Output**:
    * Good Finished Packets: `188`
    * Damaged Pouches / Wastage: `6`
    * Cartons Used: `9`
    * Click **Save Output & Update Stock Ledger**.
* **Talking Points:**
  * "Notice how the system immediately flags two variances beyond the 3% tolerance: Yield variance of −6.00% (188 good packets vs 200 standard) and Cooking Oil variance of +5.00% (10.5 L vs 10 L standard). The stock ledger automatically increments finished goods by 188 packets and deducts 194 pouches (188 good + 6 damaged) and 9 cartons."

---

### Minute 2:30 – 3:30 | Step 4: Field Order Entry (Salesman A Mobile View)
* **Login as:** `salesman_a` (Use bottom-left *Switch Persona* or log in as `salesman_a`).
* **View:** Resize browser to mobile phone dimension (or use DevTools Device Mode).
* **Navigation:** Opens on **New Field Order**.
* **Input Actions:**
  * Customer: Select `Retailer A (retailer, Tamil Nadu)`
  * Product Line: `Murukku 200 g` | Qty: `150` | Unit: `packet`
  * Pre-tax total dynamically shows `₹7,500.00` (150 pkts × ₹50).
  * Click **Submit Order to Factory Desk**.
  * Show **My Orders** screen: Status is `Submitted`.
* **Talking Points:**
  * "Salesman A in the field places an order for 150 packets for Retailer A in Tamil Nadu. The order form features offline caching and automatic queue synchronization if network connectivity drops in rural routes."

---

### Minute 3:30 – 4:30 | Step 5: Admin Stock Verification, GST Billing & Dispatch
* **Login as:** `admin` (Switch role to *Factory Admin*).
* **Navigation:** Click **Orders Desk**.
* **Action:** Open order `ORD-0001` for Retailer A.
* **Verification:**
  * The system displays: *On-hand: 238 pkts | Reserved: 0 | Available: 238 pkts*. Status is **Fully Covered**.
  * Click **Authorize & Approve Order**.
  * Click **Generate GST Tax Invoice**.
* **Tax Calculation & Dispatch:**
  * Show the generated tax invoice card:
    * Intra-state supply (Tamil Nadu code 33): CGST (2.5%) = `₹187.50`, SGST (2.5%) = `₹187.50`, Total = `₹7,875.00`.
  * Click **Download Official GST Invoice PDF** (briefly show the vector PDF).
  * Click **Record Dispatch (Deduct Stock)**.
* **Talking Points:**
  * "The admin verifies stock availability before approval. The invoice engine detects intra-state supply and computes CGST and SGST with paisa-level rounding. Dispatch decrements finished goods from 238 down to 88 packets."

---

### Minute 4:30 – 5:30 | Step 6: Out-of-State Order & Shortage Handling (Salesman B)
* **Login as:** `salesman_b`.
* **Action:** Place order for `Distributor B (distributor, Karnataka)`:
  * Qty: `120` packets of Murukku 200g.
* **Switch back to `admin`:**
  * Open the incoming order.
  * **Highlight:** The system alerts **SHORT by 32 pkts** (Available 88 vs Required 120), and informs the admin: *"Requires 1 more batch to fulfill"*.
  * Show back-order approval check box.
  * Show that interstate supply triggers **IGST 5.0% = ₹300.00** on ₹6,000.00.
  * Attempt dispatch: Show that physical dispatch is **strictly blocked** to prevent negative stock!
* **Talking Points:**
  * "The system prevents negative inventory while allowing back-orders, and handles inter-state IGST taxation automatically."

---

### Minute 5:30 – 6:15 | Step 7 & 8: Payment Collection & Unit Cost Calculation
* **Navigation:** Click **Payments Desk**.
  * Customer: `Retailer A` | Select invoice `INV/...` | Amount: `4000.00` | Mode: `UPI`
  * Click **Save Receipt**.
  * Show outstanding balance updates immediately to exactly `₹3,875.00` (7,875 − 4,000).
* **Navigation:** Open production run `RUN-0001` in **Batch Runs**.
  * Add direct overheads: Labour `₹1,200.00` and Power/Gas `₹600.00`.
  * **Show the Cost per Packet Card:**
    * Material cost: ₹4,055.00 + Overheads: ₹1,800.00 = Total ₹5,855.00.
    * Cost per packet = **₹31.14** across 188 good packets.
    * Gross profit margin = **₹18.86 (37.7%)** against the ₹50.00 selling price.

---

### Minute 6:15 – 7:30 | Step 9: Auditor Reports Hub, Tally XML & 1-Click Benchmark
* **Navigation:** Go to **Audit Reports Hub**.
  * Open **GST Outward Supplies (GSTR-1 / 3B)**: Show Table 3.1(a) and HSN Table 12.
  * Open **Stock Reconciliation Summary**: Verify opening + receipts − issues = closing balance.
  * Open **Traceable Stock Ledger**: Show individual ledger transactions.
  * Click **Tally Prime Export**: Show downloaded XML voucher file.
* **Final Highlight:** Click the top-bar **NIT Benchmark: 14/14 PASS** badge.
  * Show the live verification matrix with all 14 Section 5 checks passing with green checkmarks!
* **Closing:** "DakshinERP delivers a complete, verified, zero-drift solution built to the highest engineering standards."
