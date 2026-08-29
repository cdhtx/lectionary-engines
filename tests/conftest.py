"""
Pytest configuration for web tests
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from web.app import app
from web.auth import create_session_cookie, COOKIE_NAME
from web.database import init_db, close_db, get_db
from web.models import Base


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Initialize the test database before any tests run."""
    init_db()
    yield
    close_db()


@pytest.fixture
def isolated_client():
    """
    An authenticated TestClient backed by an in-memory SQLite DB via a
    get_db override, instead of the real local lectionary.db.

    Any test that writes through a route (e.g. hits / and caches the
    mocked Sunday readings via LectionaryReadingCache) needs this: the
    plain `client` fixture in test_route_smoke.py uses the real local DB
    file with no cleanup, which would leak fake rows into it.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    c = TestClient(app)
    c.cookies.set(COOKIE_NAME, create_session_cookie(1))
    yield c

    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def study_client():
    """
    Like isolated_client, but also yields the session factory so tests
    can seed rows into (or read rows back out of) the same in-memory DB
    around the request under test.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    c = TestClient(app)
    c.cookies.set(COOKIE_NAME, create_session_cookie(1))
    yield c, SessionLocal

    app.dependency_overrides.pop(get_db, None)
