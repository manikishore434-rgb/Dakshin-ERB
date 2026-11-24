# SOFTWARE TESTING & QUALITY ASSURANCE REPORT
## Dakshin ERP (SnackFlow Operating System)
### Enterprise Order-to-Audit Manufacturing Platform

---

## 1. Executive Summary & Test Metrics

Dakshin ERP has undergone thorough quality assurance testing across business logic, database transactions, unit conversion accuracy, Indian GST tax calculations, and end-to-end user workflows.

### Summary QA Dashboard
- **Total Automated Test Suites:** 5 suites
- **Total Executed Tests:** 50 automated tests
- **Tests Passed:** 50 (100% Pass Rate)
- **Tests Failed:** 0
- **Execution Duration:** ~15.5 seconds
- **NIT Trichy Mandatory Benchmark:** 14 / 14 Checkpoints Passed (100% Compliance)

---

## 2. Test Suites Architecture & Coverage Matrix

| Test Suite File | Domain Covered | Tests Count | Status | Key Assertions Verified |
|---|---|---|---|---|
| `tests/test_benchmark.py` | Section 5 NIT Trichy Scenario | 6 | **PASS** | Exact closing balances, yield & oil variance %, invoice total, outstanding balance, shortage flag |
| `tests/test_rules.py` | Core Business & Ledger Rules | 10 | **PASS** | Role-based authorization, duplicate submission prevention, stock availability, dispatch blocks, credit notes |
| `tests/test_tax_units.py` | Math, Precision & Taxes | 4 | **PASS** | Exact paise arithmetic, milligram unit conversions, CGST/SGST vs IGST split, zero floating point drift |
| `tests/test_intelligence.py` | Predictive Intelligence | 23 | **PASS** | Demand forecasting, cash flow modeling, inventory health, lost sales capture, simulators, health endpoint |
| `tests/test_new_modules.py` | Enterprise Modules | 7 | **PASS** | Purchase order approval & receipt, supplier payments, QA inspection release & blocks, batch lineage trace |

---

## 3. Mandatory NIT Tiruchirappalli Section 5 Benchmark Verification

The platform was subjected to the exact benchmark scenario specified in Section 5 of the NIT Tiruchirappalli Problem Statement:

### Benchmark Execution Results

| Checkpoint Name | Problem Statement Specification | Expected Value | Actual ERP Output | Status |
|---|---|---|---|---|
| **Flour Closing Balance** | Opening 100 kg + Purchase 60 kg - Issue 40 kg | `120 kg` | `120 kg` | **PASS** |
| **Cooking Oil Closing Balance** | Opening 30 L - Issue 10.5 L (0.5 L over standard) | `19.5 L` | `19.5 L` | **PASS** |
| **Pouches Closing Balance** | Opening 500 - (188 good + 6 damaged pouches) | `306` | `306` | **PASS** |
| **Finished Goods Post-Run** | Opening 50 packets + Run Output 188 packets | `238 packets` | `238 packets` | **PASS** |
| **Finished Goods Post-Dispatch** | Stock 238 packets - Retailer A Order 150 packets | `88 packets` | `88 packets` | **PASS** |
| **Production Yield Variance** | 188 actual vs 200 standard BOM yield | `-6.00%` (Flagged) | `-6.00%` (Flagged) | **PASS** |
| **Oil Consumption Variance** | 10.5 L actual vs 10.0 L standard BOM requirement | `+5.00%` (Flagged) | `+5.00%` (Flagged) | **PASS** |
| **Retailer A Taxable Amount** | 150 packets @ ₹50/packet selling price | `₹7,500.00` | `₹7,500.00` | **PASS** |
| **Retailer A CGST & SGST Split** | Intra-State supply (TN 33 to TN 33) @ 2.5% each | `₹187.50 / ₹187.50` | `₹187.50 / ₹187.50` | **PASS** |
| **Retailer A Total Invoice** | Taxable ₹7,500 + CGST ₹187.50 + SGST ₹187.50 | `₹7,875.00` | `₹7,875.00` | **PASS** |
| **Retailer A Outstanding Dues** | Total Invoice ₹7,875.00 - Payment ₹4,000.00 | `₹3,875.00` | `₹3,875.00` | **PASS** |
| **Distributor B Shortage Detection** | Order 120 packets vs Stock 88 packets on hand | `32 packets short` | `32 packets short` | **PASS** |
| **Distributor B Tax Type (Inter-State)** | Inter-State supply (TN 33 to KA 29) @ 5% IGST | `IGST ₹300.00` | `IGST ₹300.00` | **PASS** |
| **Distributor B Dispatch Block** | Prevent negative stock dispatch | `Blocked` | `Blocked` | **PASS** |

### Unit Manufacturing Cost & Profit Margin Analysis
- **Direct Material Cost:** Flour (40 kg × ₹43.125 WAC = ₹1,725.00) + Oil (10.5 L × ₹140 = ₹1,470.00) + Spice Mix (1.2 kg × ₹200 = ₹240.00) + Pouches (194 used/damaged × ₹2.50 = ₹485.00) + Cartons (9 × ₹15 = ₹135.00) = **₹4,055.00**
- **Operational Overheads:** Labour ₹1,200.00 + Gas & Power ₹600.00 = **₹1,800.00**
- **Total Batch Cost:** ₹4,055.00 + ₹1,800.00 = **₹5,855.00**
- **Actual Good Packets Produced:** 188 packets
- **Manufacturing Cost Per Packet:** $$\frac{₹5,855.00}{188} = \mathbf{₹31.14 \text{ per packet}}$$
- **Selling Price:** ₹50.00 per packet
- **Gross Profit Margin:** $$\mathbf{₹18.86 \text{ per packet (37.7\% margin)}}$$

---

## 4. End-to-End Business Flow Verifications

### 4.1 Purchase-to-Stock Traceability
1. Created PO `PO-00001` to Sri Lakshmi Flour Mills for 50 kg flour.
2. Authorized by Admin.
3. Inwarded with GRN `GRN-00001` and supplier batch `MF-2026-09`.
4. Verified that raw material inventory in `stock_ledger` increased by exactly 50,000,000 mg.

### 4.2 Quality Gate & Quarantine Dispatch Prevention
1. Created production run `RUN-00001`.
2. Created QC inspection `QC-00001` with verdict `'rejected'` (excessive moisture / rancidity).
3. Attempted to dispatch an invoice containing this finished good.
4. **Result:** Dispatch was rejected with HTTP 400 and `ServiceError: Dispatch blocked by Quality Control: Item has not passed quality inspection`.

### 4.3 Order-to-Cash Idempotency
1. Submitted field sales order with client UUID.
2. Re-submitted identical payload.
3. **Result:** The system detected the existing client UUID and returned the existing order rather than creating a duplicate transaction.
