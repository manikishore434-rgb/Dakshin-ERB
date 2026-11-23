"""Single command start-up:  python run.py   ->  http://localhost:5000  (creates + seeds data/oto.db on first run)"""
import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "5000")), debug=False)
