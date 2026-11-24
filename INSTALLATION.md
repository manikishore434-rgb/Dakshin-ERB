# INSTALLATION & QUICK START GUIDE
## Dakshin ERP (SnackFlow Operating System)
### Enterprise Order-to-Audit Manufacturing Platform

---

## 1. System Requirements

| Component | Minimum Specification | Recommended Specification |
|---|---|---|
| **Operating System** | Windows 10/11, Ubuntu 20.04+, macOS 12+ | Ubuntu 22.04 LTS or Windows 11 64-bit |
| **Python** | Python 3.11.x | Python 3.11 or 3.12 (standard 64-bit) |
| **Memory (RAM)** | 2 GB RAM | 4 GB+ RAM |
| **Storage** | 500 MB free disk space | 2 GB+ SSD storage |
| **Web Browser** | Chrome 100+, Firefox 100+, Edge 100+ | Modern Evergreen Browser with PWA support |
| **Docker (Optional)** | Docker Engine 24+ & Docker Compose v2 | Docker Desktop 4.25+ |

---

## 2. Local Python Environment Setup

### Step 1: Clone or Open the Repository
```bash
git clone https://github.com/manikishore434-rgb/Dakshin-ERB.git
cd Dakshin-ERB
```

### Step 2: Create and Activate Virtual Environment
- **On Windows (PowerShell):**
  ```powershell
  python -m venv venv
  .\venv\Scripts\Activate.ps1
  ```
- **On Linux / macOS (Bash / Zsh):**
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  ```

### Step 3: Install Production Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt gunicorn
```

### Step 4: Environment Configuration
Copy the provided environment template to `.env`:
```bash
# On Linux/macOS
cp .env.example .env

# On Windows PowerShell
Copy-Item .env.example .env
```

### Step 5: Launch the Application
```bash
python run.py
```
The application will automatically:
1. Initialize the SQLite schema with foreign keys and WAL mode.
2. Auto-seed master items, customers, suppliers, BOMs, and opening balances (Section 5 NIT Trichy data).
3. Bind to `http://127.0.0.1:5000` (or `http://localhost:5000`).

---

## 3. Containerized Setup (Docker & Compose)

To run the complete platform inside an isolated container with volume-backed persistence and health checks:

### Single Command Launch
```bash
docker compose up --build -d
```

### Verify Running Services
```bash
docker compose ps
docker compose logs -f web
```
The web service includes an automated container healthcheck testing `http://127.0.0.1:5000/health`.

### Stopping Containers
```bash
docker compose down
```

---

## 4. Pre-Seeded Demonstration Logins

The database initializes with 5 role-based personas designed for evaluation:

| Role Persona | Username | Password | Default Landing Dashboard | Primary Capabilities |
|---|---|---|---|---|
| **Executive Owner** | `owner` | `demo123` | `/owner/suite` | Executive Control Tower, business valuation, macro variance alerts |
| **Factory Admin** | `admin` | `demo123` | `/admin/orders` | Order approval, GST tax invoicing, payment logging, masters |
| **Production Supervisor** | `production` | `demo123` | `/production/runs` | Material issue, batch output recording, scrap tracking, QA inspection |
| **Field Salesman A** | `salesman_a` | `demo123` | `/sales/order/new` | Mobile order entry, Retailer A pricing, GPS visit check-in |
| **Field Salesman B** | `salesman_b` | `demo123` | `/sales/order/new` | Mobile order entry, Distributor B out-of-state order entry |
| **Accountant / Auditor** | `accountant` | `demo123` | `/reports` | 14 statutory reports, GSTR-1/3B summary, Tally XML export |

> **Evaluator Convenience:** In addition to manual login, you can switch personas instantly using the **"Switch Persona (Demo)"** selector in the sidebar or by visiting `/roles`.

---

## 5. Verification Commands

### Execute Automated NIT Benchmark Verification (14 Checks)
```bash
python -m app.benchmark
```
*Expected: 14/14 checkpoints return `PASS` with zero numerical drift.*

### Execute Full Enterprise Test Suite (50 Tests)
```bash
python -m unittest discover -s tests -v
```
*Expected: `Ran 50 tests in ~15s - OK`*

### Query System Health Endpoint
```bash
curl http://localhost:5000/health
```
*Expected JSON: `{"status": "healthy", "system": "SnackFlow ERP", "version": "2.2.0-enterprise", ...}`*

---

## 6. Troubleshooting Common Issues

### Issue 1: PowerShell Execution Policy prevents virtual environment activation
**Error:** `File Activate.ps1 cannot be loaded because running scripts is disabled on this system.`  
**Fix:** Run:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

### Issue 2: `ModuleNotFoundError: No module named 'app'` when running tests
**Fix:** Ensure `PYTHONPATH` includes the repository root directory:
- PowerShell: `$env:PYTHONPATH="."; python -m unittest discover -s tests`
- Bash: `PYTHONPATH=. python -m unittest discover -s tests`

### Issue 3: Port 5000 Already In Use
**Fix:** Pass custom port via environment variable:
- Windows PowerShell: `$env:PORT="5050"; python run.py`
- Linux/macOS: `PORT=5050 python run.py`
