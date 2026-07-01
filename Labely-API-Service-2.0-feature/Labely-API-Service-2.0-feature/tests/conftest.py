"""
Shared pytest fixtures for the Labely test suite.

All fixtures use an in-memory SQLite database so no real MySQL / Redis
instance is required to run the tests.
"""
import os
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

# ── env vars must be set BEFORE any app module is imported ───────────────────
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-at-least-32-chars-long!!")
os.environ.setdefault("BASE_URL", "http://localhost:8000")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("DB_MODE", "tcp")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_NAME", "test_db")
os.environ.setdefault("MIRAKL_BASE_URL", "https://mirakl.example.com")
os.environ.setdefault("MIRAKL_API_KEY", "test-api-key")
os.environ.setdefault("MIRAKL_SHOP_ID", "123")
os.environ.setdefault("SRP_ENDPOINT_URI", "https://srp.example.com")
os.environ.setdefault("SRP_USERNAME", "test-user")
os.environ.setdefault("SRP_CLIENT_ID", "test-client")
os.environ.setdefault("SRP_PASSWORD", "test-password")
os.environ.setdefault("OUTPUT_FOLDER", "/tmp/labely_test_output")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.models.base import Base
from app.models.user import User, PasswordResetToken
from app.models.order import OrderProcess, Order
from app.models.tracking import TrackingUpdate
from app.core.security import hash_password, create_access_token


# ── in-memory SQLite engine ───────────────────────────────────────────────────
TEST_DB_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def create_tables():
    """Create all tables once for the test session."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
    """Provide a transactional database session that rolls back after each test."""
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def test_user(db):
    """Return a persisted test user."""
    user = User(
        email="test@example.com",
        username="testuser",
        password=hash_password("password123"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def auth_token(test_user):
    """Return a valid JWT access token for the test user."""
    return create_access_token({"sub": str(test_user.id)})


@pytest.fixture()
def auth_headers(auth_token):
    """Return Authorization header dict for the test user."""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture()
def test_order_process(db, test_user):
    """Return a persisted OrderProcess fixture."""
    process = OrderProcess(
        user_id=test_user.id,
        srp="SRP",
        quantity=5,
        status="Pending",
        total_orders=5,
        successful_count=0,
        failed_count=0,
        request_method="quantity",
    )
    db.add(process)
    db.commit()
    db.refresh(process)
    return process


@pytest.fixture()
def test_tracking_update(db, test_user, test_order_process):
    """Return a persisted TrackingUpdate fixture."""
    tracking = TrackingUpdate(
        user_id=test_user.id,
        process_id=test_order_process.id,
        order_id="ORDER-001",
        tracking_number="TRACK123456",
        carrier="Colissimo",
        label_generated=True,
        tracking_updated=False,
        shipment_confirmed=False,
    )
    db.add(tracking)
    db.commit()
    db.refresh(tracking)
    return tracking


# ── FastAPI TestClient ────────────────────────────────────────────────────────

@pytest.fixture()
def client(db):
    """
    FastAPI TestClient with DB and Redis mocked out.

    Overrides:
      - get_db  → in-memory SQLite session
      - redis_client.is_initialized → False  (no Redis needed)
    """
    from app.main import app
    from app.api import deps
    from app.core import redis_client as rc_module

    # Patch Redis so lifespan never tries a real connection.
    # is_initialized is a @property, so we must patch it on the class.
    with patch.object(
            type(rc_module.redis_client), "is_initialized",
            new_callable=lambda: property(lambda self: False)
         ), \
         patch("app.main.init_redis", new_callable=AsyncMock, return_value=False), \
         patch("app.main.init_database", return_value=None), \
         patch("app.services.file_service.file_service.cleanup_old_files", return_value=None):

        def override_get_db():
            try:
                yield db
            finally:
                pass

        app.dependency_overrides[deps.get_db] = override_get_db
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
        app.dependency_overrides.clear()


@pytest.fixture()
def authed_client(client, test_user, auth_token, db):
    """TestClient pre-configured with a valid auth token."""
    from app.api import deps

    async def override_current_user():
        return test_user

    from app.main import app
    app.dependency_overrides[deps.get_current_user] = override_current_user
    yield client
    app.dependency_overrides.pop(deps.get_current_user, None)
