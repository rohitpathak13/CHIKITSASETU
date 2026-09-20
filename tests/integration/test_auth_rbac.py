import pytest
from datetime import date
from flask import session
from core.models import User, RoleEnum, Patient, AuditLog
from core.security import get_password_hash, verify_password
from web.decorators import (
    normalize_role, get_current_user, get_current_role,
    is_authenticated, has_role
)


def create_test_user(db_session, email, role, password="Password123!", is_active=True, first_name="Test", last_name="User"):
    """Helper to ensure a clean test user exists in the test database."""
    user = db_session.query(User).filter(User.email == email).first()
    if not user:
        user = User(
            email=email,
            password_hash=get_password_hash(password),
            role=role,
            first_name=first_name,
            last_name=last_name,
            is_active=is_active
        )
        db_session.add(user)
        db_session.commit()
    return user


# =====================================================================
# 1. Password Hashing & Validation Tests
# =====================================================================

def test_password_hashing_security():
    raw_pass = "SecurePass2026!"
    hashed = get_password_hash(raw_pass)

    assert hashed != raw_pass
    assert hashed.startswith("$2")  # Bcrypt hash format
    assert verify_password(raw_pass, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False

    # Verify model methods
    user = User(email="hash_test@medicare.ai", role=RoleEnum.PATIENT, first_name="Hash", last_name="Tester")
    user.set_password(raw_pass)
    assert user.check_password(raw_pass) is True
    assert user.check_password("InvalidPass") is False


# =====================================================================
# 2. Valid Login Tests Across All 7 Roles
# =====================================================================

@pytest.mark.parametrize("role,email,expected_dashboard_endpoint", [
    (RoleEnum.ADMIN, "admin_user@medicare.ai", "/admin/"),
    (RoleEnum.DOCTOR, "doctor_user@medicare.ai", "/doctor/"),
    (RoleEnum.RECEPTIONIST, "rec_user@medicare.ai", "/receptionist/"),
    (RoleEnum.NURSE, "nurse_user@medicare.ai", "/nurse/"),
    (RoleEnum.PHARMACIST, "pharm_user@medicare.ai", "/pharmacy/"),
    (RoleEnum.LAB_TECH, "lab_user@medicare.ai", "/laboratory/"),
    (RoleEnum.PATIENT, "pat_user@medicare.ai", "/patient/"),
])
def test_valid_login_all_roles(flask_client, db_session, role, email, expected_dashboard_endpoint):
    create_test_user(db_session, email=email, role=role, password="Password123!", first_name="Role", last_name=role.value)

    res = flask_client.post("/login", data={
        "email": email,
        "password": "Password123!"
    }, follow_redirects=False)

    # Verify HTTP 302 Redirect to the designated role portal
    assert res.status_code == 302
    assert expected_dashboard_endpoint in res.headers["Location"]

    # Verify session contents
    with flask_client.session_transaction() as sess:
        assert sess["user_email"] == email
        assert sess["user_role"] == role.value
        assert "user_id" in sess
        assert "login_time" in sess

    # Verify Security Audit Log created
    audit = db_session.query(AuditLog).filter(
        AuditLog.action == "USER_LOGIN",
        AuditLog.details_json.like(f"%Login Successful%")
    ).order_by(AuditLog.timestamp.desc()).first()
    assert audit is not None

    # Clean up session for subsequent test iterations
    flask_client.get("/logout")


# =====================================================================
# 3. Invalid Password & Nonexistent Email Tests
# =====================================================================

def test_invalid_password_returns_401(flask_client, db_session):
    create_test_user(db_session, email="dr.login_fail@medicare.ai", role=RoleEnum.DOCTOR)

    res = flask_client.post("/login", data={
        "email": "dr.login_fail@medicare.ai",
        "password": "CompletelyWrongPassword!"
    })

    assert res.status_code == 401
    assert b"Invalid email or password" in res.data

    with flask_client.session_transaction() as sess:
        assert "user_id" not in sess

    # Verify Failed Login Audit Log
    audit = db_session.query(AuditLog).filter(
        AuditLog.action == "USER_LOGIN_FAILED"
    ).order_by(AuditLog.timestamp.desc()).first()
    assert audit is not None
    assert "dr.login_fail@medicare.ai" in audit.details_json


def test_nonexistent_email_returns_401(flask_client, db_session):
    res = flask_client.post("/login", data={
        "email": "does_not_exist@medicare.ai",
        "password": "Password123!"
    })

    assert res.status_code == 401
    assert b"Invalid email or password" in res.data

    with flask_client.session_transaction() as sess:
        assert "user_id" not in sess


def test_deactivated_user_login_blocked(flask_client, db_session):
    create_test_user(db_session, email="deactivated@medicare.ai", role=RoleEnum.PATIENT, is_active=False)

    res = flask_client.post("/login", data={
        "email": "deactivated@medicare.ai",
        "password": "Password123!"
    })

    assert res.status_code == 403
    assert b"account has been deactivated" in res.data

    with flask_client.session_transaction() as sess:
        assert "user_id" not in sess


# =====================================================================
# 4. Unauthorized Access (Unauthenticated Users)
# =====================================================================

@pytest.mark.parametrize("protected_route", [
    "/admin/",
    "/doctor/",
    "/patient/",
    "/nurse/",
    "/pharmacy/",
    "/laboratory/",
    "/receptionist/",
    "/billing/",
    "/analytics/",
    "/notifications/"
])
def test_unauthenticated_access_redirects_to_login(flask_client, protected_route):
    # Ensure fresh unauthenticated state
    flask_client.get("/logout")

    res = flask_client.get(protected_route, follow_redirects=False)
    assert res.status_code == 302
    assert "/login" in res.headers["Location"]
    assert "next=" in res.headers["Location"]


def test_safe_redirect_after_login(flask_client, db_session):
    create_test_user(db_session, email="redirect_user@medicare.ai", role=RoleEnum.ADMIN)

    # Login with a safe internal next parameter
    res = flask_client.post("/login", data={
        "email": "redirect_user@medicare.ai",
        "password": "Password123!",
        "next": "/admin/audits"
    }, follow_redirects=False)

    assert res.status_code == 302
    assert res.headers["Location"] == "/admin/audits"
    flask_client.get("/logout")


def test_open_redirect_vulnerability_prevented(flask_client, db_session):
    create_test_user(db_session, email="open_redirect@medicare.ai", role=RoleEnum.ADMIN)

    # Attempt malicious redirect targets
    for malicious_url in ["https://malicious-site.com", "//evil.com", "javascript:alert(1)"]:
        res = flask_client.post("/login", data={
            "email": "open_redirect@medicare.ai",
            "password": "Password123!",
            "next": malicious_url
        }, follow_redirects=False)

        assert res.status_code == 302
        # Must NOT redirect to external malicious URL; should fall back to admin dashboard
        assert malicious_url not in res.headers["Location"]
        assert "/admin/" in res.headers["Location"]

    flask_client.get("/logout")


# =====================================================================
# 5. Role-Based Access Control (RBAC) & 403 Forbidden
# =====================================================================

def test_role_based_access_violations(flask_client, db_session):
    # Create users
    patient = create_test_user(db_session, email="rbac_pat@medicare.ai", role=RoleEnum.PATIENT)
    doctor = create_test_user(db_session, email="rbac_doc@medicare.ai", role=RoleEnum.DOCTOR)
    nurse = create_test_user(db_session, email="rbac_nurse@medicare.ai", role=RoleEnum.NURSE)

    # 1. Patient attempts to access Admin portal -> 403 Forbidden
    flask_client.post("/login", data={"email": "rbac_pat@medicare.ai", "password": "Password123!"})
    res_pat_admin = flask_client.get("/admin/")
    assert res_pat_admin.status_code == 403
    assert b"403" in res_pat_admin.data
    assert b"Restricted Access Module" in res_pat_admin.data

    # Patient attempts to access Doctor portal -> 403 Forbidden
    res_pat_doc = flask_client.get("/doctor/")
    assert res_pat_doc.status_code == 403

    flask_client.get("/logout")

    # 2. Doctor attempts to access Admin portal -> 403 Forbidden
    flask_client.post("/login", data={"email": "rbac_doc@medicare.ai", "password": "Password123!"})
    res_doc_admin = flask_client.get("/admin/")
    assert res_doc_admin.status_code == 403

    # Doctor attempts to access Patient portal -> 403 Forbidden
    res_doc_pat = flask_client.get("/patient/")
    assert res_doc_pat.status_code == 403

    flask_client.get("/logout")

    # 3. Nurse attempts to access Pharmacy portal -> 403 Forbidden
    flask_client.post("/login", data={"email": "rbac_nurse@medicare.ai", "password": "Password123!"})
    res_nurse_pharm = flask_client.get("/pharmacy/")
    assert res_nurse_pharm.status_code == 403

    # Verify UNAUTHORIZED_ACCESS_ATTEMPT logged in AuditLog
    audit = db_session.query(AuditLog).filter(
        AuditLog.action == "UNAUTHORIZED_ACCESS_ATTEMPT"
    ).order_by(AuditLog.timestamp.desc()).first()
    assert audit is not None
    assert "/pharmacy/" in audit.details_json
    assert "nurse" in audit.details_json

    flask_client.get("/logout")


def test_authorized_role_access(flask_client, db_session):
    admin = create_test_user(db_session, email="authorized_admin@medicare.ai", role=RoleEnum.ADMIN)

    # Admin has access to admin portal
    flask_client.post("/login", data={"email": "authorized_admin@medicare.ai", "password": "Password123!"})
    res = flask_client.get("/admin/")
    assert res.status_code == 200
    assert b"System Overview" in res.data or b"Dashboard" in res.data

    # Admin also has multi-role authorization to nurse, pharmacy, receptionist, laboratory
    assert flask_client.get("/nurse/").status_code == 200
    assert flask_client.get("/pharmacy/").status_code == 200
    assert flask_client.get("/laboratory/").status_code == 200
    assert flask_client.get("/receptionist/").status_code == 200

    flask_client.get("/logout")


# =====================================================================
# 6. Logout Workflow
# =====================================================================

def test_logout_clears_session_and_audits(flask_client, db_session):
    create_test_user(db_session, email="logout_test@medicare.ai", role=RoleEnum.DOCTOR)

    # Login
    flask_client.post("/login", data={"email": "logout_test@medicare.ai", "password": "Password123!"})
    with flask_client.session_transaction() as sess:
        assert "user_id" in sess

    # Logout
    res = flask_client.get("/logout", follow_redirects=False)
    assert res.status_code == 302
    assert "/login" in res.headers["Location"]

    # Verify session cleared
    with flask_client.session_transaction() as sess:
        assert "user_id" not in sess
        assert "user_role" not in sess

    # Verify audit log entry
    audit = db_session.query(AuditLog).filter(
        AuditLog.action == "USER_LOGOUT"
    ).order_by(AuditLog.timestamp.desc()).first()
    assert audit is not None

    # Subsequent protected route access redirected to login
    protected_res = flask_client.get("/doctor/")
    assert protected_res.status_code == 302
    assert "/login" in protected_res.headers["Location"]


# =====================================================================
# 7. Patient Self-Registration Workflow
# =====================================================================

def test_patient_self_registration_and_login(flask_client, db_session):
    reg_data = {
        "first_name": "Aarav",
        "last_name": "Patel",
        "email": "aarav.patel@example.com",
        "password": "SecurePassword123!",
        "confirm_password": "SecurePassword123!",
        "phone": "+91 98765 43210",
        "dob": "1994-06-15",
        "gender": "male",
        "blood_group": "O+",
        "emergency_contact_name": "Priya Patel",
        "emergency_contact_phone": "+91 98765 43211",
        "address": "45 MG Road, Mumbai",
        "allergies": "Penicillin",
        "chronic_conditions": "None"
    }

    # Submit registration
    res = flask_client.post("/register", data=reg_data, follow_redirects=False)
    assert res.status_code == 302
    assert "/login" in res.headers["Location"]

    # Verify User created in database with hashed password
    new_user = db_session.query(User).filter(User.email == "aarav.patel@example.com").first()
    assert new_user is not None
    assert new_user.first_name == "Aarav"
    assert new_user.last_name == "Patel"
    assert new_user.role == RoleEnum.PATIENT
    assert new_user.check_password("SecurePassword123!") is True
    assert new_user.check_password("WrongPassword") is False

    # Verify Patient profile created
    patient_profile = db_session.query(Patient).filter(Patient.user_id == new_user.id).first()
    assert patient_profile is not None
    assert patient_profile.blood_group == "O+"
    assert patient_profile.allergies == "Penicillin"

    # Verify PATIENT_REGISTRATION AuditLog entry
    audit = db_session.query(AuditLog).filter(
        AuditLog.action == "PATIENT_REGISTRATION",
        AuditLog.user_id == new_user.id
    ).first()
    assert audit is not None

    # Verify the registered patient can now log in
    login_res = flask_client.post("/login", data={
        "email": "aarav.patel@example.com",
        "password": "SecurePassword123!"
    }, follow_redirects=False)
    assert login_res.status_code == 302
    assert "/patient/" in login_res.headers["Location"]

    flask_client.get("/logout")


def test_patient_registration_password_mismatch(flask_client, db_session):
    res = flask_client.post("/register", data={
        "first_name": "Test",
        "last_name": "Mismatch",
        "email": "mismatch@example.com",
        "password": "Password123!",
        "confirm_password": "DifferentPassword123!",
        "phone": "+91 91234 56789",
        "dob": "1990-01-01",
        "gender": "female"
    })

    assert res.status_code == 400
    assert b"Passwords do not match" in res.data

    user = db_session.query(User).filter(User.email == "mismatch@example.com").first()
    assert user is None


def test_patient_registration_duplicate_email(flask_client, db_session):
    create_test_user(db_session, email="duplicate@example.com", role=RoleEnum.PATIENT)

    res = flask_client.post("/register", data={
        "first_name": "Duplicate",
        "last_name": "User",
        "email": "duplicate@example.com",
        "password": "Password123!",
        "confirm_password": "Password123!",
        "phone": "+91 91234 56789",
        "dob": "1990-01-01",
        "gender": "female"
    })

    assert res.status_code == 400
    assert b"already registered" in res.data


# =====================================================================
# 8. Reusable Decorator Helper Functions
# =====================================================================

def test_decorator_helper_functions(flask_client, db_session):
    assert normalize_role(RoleEnum.ADMIN) == "admin"
    assert normalize_role(RoleEnum.LAB_TECH) == "lab_tech"
    assert normalize_role("LAB_TECHNICIAN") == "lab_tech"
    assert normalize_role("doctor") == "doctor"

    user = create_test_user(db_session, email="helper_doc@medicare.ai", role=RoleEnum.DOCTOR)

    # In test context with no session
    with flask_client.application.test_request_context():
        assert is_authenticated() is False
        assert get_current_role() == ""
        assert has_role("doctor") is False
        assert get_current_user() is None

        # Simulate authenticated session
        session["user_id"] = user.id
        session["user_role"] = user.role.value
        assert is_authenticated() is True
        assert get_current_role() == "doctor"
        assert has_role("doctor") is True
        assert has_role(RoleEnum.DOCTOR) is True
        assert has_role("admin") is False
        curr_user = get_current_user()
        assert curr_user is not None
        assert curr_user.email == "helper_doc@medicare.ai"
