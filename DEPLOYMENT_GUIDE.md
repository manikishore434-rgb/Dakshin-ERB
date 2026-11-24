# ENTERPRISE DEPLOYMENT & DEVOPS RUNBOOK
## Dakshin ERP (SnackFlow Operating System)
### Enterprise Order-to-Audit Manufacturing Platform

---

## 1. Production Architecture Overview

Dakshin ERP is packaged for production deployment as a lightweight, high-performance web service. It can be hosted on:
- **Cloud PaaS Platforms:** Render, Railway, Fly.io, or Heroku.
- **Container Infrastructure:** Docker, Docker Compose, AWS ECS, or Kubernetes.
- **Bare-Metal / Linux VPS:** Ubuntu 22.04 LTS / Debian 12 with Systemd, Gunicorn, and Nginx.

### Critical Database Persistence Rule
Because SQLite with Write-Ahead Logging (WAL) is utilized as the transactional engine, **the database file directory (`/srv/data` or `./data`) must reside on a persistent storage volume**. Ephemeral container filesystems will erase transactions on container redeployment.

---

## 2. Option A: Deployment via Docker Compose (Recommended for VPS)

### Step 1: Clone Repository on Host
```bash
git clone https://github.com/manikishore434-rgb/Dakshin-ERB.git /opt/dakshin-erp
cd /opt/dakshin-erp
```

### Step 2: Configure Environment
```bash
cp .env.example .env
nano .env
```
Ensure a strong, random cryptographic secret is set:
```env
SECRET_KEY=9f83b2a8d71e46c59b2e0431a7c5b62e4f01d8e3b7c2a1
DATABASE=/srv/data/oto.db
PORT=5000
FLASK_ENV=production
```

### Step 3: Launch with Persistent Volume & Health Check
```bash
docker compose up -d --build
```

### Step 4: Verify Container Health
```bash
docker compose ps
curl http://localhost:5000/health
```

---

## 3. Option B: Cloud PaaS Deployment (Render)

The repository includes a ready-to-use infrastructure-as-code specification: `render.yaml`.

### 1-Click Setup on Render
1. Create a new Web Service on [Render](https://render.com).
2. Connect your GitHub repository: `https://github.com/manikishore434-rgb/Dakshin-ERB.git`.
3. Choose **Python 3** environment.
4. Set **Build Command:** `pip install -r requirements.txt gunicorn`.
5. Set **Start Command:** `gunicorn -b 0.0.0.0:$PORT -w 1 --threads 4 run:app`.
6. Attach a **Persistent Disk:**
   - **Mount Path:** `/srv/data`
   - **Size:** 1 GB
7. Add Environment Variables:
   - `SECRET_KEY`: (Auto-generated random key)
   - `DATABASE`: `/srv/data/oto.db`
   - `AUTO_SEED`: `1` (Seeds Section 5 benchmark data on initial boot)
8. Deploy! Render will build and expose your live URL (e.g. `https://dakshin-erb.onrender.com`).

---

## 4. Option C: Bare-Metal Ubuntu Linux (Systemd + Nginx)

### Step 1: Systemd Service Unit
Create `/etc/systemd/system/dakshin-erp.service`:
```ini
[Unit]
Description=Dakshin ERP Production Gunicorn Service
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/dakshin-erp
Environment="PATH=/var/www/dakshin-erp/venv/bin"
Environment="DATABASE=/var/www/dakshin-erp/data/oto.db"
Environment="SECRET_KEY=secure-random-token-here"
ExecStart=/var/www/dakshin-erp/venv/bin/gunicorn -b 127.0.0.1:5000 -w 1 --threads 4 run:app
Restart=always

[Install]
WantedBy=multi-user.target
```

### Step 2: Nginx Reverse Proxy Configuration
Create `/etc/nginx/sites-available/dakshin-erp`:
```nginx
server {
    listen 80;
    server_name erp.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static {
        alias /var/www/dakshin-erp/app/static;
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }
}
```
Enable site and obtain SSL certificate with Certbot:
```bash
sudo ln -s /etc/nginx/sites-available/dakshin-erp /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
sudo certbot --nginx -d erp.yourdomain.com
```

---

## 5. Backup & Disaster Recovery Strategy

Because SQLite is operating in WAL mode, backups can be performed **live without locking writers or stopping the web service**:

### Online Hot Backup Command
```bash
sqlite3 data/oto.db ".backup 'data/backups/oto_backup_$(date +%Y%m%d_%H%M%S).db'"
```

### Automated Nightly Cron Job
```cron
0 2 * * * /usr/bin/sqlite3 /var/www/dakshin-erp/data/oto.db ".backup '/var/www/dakshin-erp/data/backups/oto_$(date +\%F).db'" && find /var/www/dakshin-erp/data/backups/ -name "oto_*.db" -mtime +14 -delete
```

---

## 6. Post-Deployment Smoke Test Checklist

- [ ] Liveness probe: `GET /health` returns `200 OK` with `"status": "healthy"`.
- [ ] Login screen loads with Premium Light Purple SaaS styling.
- [ ] Persona switcher `/roles` functions properly across all 5 roles.
- [ ] Section 5 Benchmark report at `/reports/benchmark` displays 14/14 PASS.
- [ ] GST Tax invoice PDF download works and renders properly.
- [ ] Production restart test: Verify orders and ledger balance persist across container restart.
