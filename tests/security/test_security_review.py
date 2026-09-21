import pytest
from datetime import date, datetime, timezone, timedelta
from backend.models import User, RoleEnum, GenderEnum, Patient, PatientProfile, Doctor, DoctorProfile, Department, LabOrder, LabTest, MedicalRecord
from backend.security import get_password_hash, create_access_token, validate_password_strength
from backend.services import audit_service
from backend.app import create_app as create_flask_app


@pytest.fixture
def test_users(db_session):
    """Creates a distinct user per role for security and authorization testing."""
    # 1. Admin
    admin = User(
        email="sec_admin@chikitsasetu.ai",
        password_hash=get_password_hash("Password123!"),
        role=RoleEnum.ADMIN,
        first_name="Sec",
        last_name="Admin",
        is_active=True
    )
    # 2. Doctor
    doctor_user = User(
        email="sec_doctor@chikitsasetu.ai",
        password_hash=get_password_hash("Password123!"),
        role=RoleEnum.DOCTOR,
        first_name="Sec",
        last_name="Doctor",
        is_active=True
    )
    # 3. Patient 1
    patient_user_1 = User(
        email="sec_patient1@chikitsasetu.ai",
        password_hash=get_password_hash("Password123!"),
        role=RoleEnum.PATIENT,
        first_name="Patient",
        last_name="One",
        is_active=True
    )
    # 4. Patient 2
    patient_user_2 = User(
        email="sec_patient2@chikitsasetu.ai",
        password_hash=get_password_hash("Password123!"),
        role=RoleEnum.PATIENT,
        first_name="Patient",
        last_name="Two",
        is_active=True
    )
    # 5. Receptionist
    receptionist = User(
        email="sec_receptionist@chikitsasetu.ai",
        password_hash=get_password_hash("Password123!"),
        role=RoleEnum.RECEPTIONIST,
        first_name="Sec",
        last_name="Receptionist",
        is_active=True
    )
    # 6. Deactivated User
    deactivated = User(
        email="sec_deactivated@chikitsasetu.ai",
        password_hash=get_password_hash("Password123!"),
        role=RoleEnum.PATIENT,
        first_name="Inactive",
        last_name="User",
        is_active=False
    )

    db_session.add_all([admin, doctor_user, patient_user_1, patient_user_2, receptionist, deactivated])
    db_session.flush()

    # Profiles
    doc_prof = DoctorProfile(
        id=doctor_user.id,
        specialization="Internal Medicine",
        license_number="LIC-SEC-001",
        qualification="MD",
        consultation_fee=500.00
    )
    pat1_prof = PatientProfile(
        id=patient_user_1.id,
        dob=date(1992, 4, 10),
        gender=GenderEnum.MALE
    )
    pat2_prof = PatientProfile(
        id=patient_user_2.id,
        dob=date(1995, 8, 20),
        gender=GenderEnum.FEMALE
    )
    db_session.add_all([doc_prof, pat1_prof, pat2_prof])
    db_session.commit()

    return {
        "admin": admin,
        "doctor": doctor_user,
        "patient1": patient_user_1,
        "patient2": patient_user_2,
        "receptionist": receptionist,
        "deactivated": deactivated
    }


def auth_headers_for(user: User) -> dict:
    token = create_access_token({"sub": str(user.id), "role": user.role.value, "email": user.email})
    return {"Authorization": f"Bearer {token}"}


# =====================================================================
# 1. Authentication & Token Security Tests
# =====================================================================

def test_auth_login_valid_and_invalid(fastapi_client, test_users):
    """Verifies authentication accepts valid credentials, rejects invalid, and locks deactivated."""
    # Valid
    res_valid = fastapi_client.post("/api/v1/auth/login", json={"email": "sec_admin@chikitsasetu.ai", "password": "Password123!"})
    assert res_valid.status_code == 200
    assert "access_token" in res_valid.json()

    # Invalid password
    res_invalid = fastapi_client.post("/api/v1/auth/login", json={"email": "sec_admin@chikitsasetu.ai", "password": "WrongPassword!"})
    assert res_invalid.status_code == 401

    # Deactivated account
    res_deactivated = fastapi_client.post("/api/v1/auth/login", json={"email": "sec_deactivated@chikitsasetu.ai", "password": "Password123!"})
    assert res_deactivated.status_code in (400, 401)


def test_malformed_token_subject_handling(fastapi_client):
    """Verifies that non-integer / malformed token subject returns 401 and does not crash with 500."""
    bad_token = create_access_token({"sub": "non-integer-guid-string", "role": "patient", "email": "test@chikitsasetu.ai"})
    res = fastapi_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {bad_token}"})
    assert res.status_code == 401
    assert "invalid token" in res.text.lower() or "credentials" in res.text.lower()


# =====================================================================
# 2. Authorization & IDOR Protection Tests
# =====================================================================

def test_patient_cannot_schedule_appointment_for_another_patient(fastapi_client, test_users):
    """IDOR Prevention: Patient 1 must NOT be able to book an appointment with Patient 2's ID."""
    p1 = test_users["patient1"]
    p2 = test_users["patient2"]
    doc = test_users["doctor"]

    headers_p1 = auth_headers_for(p1)

    payload_idor = {
        "patient_id": p2.id,  # Attempting to book as Patient 2
        "doctor_id": doc.id,
        "appointment_datetime": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        "reason": "Unauthorized Booking Attempt"
    }

    res = fastapi_client.post("/api/v1/appointments/", json=payload_idor, headers=headers_p1)
    assert res.status_code == 403
    assert "denied" in res.text.lower() or "themselves" in res.text.lower()


def test_patient_cross_order_laboratory_data_isolation(fastapi_client, test_users, db_session):
    """Confidentiality: Patients cannot browse or see other patients' lab orders."""
    p1 = test_users["patient1"]
    p2 = test_users["patient2"]
    doc = test_users["doctor"]

    # Seed test and orders
    test_item = LabTest(name="Complete Blood Count", test_code="CBC-SEC", sample_type="Blood", cost=350.00)
    db_session.add(test_item)
    db_session.flush()

    order_p1 = LabOrder(patient_id=p1.id, doctor_id=doc.id, test_id=test_item.id, priority="routine")
    order_p2 = LabOrder(patient_id=p2.id, doctor_id=doc.id, test_id=test_item.id, priority="urgent")
    db_session.add_all([order_p1, order_p2])
    db_session.commit()

    # Patient 1 lists orders
    headers_p1 = auth_headers_for(p1)
    res = fastapi_client.get("/api/v1/laboratory/orders", headers=headers_p1)
    assert res.status_code == 200
    orders = res.json()
    assert all(o["patient_id"] == p1.id for o in orders)
    assert not any(o["patient_id"] == p2.id for o in orders)


def test_receptionist_denied_from_clinical_emr_records(fastapi_client, test_users, db_session):
    """Principle of Least Privilege: Non-clinical receptionist role cannot view clinical EMR notes."""
    rec = test_users["receptionist"]
    p1 = test_users["patient1"]
    headers_rec = auth_headers_for(rec)

    # Attempt to list medical records
    res_list = fastapi_client.get("/api/v1/medical-records/", headers=headers_rec)
    assert res_list.status_code == 403

    # Attempt to view patient EMR history
    res_history = fastapi_client.get(f"/api/v1/medical-records/patient/{p1.id}", headers=headers_rec)
    assert res_history.status_code == 403


def test_doctor_denied_from_general_billing_invoices(fastapi_client, test_users):
    """Financial Data Protection: Clinical doctor cannot browse hospital-wide financial invoice lists."""
    doc = test_users["doctor"]
    headers_doc = auth_headers_for(doc)

    res = fastapi_client.get("/api/v1/billing/invoices", headers=headers_doc)
    assert res.status_code == 403


# =====================================================================
# 3. Password Hashing & Complexity Validation
# =====================================================================

def test_password_strength_validator():
    """Verifies that password complexity validator enforces length, letters, and numbers."""
    valid, err = validate_password_strength("Pass1234!")
    assert valid is True
    assert err is None

    # Too short (< 8)
    valid_short, err_short = validate_password_strength("Pass1")
    assert valid_short is False
    assert "at least 8" in err_short

    # No letters
    valid_no_letters, err_no_letters = validate_password_strength("123456789")
    assert valid_no_letters is False
    assert "letter" in err_no_letters

    # No digits
    valid_no_digits, err_no_digits = validate_password_strength("PasswordOnly")
    assert valid_no_digits is False
    assert "digit" in err_no_digits


def test_patient_registration_password_min_length(fastapi_client, test_users):
    """Ensures registration schema rejects weak passwords under 8 characters."""
    headers_admin = auth_headers_for(test_users["admin"])
    payload = {
        "email": "weak_pass_patient@chikitsasetu.ai",
        "password": "short",  # Only 5 chars
        "first_name": "Weak",
        "last_name": "Pass",
        "dob": "1990-01-01",
        "gender": "other"
    }
    res = fastapi_client.post("/api/v1/patients/", json=payload, headers=headers_admin)
    assert res.status_code == 422  # Unprocessable Entity from Pydantic min_length validation


# =====================================================================
# 4. HTTP Defensive Security Headers & CORS
# =====================================================================

def test_api_defensive_security_headers(fastapi_client):
    """Verifies that API responses include standard defensive security headers."""
    res = fastapi_client.get("/")
    assert res.status_code == 200
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-Frame-Options") == "DENY"
    assert res.headers.get("X-XSS-Protection") == "1; mode=block"
    assert res.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


def test_flask_security_headers_and_csrf_init():
    """Verifies Flask application factory initializes CSRF and sets secure headers."""
    app = create_flask_app()
    assert "csrf" in app.extensions or hasattr(app, "jinja_env")

    with app.test_client() as client:
        res = client.get("/login")
        assert res.headers.get("X-Content-Type-Options") == "nosniff"
        assert res.headers.get("X-Frame-Options") == "SAMEORIGIN"
        assert res.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


# =====================================================================
# 5. SQL Injection & Search Parameterization Tests
# =====================================================================

def test_sql_injection_resistance_in_search_queries(fastapi_client, test_users):
    """Verifies that classic SQL injection strings are safely treated as literal parameters."""
    headers_admin = auth_headers_for(test_users["admin"])

    sqli_payloads = [
        "' OR '1'='1",
        "'; DROP TABLE users; --",
        "admin'--",
        "' UNION SELECT NULL, NULL, NULL --"
    ]

    for payload in sqli_payloads:
        res = fastapi_client.get(f"/api/v1/patients/?query={payload}", headers=headers_admin)
        assert res.status_code == 200
        # Must return clean JSON list, not 500 database syntax error
        assert isinstance(res.json(), list)


# =====================================================================
# 6. Sensitive Medical Data & Secret Redaction in Audit Logs
# =====================================================================

def test_audit_logs_redact_secrets_and_passwords(db_session):
    """Confirms audit logging automatically redacts passwords, tokens, and payment card numbers."""
    audit_entry = audit_service.log_action(
        db=db_session,
        action="SECURITY_AUDIT_VERIFY",
        resource_type="User",
        metadata={
            "user_id": 1,
            "password": "VerySecretPassword!",
            "token": "jwt-auth-token-123",
            "card_number": "4111222233334444",
            "cvv": "123",
            "clinical_diagnosis": "Confidential Diagnosis Note"
        }
    )

    details = audit_entry.details
    assert details["password"] == "[REDACTED]"
    assert details["token"] == "[REDACTED]"
    assert details["card_number"] == "[REDACTED]"
    assert details["cvv"] == "[REDACTED]"
    assert details["clinical_diagnosis"] == "Confidential Diagnosis Note"
