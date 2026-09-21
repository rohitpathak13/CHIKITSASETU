import pytest
from backend.models import User, RoleEnum
from backend.security import get_password_hash

def test_flask_login_page_renders(flask_client):
    res = flask_client.get("/login")
    assert res.status_code == 200
    assert b"Sign In - CHIKITSASETU" in res.data
    assert b"1-Click Role Quick Fill" in res.data

def test_flask_unauthorized_access_redirects(flask_client):
    res = flask_client.get("/admin/")
    assert res.status_code == 302
    assert "/login" in res.headers["Location"]

def test_flask_admin_login_and_access(flask_client, db_session):
    admin = db_session.query(User).filter(User.email == "admin@chikitsasetu.ai").first()
    if not admin:
        admin = User(
            email="admin@chikitsasetu.ai",
            password_hash=get_password_hash("Password123!"),
            role=RoleEnum.ADMIN,
            first_name="Admin",
            last_name="Superuser",
            is_active=True
        )
        db_session.add(admin)
        db_session.commit()

    login_res = flask_client.post("/login", data={
        "email": "admin@chikitsasetu.ai",
        "password": "Password123!"
    }, follow_redirects=True)

    assert login_res.status_code == 200
    assert b"System Overview" in login_res.data
