# CHIKITSASETU — Duplicate File Analysis (Phase 3)

**Audit Date**: 2026-09-23T16:26:00+05:30  
**Status**: Comprehensive Duplicate Scan Completed (Zero Redundant Files)

---

## 1. Automated Scan Results

| Check Category | Search Criteria | Result | Notes |
|---|---|---|---|
| **Backup & Copy Patterns** | `*_old*`, `*_backup*`, `*_bak*`, `*_copy*`, `*_final*`, `*_new*`, `test2*`, `backup_*`, `temp_*` | **0 found** | No lingering ad-hoc backups or temporary copy files exist in the project tree. |
| **Exact Content Hash Match** | SHA-256 match across all non-git, non-cache files | **0 found** | Every file in the repository possesses unique content. |
| **Zero-Byte Empty Files** | File length = 0 bytes | **0 found** | No abandoned zero-byte placeholder files exist. |

---

## 2. Review of Same-Name Files Across Architectural Layers

The following files share identical base names across distinct subpackages. Each was verified against imports, routes, and template render calls to confirm architectural necessity:

| Filename | Locations & Architectural Roles | References Found | Recommended Action |
|---|---|---|---|
| `analytics.py` | 1. `backend/routes/analytics.py` (Flask views)<br>2. `backend/fastapi_service/routers/analytics.py` (FastAPI REST)<br>3. `backend/models/clinical.py` & services | - Flask blueprint registered in `backend/app/__init__.py`<br>- FastAPI router included in `backend/fastapi_service/main.py`<br>- Unit tests: `tests/unit/test_analytics_service.py` | **KEEP BOTH**: One handles server-side Jinja2 web rendering, while the other serves high-speed JSON APIs with OpenAPI docs. |
| `auth.py` | 1. `backend/routes/auth.py` (Flask session auth)<br>2. `backend/fastapi_service/routers/auth.py` (FastAPI OAuth2/JWT) | - Flask auth routes (`/login`, `/register`, `/logout`)<br>- FastAPI auth routes (`/api/v1/auth/token`)<br>- Integration tests: `tests/integration/test_auth_rbac.py` | **KEEP BOTH**: Necessary for dual WSGI (session-based) and ASGI (token-based) authentication. |
| `billing.py`, `laboratory.py`, `pharmacy.py`, `inpatient.py` | 1. `backend/routes/*.py`<br>2. `backend/fastapi_service/routers/*.py`<br>3. `backend/models/*.py` | - Respective Flask blueprints<br>- Respective FastAPI routers<br>- Respective SQLAlchemy ORM models | **KEEP ALL**: Standard layered architecture separating presentation routes, API routers, and database entity definitions. |
| `dashboard.html` | 1. `frontend/templates/admin/dashboard.html`<br>2. `frontend/templates/doctor/dashboard.html`<br>3. `frontend/templates/patient/dashboard.html`<br>4. `frontend/templates/nurse/dashboard.html`<br>5. `frontend/templates/receptionist/dashboard.html`<br>6. `frontend/templates/ipd/dashboard.html`<br>7. `frontend/templates/pharmacy/dashboard.html`<br>8. `frontend/templates/laboratory/dashboard.html`<br>9. `frontend/templates/billing/dashboard.html`<br>10. `frontend/templates/analytics/dashboard.html` | - Rendered specifically by each role's dashboard endpoint (e.g. `admin_bp`, `doctor_bp`, `patient_bp`, etc.) | **KEEP ALL**: Role-specific dashboards presenting distinct operational workspaces for 7+ RBAC personas. |
| `loader.py`, `evaluator.py`, `metrics.py`, `trainer.py`, `predictor.py` | 1. `ml/no_show_prediction/*`<br>2. `ml/risk_prediction/*` | - Imported by respective pipeline runners in `ml/train/` and `scripts/` | **KEEP ALL**: Modular 6-tier architecture isolating No-Show binary prediction from Patient Clinical Risk multiclass prediction. |

---

## 3. Conclusion

No redundant or duplicate files require deletion. All identically named files serve distinct, verified purposes across different architectural layers, modules, and user roles.
