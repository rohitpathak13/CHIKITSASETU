import pytest
import os
from datetime import date
from decimal import Decimal
from fastapi.testclient import TestClient

# Configure environment for tests
os.environ["TESTING"] = "1"
os.environ["USE_SQLITE"] = "true"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from core.database import Base
from core.models import User, RoleEnum
from core.security import get_password_hash, create_access_token

# Dedicated isolated in-memory database for testing
test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=test_engine)

import core.database
core.database.engine = test_engine
core.database.SessionLocal.configure(bind=test_engine, expire_on_commit=False)
core.database.db_session.configure(bind=test_engine, expire_on_commit=False)

@pytest.fixture(scope="session", autouse=True)
def setup_db():
    """Initializes all tables in the in-memory database."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)

from api.main import app as fastapi_app
from web import create_app as create_flask_app
from core.database import get_db

@pytest.fixture(scope="function")
def db_session():
    """Provides a fresh isolated database session per test function."""
    session = core.database.db_session()
    yield session
    session.rollback()
    core.database.db_session.remove()
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()

@pytest.fixture(scope="module")
def flask_client():
    """Flask web application test client."""
    app = create_flask_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as client:
        yield client

@pytest.fixture(scope="module")
def fastapi_client():
    """FastAPI test client with test db dependency override."""
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()
    fastapi_app.dependency_overrides[get_db] = override_get_db
    with TestClient(fastapi_app) as client:
        yield client

@pytest.fixture(scope="function")
def admin_user(db_session):
    """Fixture ensuring an admin user exists and returns the user object."""
    admin = db_session.query(User).filter(User.email == "test_admin@medicare.ai").first()
    if not admin:
        admin = User(
            email="test_admin@medicare.ai",
            password_hash=get_password_hash("Password123!"),
            role=RoleEnum.ADMIN,
            first_name="Test",
            last_name="Admin",
            is_active=True
        )
        db_session.add(admin)
        db_session.commit()
    return admin

@pytest.fixture(scope="function")
def admin_auth_headers(admin_user):
    """Returns valid JWT Bearer authentication headers for the admin user."""
    token = create_access_token({"sub": str(admin_user.id), "role": admin_user.role.value, "email": admin_user.email})
    return {"Authorization": f"Bearer {token}"}
