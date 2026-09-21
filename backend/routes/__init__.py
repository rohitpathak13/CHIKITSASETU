"""
CHIKITSASETU - Backend Routes / Flask Blueprints
"""
from backend.routes.auth import auth_bp
from backend.routes.admin import admin_bp
from backend.routes.doctor import doctor_bp
from backend.routes.patient import patient_bp
from backend.routes.receptionist import receptionist_bp
from backend.routes.nurse import nurse_bp
from backend.routes.pharmacy import pharmacy_bp
from backend.routes.laboratory import laboratory_bp
from backend.routes.billing import billing_bp
from backend.routes.analytics import analytics_bp
from backend.routes.notifications import notifications_bp
from backend.routes.appointment import appointment_bp
from backend.routes.ipd import ipd_bp

__all__ = [
    "auth_bp",
    "admin_bp",
    "doctor_bp",
    "patient_bp",
    "receptionist_bp",
    "nurse_bp",
    "pharmacy_bp",
    "laboratory_bp",
    "billing_bp",
    "analytics_bp",
    "notifications_bp",
    "appointment_bp",
    "ipd_bp",
]
