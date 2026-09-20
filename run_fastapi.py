"""
CHIKITSASETU - FastAPI Service Entrypoint
Run this script to launch the high-speed REST API & ML Inference Service.
Usage: python run_fastapi.py
"""
import os
import sys
import uvicorn

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config import settings

if __name__ == "__main__":
    print(f"==================================================")
    print(f" CHIKITSASETU - REST & Machine Learning Engine     ")
    print(f" API Docs (Swagger): http://127.0.0.1:{settings.FASTAPI_PORT}/docs")
    print(f" ReDoc Docs:         http://127.0.0.1:{settings.FASTAPI_PORT}/redoc")
    print(f"==================================================")
    uvicorn.run("api.main:app", host="0.0.0.0", port=settings.FASTAPI_PORT, reload=False)
