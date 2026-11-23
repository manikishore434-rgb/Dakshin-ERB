import os

from flask import Flask, g, redirect, session, url_for

from . import db as dbm
from .util import money, qty


def create_app(database=None):
    app = Flask(__name__)
    app.config.update(SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
                      DATABASE=database or os.environ.get("DATABASE", os.path.join(app.root_path, "..", "data", "oto.db")))
    app.teardown_appcontext(dbm.close_db)
    app.jinja_env.filters.update(money=money, qty=qty)
    translations = {
        "en": {"New order":"New order", "My orders":"My orders", "My sales":"My sales", "Orders":"Orders", "Invoices":"Invoices", "Payments":"Payments", "Production":"Production", "Purchases":"Purchases", "Masters":"Masters", "Dashboard":"Dashboard", "Reports":"Reports", "Log out":"Log out", "Order-to-Audit":"Order-to-Audit", "Sales visit GPS log":"Sales visit GPS log"},
        "ta": {"New order":"புதிய ஆர்டர்", "My orders":"என் ஆர்டர்கள்", "My sales":"என் விற்பனை", "Orders":"ஆர்டர்கள்", "Invoices":"விலைப்பட்டியல்", "Payments":"பணம் செலுத்துதல்", "Production":"உற்பத்தி", "Purchases":"கொள்முதல்", "Masters":"முதன்மை விவரங்கள்", "Dashboard":"முகப்பு பலகை", "Reports":"அறிக்கைகள்", "Log out":"வெளியேறு", "Order-to-Audit":"Order-to-Audit", "Sales visit GPS log":"விற்பனை விஜயம் GPS பதிவு"}}
    app.jinja_env.globals['tr'] = lambda text: translations.get(__import__('flask').session.get('lang', 'en'), translations['en']).get(text, text)

    from .services import reports as rep
    app.jinja_env.globals.update(rdisplay=rep.display, today=__import__("app.util", fromlist=["today"]).today)

    @app.before_request
    def load_user():
        g.user = None
        if session.get("uid"):
            r = dbm.get_db().execute("SELECT * FROM users WHERE id=? AND active=1", (session["uid"],)).fetchone()
            g.user = dict(r) if r else None

    @app.route("/sw.js")
    def sw():  # served from the root so its scope covers the whole app
        from flask import send_from_directory
        return send_from_directory(app.static_folder, "sw.js", mimetype="application/javascript")

    from .views import admin, auth, production, reports, sales
    for m in (auth, sales, admin, production, reports):
        app.register_blueprint(m.bp)

    with app.app_context():
        conn = dbm.get_db()
        dbm.init_db(conn)
        if os.environ.get("AUTO_SEED", "1") == "1":
            from .seed import seed
            seed(conn)
    return app
