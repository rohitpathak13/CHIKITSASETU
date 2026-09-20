"""
CHIKITSASETU - Flask Application Entrypoint
Run this script to start the multi-role operational web portal.
Usage: python run_flask.py
"""
import os
import sys

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from web import create_app
from core.config import settings

app = create_app()

if __name__ == "__main__":
    print(f"==================================================")
    print(f" CHIKITSASETU - Multi-Role Clinical Web Portal     ")
    print(f" URL: http://127.0.0.1:{settings.FLASK_PORT}                      ")
    print(f" Environment: {settings.ENV}                      ")
    print(f"==================================================")
    app.run(host="0.0.0.0", port=settings.FLASK_PORT, debug=False, use_reloader=False)
