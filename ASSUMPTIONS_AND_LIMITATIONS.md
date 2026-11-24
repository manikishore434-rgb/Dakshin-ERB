# DOCUMENTED ASSUMPTIONS, DESIGN DECISIONS & KNOWN LIMITATIONS
## Dakshin ERP (SnackFlow Operating System)
### National Institute of Technology, Tiruchirappalli Winter Internship Task

---

## 1. Statutory Context & Business Assumptions

As instructed in Section 10 of the NIT Tiruchirappalli Internship Problem Statement (*"Where something is unclear, make a reasonable assumption and write it down. Documented assumptions are part of what we evaluate."*), the following operational rules and assumptions were formally established:

### 1.1 Geographic & Place of Supply Configuration
- **Manufacturing Facility:** Located in Tiruchirappalli, Tamil Nadu (GST State Code `33`).
- **Retailer A:** Registered in Tiruchirappalli, Tamil Nadu (`33BBBBB1111B1Z5`). Because Supplier State (`33`) equals Customer State (`33`), this transaction is categorized as **Intra-State Supply**, subject to equal halves of CGST (2.5%) and SGST (2.5%).
- **Distributor B:** Registered in Peenya, Bengaluru, Karnataka (`29CCCCC2222C1Z5`). Because Supplier State (`33`) does not equal Customer State (`29`), this transaction is categorized as **Inter-State Supply**, subject to full IGST (5.0%).

### 1.2 GST Product Classification
- **Murukku 200 g:** Classified under HSN code **`2106 90 99`** (*Food preparations not elsewhere specified or included - Namkeens, bhujia, mixture, chabena and similar edible preparations*).
- **Tax Rate:** Benchmarked at 5.0% (500 basis points).

### 1.3 Inventory Valuation & Packaging Scrap Absorption
- **Valuation Method:** Moving Weighted Average Cost (WAC) is adopted for all raw material lots. When 60 kg of flour is purchased at ₹45/kg into an existing opening stock of 100 kg at ₹42/kg, the new unit valuation becomes:
  $$\text{WAC} = \frac{(100 \times 42) + (60 \times 45)}{100 + 60} = \frac{4200 + 2700}{160} = \mathbf{₹43.125 \text{ per kg}}$$
- **Damaged Packaging Allocation:** During the benchmark run, 6 pouches were damaged during high-speed nitrogen sealing. These pouches are treated as normal manufacturing scrap and absorbed into the batch's total direct material cost, ensuring the closing inventory valuation reflects true cost-per-packet.
- **Finished Goods Opening Stock Valuation:** Opening inventory of 50 packets of finished Murukku 200 g is carried at an opening benchmark valuation of ₹30.00 per packet.

---

## 2. Technical Design Decisions

### 2.1 Zero-Drift Perpetual Stock Ledger vs Cached Balances
- **Decision:** The application **never stores mutable stock balances on product master records**.
- **Justification:** In fast-moving manufacturing, storing a `current_stock` column invites race conditions, silent overwrites, and audit discrepancies. Computing or verifying stock from an append-only transaction ledger guarantees complete traceability: every gram of flour and every pouch links directly to a source document (PO, GRN, Batch Run, Dispatch Invoice, or Credit Note).

### 2.2 Integer-Paisa & Milligram Math
- **Decision:** All monetary transactions are calculated and stored in integer paise (`₹1 = 100 paise`), and quantities in integer milligrams (`1 kg = 1,000,000 mg`).
- **Justification:** IEEE 754 double-precision floating-point numbers exhibit binary representation rounding artifacts (e.g. `0.1 + 0.2 = 0.30000000000000004`). In financial accounting and GST audits, fractional paisa divergence across thousands of invoice lines violates statutory compliance. Exact decimal arithmetic with explicit Banker's Half-Up rounding eliminates drift.

### 2.3 SQLite in WAL Mode
- **Decision:** SQLite with Write-Ahead Logging (`PRAGMA journal_mode = WAL;`) and Foreign Key enforcement (`PRAGMA foreign_keys = ON;`).
- **Justification:** For a small food factory with 5–15 mobile salesmen and floor terminals, SQLite in WAL mode provides microsecond response times, zero server configuration overhead, atomic ACID transactions, and live online hot backups without locking read queries.

---

## 3. Scope & Known Limitations

1. **Single Manufacturing Facility:** The current version models one central manufacturing plant with an integrated billing desk and local warehouse. Multi-warehouse in-transit transfer orders (stock transfer notes) can be added in future iterations.
2. **Third-Party API Sandboxes:**
   - **Tally Integration:** Generates 100% compliant Tally Prime XML import vouchers for direct drag-and-drop ingestion into Tally Prime. Live direct socket push requires an active Tally.NET subscription.
   - **e-Invoice & e-Way Bill:** Compliant JSON data payloads are generated ready for the NIC / GST portal. Direct automated transmission requires paid GSP (GST Suvidha Provider) credentials.
3. **Hardware Integration:**
   - Weighing scale inputs and pouch sealer telemetry are entered through the touch-friendly floor terminal interface; direct RS-232 serial scale capture can be integrated via Web Serial API.
