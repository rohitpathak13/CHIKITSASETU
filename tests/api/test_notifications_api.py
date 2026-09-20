"""
API Integration Tests for FastAPI In-App Notifications Endpoints:
- GET  /api/v1/notifications
- GET  /api/v1/notifications/unread-count
- POST /api/v1/notifications/{id}/read
- POST /api/v1/notifications/read-all
- POST /api/v1/notifications
- POST /api/v1/notifications/scan
- GET  /api/v1/notifications/{id}

Verifies OAuth2 authentication, role-based visibility isolation, pagination,
status transitions, and operational scanner execution.
"""

import pytest
from core.models import User, RoleEnum, Notification, NotificationTypeEnum, NotificationPriorityEnum
from core.security import get_password_hash, create_access_token
from core.services.notification_service import NotificationService


@pytest.fixture
def auth_users(db_session):
    """Creates a set of distinct authenticated users and their JWT auth headers."""
    # 1. Admin
    admin = User(
        email="api_admin@chikitsasetu.ai",
        password_hash=get_password_hash("AdminPass123!"),
        role=RoleEnum.ADMIN,
        first_name="Arthur",
        last_name="Director",
        is_active=True
    )
    # 2. Pharmacist
    pharm = User(
        email="api_pharm@chikitsasetu.ai",
        password_hash=get_password_hash("PharmPass123!"),
        role=RoleEnum.PHARMACIST,
        first_name="Geeta",
        last_name="Pharmacist",
        is_active=True
    )
    # 3. Patient
    pat = User(
        email="api_pat@chikitsasetu.ai",
        password_hash=get_password_hash("PatientPass123!"),
        role=RoleEnum.PATIENT,
        first_name="Vikram",
        last_name="Patient",
        is_active=True
    )

    db_session.add_all([admin, pharm, pat])
    db_session.commit()
    for u in [admin, pharm, pat]:
        db_session.refresh(u)

    def make_headers(user):
        token = create_access_token({"sub": str(user.id), "role": user.role.value, "email": user.email})
        return {"Authorization": f"Bearer {token}"}

    return {
        "admin": (admin, make_headers(admin)),
        "pharmacist": (pharm, make_headers(pharm)),
        "patient": (pat, make_headers(pat))
    }


def test_list_notifications_authenticated(fastapi_client, db_session, auth_users):
    """Verifies listing notifications for authenticated user."""
    admin_user, admin_headers = auth_users["admin"]

    # Seed notification
    NotificationService.create_notification(
        db=db_session,
        user_id=admin_user.id,
        title="Admin Alert",
        message="System backup completed successfully.",
        type=NotificationTypeEnum.SYSTEM,
        priority=NotificationPriorityEnum.NORMAL
    )

    res = fastapi_client.get("/api/v1/notifications", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()

    assert "items" in data
    assert "total" in data
    assert "unread_count" in data
    assert data["total"] >= 1
    assert any(n["title"] == "Admin Alert" for n in data["items"])


def test_unread_count_endpoint(fastapi_client, db_session, auth_users):
    """Verifies retrieval of unread count badge counter."""
    admin_user, admin_headers = auth_users["admin"]

    NotificationService.create_notification(
        db=db_session,
        user_id=admin_user.id,
        title="Pending Action",
        message="Review monthly report.",
        type=NotificationTypeEnum.SYSTEM
    )

    res = fastapi_client.get("/api/v1/notifications/unread-count", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert "unread_count" in data
    assert data["unread_count"] >= 1


def test_mark_single_notification_read(fastapi_client, db_session, auth_users):
    """Verifies marking an individual notification as read."""
    admin_user, admin_headers = auth_users["admin"]

    notif = NotificationService.create_notification(
        db=db_session,
        user_id=admin_user.id,
        title="Mark Me Read",
        message="Click read button.",
        type=NotificationTypeEnum.SYSTEM
    )

    res = fastapi_client.post(f"/api/v1/notifications/{notif.id}/read", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["notification_id"] == notif.id

    # Verify notification details reflect is_read = True
    detail_res = fastapi_client.get(f"/api/v1/notifications/{notif.id}", headers=admin_headers)
    assert detail_res.status_code == 200
    assert detail_res.json()["is_read"] is True


def test_mark_all_notifications_read(fastapi_client, db_session, auth_users):
    """Verifies bulk marking all visible unread notifications as read."""
    admin_user, admin_headers = auth_users["admin"]

    NotificationService.create_notification(db=db_session, user_id=admin_user.id, title="Unread A", message="A")
    NotificationService.create_notification(db=db_session, user_id=admin_user.id, title="Unread B", message="B")

    res = fastapi_client.post("/api/v1/notifications/read-all", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["marked_count"] >= 2

    # Verify unread count is 0
    count_res = fastapi_client.get("/api/v1/notifications/unread-count", headers=admin_headers)
    assert count_res.json()["unread_count"] == 0


def test_role_based_visibility_api_isolation(fastapi_client, db_session, auth_users):
    """Verifies that endpoints enforce role boundaries across callers."""
    _, pharm_headers = auth_users["pharmacist"]
    pat_user, pat_headers = auth_users["patient"]

    # 1. Pharmacist role broadcast
    NotificationService.create_notification(
        db=db_session,
        target_role=RoleEnum.PHARMACIST,
        title="Stock Depletion: Paracetamol",
        message="Current inventory is below safety buffer.",
        type=NotificationTypeEnum.LOW_STOCK,
        priority=NotificationPriorityEnum.HIGH
    )

    # 2. Patient personal notification
    NotificationService.create_notification(
        db=db_session,
        user_id=pat_user.id,
        title="Your Lab Report is Ready",
        message="Fasting blood glucose result ready.",
        type=NotificationTypeEnum.LAB_RESULT
    )

    # Pharmacist caller should see stock alert, NOT patient lab result
    pharm_res = fastapi_client.get("/api/v1/notifications", headers=pharm_headers)
    assert pharm_res.status_code == 200
    pharm_items = pharm_res.json()["items"]
    assert any(n["title"] == "Stock Depletion: Paracetamol" for n in pharm_items)
    assert not any(n["title"] == "Your Lab Report is Ready" for n in pharm_items)

    # Patient caller should see personal lab result, NOT pharmacist stock alert
    pat_res = fastapi_client.get("/api/v1/notifications", headers=pat_headers)
    assert pat_res.status_code == 200
    pat_items = pat_res.json()["items"]
    assert any(n["title"] == "Your Lab Report is Ready" for n in pat_items)
    assert not any(n["title"] == "Stock Depletion: Paracetamol" for n in pat_items)


def test_create_notification_role_permissions(fastapi_client, auth_users):
    """Verifies that only authorized roles can dispatch custom notifications."""
    _, admin_headers = auth_users["admin"]
    _, pat_headers = auth_users["patient"]

    payload = {
        "title": "Clinical Audit Notice",
        "message": "Quarterly prescription audit scheduled.",
        "type": "system",
        "priority": "normal",
        "target_role": "doctor"
    }

    # Admin dispatch: allowed (201)
    admin_res = fastapi_client.post("/api/v1/notifications", json=payload, headers=admin_headers)
    assert admin_res.status_code == 201
    assert admin_res.json()["title"] == "Clinical Audit Notice"

    # Patient dispatch: prohibited (403)
    pat_res = fastapi_client.post("/api/v1/notifications", json=payload, headers=pat_headers)
    assert pat_res.status_code == 403


def test_trigger_operational_scan_api(fastapi_client, auth_users):
    """Verifies triggering automated operations event scanner."""
    _, admin_headers = auth_users["admin"]

    res = fastapi_client.post("/api/v1/notifications/scan", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "events_detected" in data
    assert "low_stock_generated" in data["events_detected"]
