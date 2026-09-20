import pytest
from core.models import User, Notification, RoleEnum, NotificationTypeEnum
from core.security import get_password_hash

def test_notification_workflow(flask_client, db_session):
    """
    Tests the notification center:
    - Verifies fetching notifications for active user
    - Verifies marking single notification as read
    - Verifies bulk mark-all-read endpoint
    """
    # 1. Create test user
    user = User(
        email="notify_user@medicare.ai",
        password_hash=get_password_hash("Password123!"),
        role=RoleEnum.DOCTOR,
        first_name="Helen",
        last_name="Keller",
        is_active=True
    )
    db_session.add(user)
    db_session.commit()

    # 2. Add sample notifications
    n1 = Notification(
        user_id=user.id,
        title="Critical Lab Result",
        message="Potassium level 6.2 mEq/L (Critical high)",
        type=NotificationTypeEnum.CRITICAL,
        is_read=False
    )
    n2 = Notification(
        user_id=user.id,
        title="Appointment Cancelled",
        message="Patient John cancelled for 14:00",
        type=NotificationTypeEnum.ALERT,
        is_read=False
    )
    db_session.add_all([n1, n2])
    db_session.commit()

    # 3. Authenticate Flask session
    with flask_client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["user_email"] = user.email
        sess["user_role"] = user.role.value
        sess["user_name"] = user.full_name

    # 4. View notifications page
    resp = flask_client.get("/notifications/")
    assert resp.status_code == 200
    assert b"Critical Lab Result" in resp.data
    assert b"Appointment Cancelled" in resp.data

    # 5. Mark single notification as read
    resp_mark = flask_client.post(f"/notifications/mark-read/{n1.id}", headers={"X-Requested-With": "XMLHttpRequest"})
    assert resp_mark.status_code == 200
    n1_upd = db_session.query(Notification).filter(Notification.id == n1.id).first()
    n2_upd = db_session.query(Notification).filter(Notification.id == n2.id).first()
    assert n1_upd.is_read is True
    assert n2_upd.is_read is False

    # 6. Mark all as read
    resp_all = flask_client.post("/notifications/mark-all-read", headers={"X-Requested-With": "XMLHttpRequest"})
    assert resp_all.status_code == 200
    db_session.expire_all()
    n2_final = db_session.query(Notification).filter(Notification.id == n2.id).first()
    assert n2_final.is_read is True
