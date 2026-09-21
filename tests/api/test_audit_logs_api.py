import pytest
from backend.models import User, RoleEnum
from backend.security import get_password_hash, create_access_token
from backend.services import audit_service


@pytest.fixture
def doctor_user(db_session):
    doc = User(
        email="doctor_api_test@chikitsasetu.ai",
        password_hash=get_password_hash("Password123!"),
        role=RoleEnum.DOCTOR,
        first_name="Doctor",
        last_name="Test",
        is_active=True
    )
    db_session.add(doc)
    db_session.commit()
    return doc


@pytest.fixture
def doctor_auth_headers(doctor_user):
    token = create_access_token({"sub": str(doctor_user.id), "role": doctor_user.role.value, "email": doctor_user.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def patient_user(db_session):
    pat = User(
        email="patient_api_test@chikitsasetu.ai",
        password_hash=get_password_hash("Password123!"),
        role=RoleEnum.PATIENT,
        first_name="Patient",
        last_name="Test",
        is_active=True
    )
    db_session.add(pat)
    db_session.commit()
    return pat


@pytest.fixture
def patient_auth_headers(patient_user):
    token = create_access_token({"sub": str(patient_user.id), "role": patient_user.role.value, "email": patient_user.email})
    return {"Authorization": f"Bearer {token}"}


def test_admin_can_access_audit_logs(fastapi_client, admin_auth_headers, db_session):
    """Verifies an admin can view and search audit logs."""
    # Seed a log
    audit_service.log_action(db_session, action="TEST_SEED", resource_type="System", metadata={"info": "seeded entry"})

    response = fastapi_client.get("/api/v1/audit-logs", headers=admin_auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 1
    assert any(item["action"] == "TEST_SEED" for item in data["items"])


def test_non_admin_forbidden_from_audit_logs(fastapi_client, doctor_auth_headers, patient_auth_headers):
    """Verifies non-admin roles (Doctor, Patient) receive 403 Forbidden."""
    # Doctor attempt
    doc_res = fastapi_client.get("/api/v1/audit-logs", headers=doctor_auth_headers)
    assert doc_res.status_code == 403
    assert "not permitted" in doc_res.text.lower() or "forbidden" in doc_res.text.lower()

    # Patient attempt
    pat_res = fastapi_client.get("/api/v1/audit-logs", headers=patient_auth_headers)
    assert pat_res.status_code == 403
    assert "not permitted" in pat_res.text.lower() or "forbidden" in pat_res.text.lower()


def test_unauthenticated_request_rejected(fastapi_client):
    """Verifies missing token returns 401 Unauthorized."""
    res = fastapi_client.get("/api/v1/audit-logs")
    assert res.status_code == 401


def test_filter_audit_logs_by_action_and_resource(fastapi_client, admin_auth_headers, db_session):
    """Verifies query parameters for action and resource_type filtering."""
    audit_service.log_action(db_session, action="FILTER_ACTION_ALPHA", resource_type="AlphaType")
    audit_service.log_action(db_session, action="FILTER_ACTION_BETA", resource_type="BetaType")

    # Filter by action
    res_act = fastapi_client.get("/api/v1/audit-logs?action=FILTER_ACTION_ALPHA", headers=admin_auth_headers)
    assert res_act.status_code == 200
    data_act = res_act.json()
    assert data_act["total"] == 1
    assert data_act["items"][0]["action"] == "FILTER_ACTION_ALPHA"

    # Filter by resource_type
    res_type = fastapi_client.get("/api/v1/audit-logs?resource_type=BetaType", headers=admin_auth_headers)
    assert res_type.status_code == 200
    data_type = res_type.json()
    assert data_type["total"] == 1
    assert data_type["items"][0]["resource_type"] == "BetaType"


def test_audit_logs_helper_endpoints(fastapi_client, admin_auth_headers, db_session):
    """Verifies /actions, /resource-types, and /stats endpoints."""
    audit_service.log_action(db_session, action="ACTION_ONE", resource_type="ResourceOne")
    audit_service.log_action(db_session, action="ACTION_TWO", resource_type="ResourceTwo")

    # Distinct actions
    act_res = fastapi_client.get("/api/v1/audit-logs/actions", headers=admin_auth_headers)
    assert act_res.status_code == 200
    actions_list = act_res.json()["actions"]
    assert "ACTION_ONE" in actions_list
    assert "ACTION_TWO" in actions_list

    # Distinct resource types
    res_res = fastapi_client.get("/api/v1/audit-logs/resource-types", headers=admin_auth_headers)
    assert res_res.status_code == 200
    res_list = res_res.json()["resource_types"]
    assert "ResourceOne" in res_list
    assert "ResourceTwo" in res_list

    # Stats
    stats_res = fastapi_client.get("/api/v1/audit-logs/stats", headers=admin_auth_headers)
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert stats["total_logs"] >= 2


def test_single_audit_log_endpoint(fastapi_client, admin_auth_headers, db_session):
    """Verifies fetching specific audit log by ID and 404 for invalid ID."""
    entry = audit_service.log_action(
        db_session,
        action="SINGLE_TEST",
        resource_type="Document",
        resource_id=999,
        metadata={"key": "value"}
    )

    res = fastapi_client.get(f"/api/v1/audit-logs/{entry.id}", headers=admin_auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == entry.id
    assert data["action"] == "SINGLE_TEST"
    assert data["resource_id"] == 999

    res_404 = fastapi_client.get("/api/v1/audit-logs/999999", headers=admin_auth_headers)
    assert res_404.status_code == 404


def test_end_to_end_login_logout_and_patient_auditing(fastapi_client, admin_auth_headers, db_session):
    """
    Verifies that real REST operations (login, logout, patient registration)
    automatically generate audit logs with redacted sensitive information.
    """
    # 1. Login via REST API
    login_res = fastapi_client.post(
        "/api/v1/auth/login",
        json={"email": "test_admin@chikitsasetu.ai", "password": "Password123!"}
    )
    assert login_res.status_code == 200

    # 2. Verify login audit log was generated
    audit_res = fastapi_client.get(
        "/api/v1/audit-logs?action=USER_LOGIN",
        headers=admin_auth_headers
    )
    assert audit_res.status_code == 200
    login_logs = audit_res.json()["items"]
    assert len(login_logs) >= 1
    # Verify password is NOT in the audit log details
    assert "Password123!" not in str(login_logs[0]["details"])
    assert "password" not in login_logs[0]["details"]

    # 3. Call REST logout
    logout_res = fastapi_client.post("/api/v1/auth/logout", headers=admin_auth_headers)
    assert logout_res.status_code == 200

    # Verify logout audit log
    logout_audit_res = fastapi_client.get(
        "/api/v1/audit-logs?action=USER_LOGOUT",
        headers=admin_auth_headers
    )
    assert logout_audit_res.status_code == 200
    assert any(log["action"] == "USER_LOGOUT" for log in logout_audit_res.json()["items"])

    # 4. Register a patient via REST API
    patient_payload = {
        "email": "audited_patient@example.com",
        "password": "SecretPatientPass123!",
        "first_name": "Audit",
        "last_name": "Patient",
        "phone": "9998887776",
        "dob": "1990-05-15",
        "gender": "female",
        "blood_group": "A+",
        "emergency_contact_name": "Emergency Person",
        "emergency_contact_phone": "9998887770",
        "address": "123 Health Ave",
        "allergies": "None",
        "chronic_conditions": "None"
    }
    create_pat_res = fastapi_client.post("/api/v1/patients/", json=patient_payload, headers=admin_auth_headers)
    assert create_pat_res.status_code == 201

    # Verify patient creation audit log
    pat_audit_res = fastapi_client.get(
        "/api/v1/audit-logs?action=PATIENT_CREATE",
        headers=admin_auth_headers
    )
    assert pat_audit_res.status_code == 200
    pat_logs = pat_audit_res.json()["items"]
    assert len(pat_logs) >= 1
    # Verify patient password was NOT logged
    assert "SecretPatientPass123!" not in str(pat_logs[0]["details"])
    assert "password" not in pat_logs[0]["details"]
