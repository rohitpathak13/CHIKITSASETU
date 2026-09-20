from web import create_app
from core.config import settings

app = create_app()

if __name__ == "__main__":
    print(f"[*] Starting CHIKITSASETU Web Portal on http://127.0.0.1:{settings.FLASK_PORT} ...")
    app.run(host="0.0.0.0", port=settings.FLASK_PORT, debug=True)
