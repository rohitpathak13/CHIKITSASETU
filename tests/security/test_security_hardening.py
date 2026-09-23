"""
CHIKITSASETU - Security Hardening & Audit Verification Tests
Covers Phase 11 minimum security test suite:
1. Unauthenticated chatbot request rejected
2. Authenticated chatbot request succeeds
3. Unauthorized role rejected where appropriate
4. Chatbot cannot access another patient's data
5. Chatbot upload requires authentication
6. Invalid upload rejected
7. Oversized upload rejected
8. Production SECRET_KEY missing causes configuration failure
9. Production PostgreSQL configuration does not silently fall back to SQLite
10. Invalid payment amount rejected
11. Unauthorized refund rejected
12. Raw internal exception details are not returned to clients
"""

import io
import os
import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from backend.config import Settings
from backend.models import User, RoleEnum, Patient, GenderEnum, Bill, BillStatusEnum
from backend.security import get_password_hash, create_access_token
from backend.services import billing_service
from backend.chatbot.retrieval import get_patient_authorized_context
from backend.chatbot.processors.image_processor import validate_and_save_upload, FileValidationError


@pytest.fixture
def hardening_users(db_session):
    admin = User(
        email="hardened_admin@chikitsasetu.ai",
        password_hash=get_password_hash("Password123!"),
        role=RoleEnum.ADMIN,
        first_name="Hardened",
        last_name="Admin",
        is_active=True
    )
    doctor = User(
        email="hardened_doc@chikitsasetu.ai",
        password_hash=get_password_hash("Password123!"),
        role=RoleEnum.DOCTOR,
        first_name="Hardened",
        last_name="Doctor",
        is_active=True
    )
    patient = User(
        email="hardened_pat@chikitsasetu.ai",
        password_hash=get_password_hash("Password123!"),
        role=RoleEnum.PATIENT,
        first_name="Hardened",
        last_name="Patient",
        is_active=True
    )
    db_session.add_all([admin, doctor, patient])
    db_session.flush()

    pat_record = Patient(id=patient.id, dob=date(1990, 1, 1), gender=GenderEnum.OTHER)
    db_session.add(pat_record)
    db_session.commit()

    return {"admin": admin, "doctor": doctor, "patient": patient}


def token_for(user: User) -> str:
    return create_access_token({"sub": str(user.id), "role": user.role.value, "email": user.email})


# -----------------------------------------------------------------------------
# 1 & 2. Chatbot Unauthenticated Rejected (401) & Authenticated Succeeds (200)
# -----------------------------------------------------------------------------
def test_chatbot_unauthenticated_rejected_and_authenticated_succeeds(flask_client, fastapi_client, hardening_users):
    # Flask Unauthenticated
    flask_resp_unauth = flask_client.post("/chatbot/api/message", json={"message": "Help with fever"})
    assert flask_resp_unauth.status_code == 401

    # Flask Authenticated
    doc = hardening_users["doctor"]
    with flask_client.session_transaction() as sess:
        sess["user_id"] = doc.id
        sess["user_role"] = doc.role.value

    flask_resp_auth = flask_client.post("/chatbot/api/message", json={"message": "Help with fever"})
    assert flask_resp_auth.status_code == 200
    assert flask_resp_auth.get_json()["success"] is True

    # FastAPI Unauthenticated
    fastapi_resp_unauth = fastapi_client.post("/api/v1/chatbot/chat", json={"message": "Help with fever"})
    assert fastapi_resp_unauth.status_code in (401, 403)

    # FastAPI Authenticated
    tok = token_for(doc)
    fastapi_resp_auth = fastapi_client.post(
        "/api/v1/chatbot/chat",
        json={"message": "Help with fever"},
        headers={"Authorization": f"Bearer {tok}"}
    )
    assert fastapi_resp_auth.status_code == 200
    assert fastapi_resp_auth.json()["success"] is True


# -----------------------------------------------------------------------------
# 3. Unauthorized Role Rejected
# -----------------------------------------------------------------------------
def test_unauthorized_role_rejected(fastapi_client, hardening_users):
    pat = hardening_users["patient"]
    tok = token_for(pat)

    # Patient trying to access Admin-only doctor creation
    resp = fastapi_client.post(
        "/api/v1/doctors/",
        json={
            "email": "rogue_doctor@chikitsasetu.ai",
            "first_name": "Rogue",
            "last_name": "Doc",
            "specialization": "Cardiology",
            "license_number": "ROGUE-123"
        },
        headers={"Authorization": f"Bearer {tok}"}
    )
    assert resp.status_code == 403


# -----------------------------------------------------------------------------
# 4. Chatbot Cannot Access Another Patient's Data
# -----------------------------------------------------------------------------
def test_chatbot_patient_context_isolation(hardening_users):
    pat = hardening_users["patient"]
    doc = hardening_users["doctor"]

    # Doctor trying to load patient context via patient helper is rejected
    doc_context = get_patient_authorized_context(user_id=doc.id, user_role=doc.role.value)
    assert doc_context["authorized"] is False
    assert len(doc_context["prescriptions"]) == 0

    # Anonymous user has zero access
    anon_context = get_patient_authorized_context(user_id=None, user_role=None)
    assert anon_context["authorized"] is False
    assert len(anon_context["prescriptions"]) == 0


# -----------------------------------------------------------------------------
# 5. Chatbot Upload Requires Authentication
# -----------------------------------------------------------------------------
def test_chatbot_upload_requires_authentication(flask_client, fastapi_client):
    # Flask upload unauthenticated
    flask_resp = flask_client.post("/chatbot/api/upload", data={"file": (io.BytesIO(b"fake"), "test.jpg")})
    assert flask_resp.status_code == 401

    # FastAPI upload unauthenticated
    fastapi_resp = fastapi_client.post(
        "/api/v1/chatbot/upload",
        files={"file": ("test.jpg", b"fake", "image/jpeg")}
    )
    assert fastapi_resp.status_code in (401, 403)


# -----------------------------------------------------------------------------
# 6. Invalid Upload Rejected (Invalid Magic Bytes / Content)
# -----------------------------------------------------------------------------
def test_invalid_upload_rejected():
    # PDF extension but fake non-PDF content (fails magic byte b"%PDF-")
    fake_pdf = b"MZ\x90\x00\x03\x00\x00\x00This is an executable"
    with pytest.raises(FileValidationError):
        validate_and_save_upload(fake_pdf, "malicious.pdf", "application/pdf")

    # Image extension with random corrupt bytes
    corrupt_img = b"corrupt image bytes that PIL cannot parse"
    with pytest.raises(FileValidationError):
        validate_and_save_upload(corrupt_img, "bad.jpg", "image/jpeg")


# -----------------------------------------------------------------------------
# 7. Oversized Upload Rejected (> 10MB)
# -----------------------------------------------------------------------------
def test_oversized_upload_rejected():
    # File with size > 10MB
    oversized = b"%PDF-" + b"0" * (11 * 1024 * 1024)
    with pytest.raises(FileValidationError, match="exceeds the maximum"):
        validate_and_save_upload(oversized, "huge.pdf", "application/pdf")


# -----------------------------------------------------------------------------
# 8. Production SECRET_KEY Missing Causes Configuration Failure
# -----------------------------------------------------------------------------
def test_production_secret_key_missing_fails_fast():
    env_vars = {
        "ENV": "production",
        "SECRET_KEY": "",
        "DATABASE_URL": "postgresql://usr:pwd@localhost:5432/chikitsasetu"
    }
    with patch.dict(os.environ, env_vars, clear=False):
        prod_settings = Settings()
        prod_settings.ENV = "production"
        with pytest.raises(RuntimeError, match="SECRET_KEY must be explicitly set"):
            _ = prod_settings.SECRET_KEY

    # Also fails if secret contains insecure placeholder
    env_vars["SECRET_KEY"] = "chikitsasetu-super-secret-key-change-in-production-2026"
    with patch.dict(os.environ, env_vars, clear=False):
        prod_settings = Settings()
        prod_settings.ENV = "production"
        with pytest.raises(RuntimeError, match="Default or insecure secret keys are strictly forbidden"):
            _ = prod_settings.SECRET_KEY


# -----------------------------------------------------------------------------
# 9. Production PostgreSQL Configuration Does Not Silently Fall Back to SQLite
# -----------------------------------------------------------------------------
def test_production_sqlite_fallback_forbidden():
    env_vars = {
        "ENV": "production",
        "USE_SQLITE": "true",
        "SECRET_KEY": "a-very-secure-production-random-secret-key-12345"
    }
    with patch.dict(os.environ, env_vars, clear=False):
        prod_settings = Settings()
        prod_settings.ENV = "production"
        prod_settings.USE_SQLITE = True
        with pytest.raises(RuntimeError, match="USE_SQLITE is strictly forbidden in production"):
            _ = prod_settings.DATABASE_URL

    # Also fails if DATABASE_URL is SQLite in production
    env_vars_sqlite_url = {
        "ENV": "production",
        "USE_SQLITE": "false",
        "DATABASE_URL": "sqlite:///production.db",
        "SECRET_KEY": "a-very-secure-production-random-secret-key-12345"
    }
    with patch.dict(os.environ, env_vars_sqlite_url, clear=False):
        prod_settings = Settings()
        prod_settings.ENV = "production"
        prod_settings.USE_SQLITE = False
        with pytest.raises(RuntimeError, match="SQLite database URL is strictly forbidden in production"):
            _ = prod_settings.DATABASE_URL


# -----------------------------------------------------------------------------
# 10. Invalid Payment Amount Rejected
# -----------------------------------------------------------------------------
def test_invalid_payment_amount_rejected(db_session, hardening_users):
    pat = hardening_users["patient"]
    admin = hardening_users["admin"]

    bill = billing_service.create_bill(
        db=db_session,
        patient_id=pat.id,
        items=[{"item_type": "consultation", "description": "Consultation", "amount": Decimal("500.00")}],
        actor_id=admin.id
    )
    db_session.commit()

    # Negative amount rejected
    with pytest.raises(billing_service.InvalidBillDataError, match="Payment amount must be greater than zero"):
        billing_service.record_payment(
            db=db_session,
            bill_id=bill.id,
            amount=Decimal("-100.00"),
            payment_method="cash",
            actor_id=admin.id
        )


# -----------------------------------------------------------------------------
# 11. Unauthorized Refund Rejected
# -----------------------------------------------------------------------------
def test_unauthorized_refund_rejected(fastapi_client, db_session, hardening_users):
    pat = hardening_users["patient"]
    admin = hardening_users["admin"]

    bill = billing_service.create_bill(
        db=db_session,
        patient_id=pat.id,
        items=[{"item_type": "consultation", "description": "Consultation", "amount": Decimal("500.00")}],
        actor_id=admin.id
    )
    db_session.commit()

    # Patient token attempting refund
    pat_tok = token_for(pat)
    resp = fastapi_client.post(
        f"/api/v1/billing/invoices/{bill.id}/refund",
        json={"refund_amount": 100.0, "reason": "Patient self refund"},
        headers={"Authorization": f"Bearer {pat_tok}"}
    )
    assert resp.status_code == 403


# -----------------------------------------------------------------------------
# 12. Raw Internal Exception Details Are Not Returned to Clients
# -----------------------------------------------------------------------------
def test_raw_exceptions_not_leaked_to_client(fastapi_client, hardening_users):
    admin = hardening_users["admin"]
    tok = token_for(admin)

    # Force a mock exception inside bill creation
    with patch("backend.services.billing_service.create_bill", side_effect=Exception("Internal DB Connection Crash: SELECT * FROM secret")):
        resp = fastapi_client.post(
            "/api/v1/billing/invoices",
            json={
                "patient_id": hardening_users["patient"].id,
                "items": [{"item_type": "consultation", "description": "Test", "unit_price": 100.0, "quantity": 1}]
            },
            headers={"Authorization": f"Bearer {tok}"}
        )
        assert resp.status_code == 500
        data = resp.json()
        assert "Internal DB Connection Crash" not in data["detail"]
        assert "SELECT * FROM secret" not in data["detail"]
        assert data["detail"] == "Bill creation failed. Please try again."
