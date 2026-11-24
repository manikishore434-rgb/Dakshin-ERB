# REST & WEB API SPECIFICATION
## Dakshin ERP (SnackFlow Operating System)
### Enterprise Order-to-Audit Manufacturing Platform

---

## 1. Overview & Protocol Architecture

Dakshin ERP provides a dual-interface architecture:
- **Web Controller Layer:** Server-rendered Jinja2 interfaces hardened with CSRF tokens, strict RBAC authorization, and contextual flash feedback.
- **REST / JSON API Layer:** Stateless programmatic endpoints for mobile field synchronization, global autocomplete search, automated health monitors, and external accounting integrations.

### Standard Response Envelopes
- **JSON Error Envelope:**
  ```json
  {
    "error": true,
    "message": "Human-readable failure description",
    "code": "BAD_REQUEST",
    "timestamp": "2026-11-24T13:30:00"
  }
  ```
- **JSON Success Envelope:**
  ```json
  {
    "success": true,
    "data": { ... },
    "timestamp": "2026-11-24T13:30:00"
  }
  ```

---

## 2. Authentication & Role-Based Access Control (RBAC)

All endpoints (except `/health`, `/login`, and `/sw.js`) are protected by the backend-enforced `@login_required(*roles)` decorator. Session cookies are protected with `HttpOnly=True`, `SameSite=Lax`, and `Secure` flags.

| Endpoint | Method | Allowed Roles | Description |
|---|---|---|---|
| `/login` | `GET`, `POST` | Public | Authenticates credentials and starts user session |
| `/logout` | `GET` | Authenticated | Clears user session |
| `/roles` | `GET`, `POST` | Authenticated | Multi-role persona inspection and 1-click test switcher |
| `/switch-role/<role>` | `GET` | Authenticated | Quick switcher for demo evaluators (`admin`, `production`, `salesman`, `accountant`, `owner`) |
| `/language/<lang>` | `GET` | Authenticated | Toggles UI language between English (`en`) and Tamil (`ta`) |

---

## 3. Core System & Utility Endpoints

### 3.1 Health Check
- **Route:** `GET /health`
- **Access:** Public (suitable for Docker healthcheck, Kubernetes liveness probes, AWS ALB)
- **Response `200 OK`:**
  ```json
  {
    "status": "healthy",
    "system": "SnackFlow ERP",
    "version": "2.2.0-enterprise",
    "timestamp": "2026-11-24",
    "environment": "production"
  }
  ```

### 3.2 Global Instant Search
- **Route:** `GET /api/search?q=<query>`
- **Access:** Any authenticated user
- **Query Parameters:** `q` (string, min 2 characters)
- **Response `200 OK`:**
  ```json
  {
    "results": [
      {
        "category": "Order",
        "badge_class": "badge-blue",
        "title": "Order #ORD-00001",
        "subtitle": "Status: Dispatched",
        "url": "/admin/orders/1"
      },
      {
        "category": "Customer",
        "badge_class": "badge-green",
        "title": "Retailer A",
        "subtitle": "Retailer · Phone: 9000000001",
        "url": "/admin/masters"
      }
    ]
  }
  ```

---

## 4. Sales & Field Order Management (`/sales`)

### 4.1 Create Sales Order
- **Route:** `POST /sales/order/new`
- **Access:** `salesman`, `admin`, `owner`
- **Form / Payload Parameters:**
  - `customer_id` (integer, required): Customer reference ID
  - `client_uuid` (string, optional): Idempotency key preventing double submission
  - `priority` (string, optional): `'normal'`, `'high'`, `'urgent'`
  - `delivery_date` (string `YYYY-MM-DD`, optional)
  - `item_id_<id>` & `qty_<id>`: Quantity requested per catalog SKU
- **Success:** Redirects to order confirmation; database transaction records state transition to `'submitted'`.

### 4.2 Offline Order Sync
- **Route:** `POST /sales/sync-offline-order`
- **Payload:** JSON array of orders captured while salesman was out of cellular network coverage.

### 4.3 Salesman GPS Visit Logging
- **Route:** `POST /sales/visits`
- **Payload:** `customer_id`, `latitude`, `longitude`, `note`.

---

## 5. Factory Admin & GST Invoicing (`/admin`)

### 5.1 Approve Sales Order & Raise GST Invoice
- **Route:** `POST /admin/orders/<id>/approve`
- **Access:** `admin`, `owner`
- **Behavior:**
  - Evaluates current finished-goods stock ledger balance against order requirement.
  - Automatically derives Place of Supply:
    - Intra-State (Factory TN 33 == Customer TN 33): Splits GST equally into CGST (2.5%) + SGST (2.5%).
    - Inter-State (Factory TN 33 != Customer KA 29): Levies full IGST (5.0%).
  - Sequences consecutive tax invoice number for the financial year (e.g., `INV/2026-27/0001`).
  - Transitions order state from `'submitted'` to `'invoiced'`.

### 5.2 Record Dispatch
- **Route:** `POST /admin/invoices/<id>/dispatch`
- **Access:** `admin`, `owner`
- **Behavior:**
  - Verifies batch quality release verdict (blocks dispatch if lot is quarantined or rejected).
  - Posts negative entries to `stock_ledger` under move type `'dispatch'`.
  - Zero-drift deduction of finished goods inventory.

### 5.3 Download GST Tax Invoice PDF
- **Route:** `GET /admin/invoices/<id>/pdf`
- **Access:** `admin`, `owner`, `accountant`
- **Response:** Binary stream `application/pdf` containing formal GSTIN invoice with QR code, HSN breakdown, tax split, and bank particulars.

---

## 6. Production & BOM Execution (`/production`)

### 6.1 Record Production Run
- **Route:** `POST /production/runs/new`
- **Access:** `production`, `admin`, `owner`
- **Parameters:**
  - `product_id` (integer): Finished good ID
  - `batches` (decimal): Multiplier of standard BOM batch size
  - `actual_packets` (integer): Actual physically produced good packets
  - `damaged_pouches` (integer): Packing material scrap
  - `cartons_used` (integer): Actual secondary packaging consumed
  - `raw_flour`, `raw_oil`, `raw_spice`: Measured physical raw material issues
- **Business Engine Output:**
  - Generates unique batch lot identifier (e.g. `BATCH-20261124-001`).
  - Posts consumption transactions to `stock_ledger` for raw materials and packaging.
  - Posts receipt of finished packets to `stock_ledger`.
  - Computes planned vs actual consumption variance and yield variance percentage.
  - Automatically flags variances exceeding factory tolerance (3.0%).

---

## 7. Procurement & Supply Chain (`/procurement`)

### 7.1 Purchase Order Lifecycle
- `GET /procurement/orders` - View purchase orders
- `POST /procurement/orders/new` - Draft purchase order to registered supplier
- `POST /procurement/orders/<id>/approve` - Authorize purchase order
- `POST /procurement/orders/<id>/receive` - Inward goods with GRN (Goods Received Note) and automatic raw material stock addition

---

## 8. Quality Control & Inspections (`/quality`)

### 8.1 QA Inspection Verdict
- `POST /quality/inspections/<id>`
- Verdict values: `'approved'`, `'quarantine'`, `'rejected'`.
- Synchronizes with referenced production batch or raw material purchase lot. Blocked batches are strictly forbidden from outbound dispatch.

---

## 9. Statutory Audit Reports & Tally (`/reports`)

### 9.1 Report Query
- **Route:** `GET /reports/view/<slug>?from=YYYY-MM-DD&to=YYYY-MM-DD`
- **Supported Slugs:**
  1. `sales-register`
  2. `purchase-register`
  3. `gst-summary` (GSTR-1 outward supply format)
  4. `stock-summary`
  5. `stock-ledger`
  6. `production`
  7. `consumption-variance`
  8. `yield-and-wastage`
  9. `cost-per-packet`
  10. `customer-outstanding`
  11. `receivables-ageing`
  12. `payments-collections`
  13. `product-profitability`
  14. `batch-production`

### 9.2 Exports
- **Excel:** `GET /reports/export/<slug>/xlsx` (openpyxl formatted sheets)
- **CSV:** `GET /reports/export/<slug>/csv`
- **Tally Prime XML:** `GET /reports/tally` (Native XML import format for Tally Prime ledgers and vouchers)
