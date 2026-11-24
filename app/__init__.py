import os

from flask import Flask, g, redirect, session, url_for

from . import db as dbm
from .util import money, qty


def create_app(database=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dakshin-erp-secret-key-enterprise-2026"),
        DATABASE=database or os.environ.get("DATABASE", os.path.join(app.root_path, "..", "data", "oto.db")),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16 MB max payload
    )
    app.teardown_appcontext(dbm.close_db)

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    app.jinja_env.filters.update(money=money, qty=qty)

    translations = {
        "en": {
            "New order": "New order", "My orders": "My orders", "My sales": "My sales", "Orders": "Orders",
            "Invoices": "Invoices", "Payments": "Payments", "Production": "Production", "Purchases": "Purchases",
            "Masters": "Masters", "Dashboard": "Dashboard", "Reports": "Reports", "Log out": "Log out",
            "Order-to-Audit": "Order-to-Audit", "Sales visit GPS log": "Sales visit GPS log",
            "Control Tower": "Control Tower", "Production Planner": "Production Planner",
            "Inventory Health": "Inventory Health", "Reorder Predictor": "Reorder Predictor",
            "Batch & Expiry": "Batch & Expiry", "Material Wastage": "Material Wastage",
            "Root Cause Analysis": "Root Cause Analysis", "Profitability": "Profitability",
            "Profit Leakage": "Profit Leakage", "Supplier Intelligence": "Supplier Intelligence",
            "Customer Intelligence": "Customer Intelligence", "Lost Sales": "Lost Sales",
            "Sales Performance": "Sales Performance", "Demand Forecasting": "Demand Forecasting",
            "Cash Flow": "Cash Flow", "Credit & Collection": "Credit & Collection",
            "Simulators": "Simulators", "AI Assistant": "AI Assistant", "Alert Center": "Alert Center",
            "Audit Readiness": "Audit Readiness", "Traceability": "Traceability",
            "Batch Recall": "Batch Recall", "Document Vault": "Document Vault",
            "Audit Package": "Audit Package", "Daily Closing": "Daily Closing",
            "Quality": "Quality", "Bottlenecks & Capacity": "Bottlenecks & Capacity",
            "Procurement": "Procurement", "Purchase Orders": "Purchase Orders"
        },
        "ta": {
            "New order": "புதிய ஆர்டர்", "My orders": "என் ஆர்டர்கள்", "My sales": "என் விற்பனை", "Orders": "ஆர்டர்கள்",
            "Invoices": "விலைப்பட்டியல்", "Payments": "பணம் செலுத்துதல்", "Production": "உற்பத்தி", "Purchases": "கொள்முதல்",
            "Masters": "முதன்மை விவரங்கள்", "Dashboard": "முகப்பு பலகை", "Reports": "அறிக்கைகள்", "Log out": "வெளியேறு",
            "Order-to-Audit": "Order-to-Audit", "Sales visit GPS log": "விற்பனை விஜயம் GPS பதிவு",
            "Control Tower": "கட்டுப்பாட்டு கோபுரம்", "Production Planner": "உற்பத்தி திட்டமிடல்",
            "Inventory Health": "சரக்கு இருப்பு நலம்", "Reorder Predictor": "மறுஆர்டர் கணிப்பு",
            "Batch & Expiry": "தொகுதி மற்றும் காலாவதி", "Material Wastage": "பொருள் வீணடிப்பு",
            "Root Cause Analysis": "மூல காரண பகுப்பாய்வு", "Profitability": "லாபத்தன்மை",
            "Profit Leakage": "லாப கசிவு கண்டறிதல்", "Supplier Intelligence": "விற்பனையாளர் செயல்திறன்",
            "Customer Intelligence": "வாடிக்கையாளர் விவரங்கள்", "Lost Sales": "இழந்த விற்பனை",
            "Sales Performance": "விற்பனை இலக்கு", "Demand Forecasting": "தேவை முன்கணிப்பு",
            "Cash Flow": "பணப்புழக்கம்", "Credit & Collection": "கடன் மற்றும் வசூல்",
            "Simulators": "வணிக மாதிரிகள்", "AI Assistant": "AI உதவியாளர்", "Alert Center": "எச்சரிக்கை மையம்",
            "Audit Readiness": "தணிக்கை தயார்நிலை", "Traceability": "பரிவர்த்தனை கண்டுபிடிப்பு",
            "Batch Recall": "தொகுதி திரும்பப்பெறுதல்", "Document Vault": "ஆவண பெட்டகம்",
            "Audit Package": "தணிக்கை தொகுப்பு", "Daily Closing": "தினசரி கணக்கு முடிவு",
            "Quality": "தரக் கட்டுப்பாடு", "Bottlenecks & Capacity": "தடைகள் மற்றும் திறன்",
            "Procurement": "கொள்முதல் மேலாண்மை", "Purchase Orders": "கொள்முதல் ஆணைகள்"
        }
    }
    app.jinja_env.globals['tr'] = lambda text: translations.get(session.get('lang', 'en'), translations['en']).get(text, text)

    from .services import reports as rep
    from .util import today
    app.jinja_env.globals.update(rdisplay=rep.display, today=today)

    @app.before_request
    def load_user():
        g.user = None
        g.alert_count = 0
        g.top_alerts = []
        if session.get("uid"):
            r = dbm.get_db().execute("SELECT * FROM users WHERE id=? AND active=1", (session["uid"],)).fetchone()
            g.user = dict(r) if r else None
            if g.user and g.user["role"] in ("admin", "owner", "production", "accountant"):
                try:
                    from .services import alerts as svc_alerts
                    alts = svc_alerts.get_active_alerts(dbm.get_db())
                    g.alert_count = len(alts)
                    g.top_alerts = alts[:5]
                except Exception:
                    pass

    @app.route("/health")
    def health_check():
        from .util import today
        return {
            "status": "healthy",
            "system": "SnackFlow ERP",
            "version": "2.2.0-enterprise",
            "timestamp": today(),
            "environment": os.environ.get("FLASK_ENV", "production")
        }

    @app.route("/sw.js")
    def sw():
        from flask import send_from_directory
        return send_from_directory(app.static_folder, "sw.js", mimetype="application/javascript")

    # Register all modular blueprints
    from .views import (
        admin,
        alerts as alerts_v,
        auth,
        decisions as decisions_v,
        intelligence,
        mrp as mrp_v,
        owner as owner_v,
        procurement as proc_v,
        production,
        profitability as prof_v,
        quality as qual_v,
        reports,
        sales,
        traceability as trace_v,
    )

    for bp_mod in (
        auth, sales, admin, production, reports, intelligence,
        proc_v, mrp_v, qual_v, trace_v, prof_v, alerts_v, decisions_v, owner_v
    ):
        app.register_blueprint(bp_mod.bp)

    with app.app_context():
        conn = dbm.get_db()
        dbm.init_db(conn)
        if os.environ.get("AUTO_SEED", "1") == "1":
            from .seed import seed
            seed(conn)

    return app
