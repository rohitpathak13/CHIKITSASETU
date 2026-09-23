# CHIKITSASETU — Initial Project Audit Baseline (Phase 1)

**Date & Time**: 2026-09-23T16:25:00+05:30  
**Project Path**: `D:\CHIKITSASETU`  
**Current Git Branch**: `main`  
**Latest Git Commit**: `2b62a1b Update CHIKITSASETU project`  

---

## 1. Runtime Environment & Technology Versions

| Component | Detected Version | Details |
|---|---|---|
| **Python** | 3.13.9 (64-bit) | Anaconda, Inc. |
| **Flask** | 3.1.2 | WSGI Web Portal Framework |
| **FastAPI** | 0.141.1 | ASGI REST API & ML Inference Engine |
| **SQLAlchemy** | 2.0.43 | Object-Relational Mapping (ORM) |
| **Alembic** | 1.18.3 | Database Schema Migrations Engine |
| **Pydantic** | 2.12.4 | Data Validation & Schema Modeling |

---

## 2. Major Project Dependencies

- **Web & API**: `flask`, `flask-wtf`, `flask-migrate`, `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `email-validator`
- **Database & Migration**: `sqlalchemy`, `alembic`, `psycopg2-binary`, `sqlite3` (built-in)
- **Security & Cryptography**: `passlib[bcrypt]`, `bcrypt`, `pyjwt`, `python-multipart`
- **Machine Learning & Analytics**: `numpy`, `pandas`, `scikit-learn`, `joblib`, `plotly`
- **Document & Multimodal Processing**: `pypdf`, `Pillow (PIL)`
- **Testing & Utilities**: `pytest`, `httpx`, `requests`, `python-dateutil`, `gunicorn`

---

## 3. Application Entry Points & Startup Commands

- **Flask Clinical Portal Entrypoint**: `run_flask.py`
  - Factory: `backend.app:create_app()`
  - Host/Port: `http://127.0.0.1:5000` (configurable via `FLASK_PORT`)
  - Dev Command: `python run_flask.py`
  - Prod WSGI: `gunicorn -w 4 -b 0.0.0.0:5000 "backend:create_app()"`
- **FastAPI REST & ML Entrypoint**: `run_fastapi.py`
  - ASGI App: `backend.fastapi_service.main:app`
  - Host/Port: `http://127.0.0.1:8000` (configurable via `FASTAPI_PORT`)
  - Swagger UI: `http://127.0.0.1:8000/docs`
  - ReDoc: `http://127.0.0.1:8000/redoc`
  - Dev Command: `python run_fastapi.py`
  - Prod ASGI: `uvicorn backend.fastapi_service.main:app --host 0.0.0.0 --port 8000 --workers 2`
- **Unified Dual-Server Launcher**: `run_all.py` (and `run.bat`)
  - Launches FastAPI followed by Flask with graceful process shutdown.
- **Container Entrypoint**: `docker-entrypoint.sh` / `Dockerfile` / `docker-compose.yml`

---

## 4. Current Working Tree State

- **Modified Files**:
  - `.env.example`
  - `backend/app/__init__.py`
  - `backend/config.py`
  - `backend/fastapi_service/main.py`
  - `frontend/templates/base.html`
- **Untracked Additive Files (AI Health Assistant Feature)**:
  - `backend/chatbot/`
  - `backend/fastapi_service/routers/chatbot.py`
  - `frontend/static/css/chatbot.css`
  - `frontend/static/js/chatbot.js`
  - `frontend/templates/components/chatbot_widget.html`
  - `tests/unit/test_chatbot_service.py`
