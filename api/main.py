from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from core.config import settings
from core.database import init_db
from api.routers import (
    auth,
    patients,
    doctors,
    appointments,
    medical_records,
    prescriptions,
    laboratory,
    pharmacy,
    admissions,
    billing,
    analytics,
    clinical,
    inpatient,
    ml_inference,
    ml,
    notifications,
    audit
)

openapi_tags = [
    {"name": "Authentication", "description": "OAuth2 standard token and JSON authentication endpoints."},
    {"name": "Audit Logs", "description": "Administrative audit logging, compliance tracking, and security monitoring."},
    {"name": "Patients", "description": "Patient registration, master profile management, and longitudinal history."},
    {"name": "Doctors", "description": "Medical physician directory, credentialing, schedules, and clinical workload."},
    {"name": "Appointments", "description": "Outpatient scheduling, token allocation, and ML attendance triage."},
    {"name": "Medical Records & EMR", "description": "Electronic medical records, vital signs, diagnoses, and encounters."},
    {"name": "Prescriptions", "description": "Electronic prescription ordering, multi-item regimens, and FEFO dispensing."},
    {"name": "Laboratory Diagnostics", "description": "Diagnostic test catalog, clinical orders, sample collection, and results."},
    {"name": "Pharmacy", "description": "Medicine formulary, batch inventory, FEFO dispensing, and stock transactions."},
    {"name": "Inpatient Admissions", "description": "IPD patient admission, bed allocation, transfers, and discharge billing."},
    {"name": "Hospital Billing", "description": "7-component invoice itemization, receipts ledger, and refund processing."},
    {"name": "Hospital Analytics & BI", "description": "15-domain BI metrics, executive KPIs, and interactive Plotly visualizations."},
    {"name": "Machine Learning Inference", "description": "Real-time clinical deterioration, readmission, and no-show prediction engines."},
    {"name": "Notifications", "description": "In-app role-based alerts, appointment reminders, stock warnings, and read tracking."}
]

app = FastAPI(
    title="CHIKITSASETU API",
    description="Advanced Hospital Management, Healthcare Analytics and AI/ML API",
    version=settings.PROJECT_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=openapi_tags
)

# Cross-Origin Resource Sharing (CORS) with explicit trusted origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Enforces standard defensive HTTP security headers on all API responses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# Register Versioned API Routers under /api/v1
API_PREFIX = "/api/v1"

# 11 Canonical Versioned Routers
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(patients.router, prefix=API_PREFIX)
app.include_router(doctors.router, prefix=API_PREFIX)
app.include_router(appointments.router, prefix=API_PREFIX)
app.include_router(medical_records.router, prefix=API_PREFIX)
app.include_router(prescriptions.router, prefix=API_PREFIX)
app.include_router(laboratory.router, prefix=API_PREFIX)
app.include_router(pharmacy.router, prefix=API_PREFIX)
app.include_router(admissions.router, prefix=API_PREFIX)
app.include_router(billing.router, prefix=API_PREFIX)
app.include_router(analytics.router, prefix=API_PREFIX)

# Compatibility Routers
app.include_router(clinical.router, prefix=API_PREFIX)
app.include_router(inpatient.router, prefix=API_PREFIX)
app.include_router(ml_inference.router, prefix=API_PREFIX)
app.include_router(ml.router, prefix=API_PREFIX)
app.include_router(notifications.router, prefix=API_PREFIX)
app.include_router(audit.router, prefix=API_PREFIX)


@app.on_event("startup")
def on_startup():
    """Initializes database tables upon microservice startup."""
    init_db()


@app.get("/")
def root():
    return {
        "service": "CHIKITSASETU REST & ML Engine",
        "status": "operational",
        "version": settings.PROJECT_VERSION,
        "docs": "/docs",
        "redoc": "/redoc",
        "openapi": "/openapi.json"
    }
