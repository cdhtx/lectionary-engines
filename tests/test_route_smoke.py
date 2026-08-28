"""
Smoke tests: every parameter-free page renders.

base.html is shared by every page in the app, so a mistake there breaks
everything at once. These tests make that immediate and obvious.

Auth note: AuthMiddleware only checks that the session cookie decodes -
it does not verify the user exists - so a signed cookie is sufficient.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from web.app import app
from web.auth import create_session_cookie, COOKIE_NAME
from web.database import get_db
from web.models import Base

PAGES = [
    "/generate",
    "/browse",
    "/workshop",
    "/workshop/browse",
    "/currents",
    "/currents/browse",
    "/resonance",
    "/profiles",
    "/engines",
]


@pytest.fixture
def client():
    c = TestClient(app)
    c.cookies.set(COOKIE_NAME, create_session_cookie(1))
    return c


@pytest.fixture
def isolated_client():
    """
    Like `client`, but backed by an in-memory SQLite DB via a get_db
    override instead of the real local lectionary.db.

    Every test that hits / needs this: that route has a write side effect
    - it caches the mocked Sunday readings via LectionaryReadingCache.
    Using the shared `client` fixture would leak those fake rows into the
    real local DB file with no cleanup. This fixture isolates that write
    and clears the override on teardown so it can't leak into other tests
    running in the same session.
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


@pytest.mark.parametrize("path", PAGES)
def test_page_renders(client, path):
    response = client.get(path)
    assert response.status_code == 200, f"{path} returned {response.status_code}"
    assert "<html" in response.text.lower(), f"{path} did not return an HTML document"


def test_login_page_renders_without_auth():
    # login is a public path and must render for a signed-out visitor.
    response = TestClient(app).get("/login")
    assert response.status_code == 200


def test_health_endpoint():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_missing_study_renders_404_not_500(client):
    response = client.get("/study/99999999")
    assert response.status_code == 404, (
        f"Expected 404, got {response.status_code}. A 500 here means the "
        "404.html template is missing."
    )


def test_missing_currents_renders_404_not_500(client):
    response = client.get("/currents/99999999")
    assert response.status_code == 404


def test_missing_workshop_prep_renders_404_not_500(client):
    response = client.get("/workshop/99999999")
    assert response.status_code == 404


def test_engines_page_lists_all_three_engines(client):
    response = client.get("/engines")
    assert response.status_code == 200
    body = response.text
    assert "Threshold" in body
    assert "Palimpsest" in body
    assert "Collision" in body


def test_library_page_shows_all_content_types(client):
    response = client.get("/browse")
    assert response.status_code == 200


def test_library_page_type_filter(client):
    response = client.get("/browse?type=workshop")
    assert response.status_code == 200


@patch("web.services.lectionary_widget_service.TextFetcher")
def test_sidebar_links_to_engines(mock_fetcher_class, isolated_client):
    mock_fetcher = mock_fetcher_class.return_value
    mock_fetcher.fetch_sunday_lectionary_readings.return_value = {
        "gospel": "Luke 14:1-14",
        "epistle": "Hebrews 13:1-8, 15-16",
        "ot": "Jeremiah 2:4-13",
        "psalm": "Psalm 81:1, 10-16",
    }

    response = isolated_client.get("/")
    assert response.status_code == 200
    assert 'href="/engines"' in response.text


@patch("web.services.lectionary_widget_service.TextFetcher")
def test_today_homepage_shows_this_week_readings(mock_fetcher_class, isolated_client):
    mock_fetcher = mock_fetcher_class.return_value
    mock_fetcher.fetch_sunday_lectionary_readings.return_value = {
        "gospel": "Luke 14:1-14",
        "epistle": "Hebrews 13:1-8, 15-16",
        "ot": "Jeremiah 2:4-13",
        "psalm": "Psalm 81:1, 10-16",
    }

    response = isolated_client.get("/")

    assert response.status_code == 200
    body = response.text
    assert "Gospel" in body
    assert "Epistle" in body
    assert "Hebrew Scripture" in body
    assert "Psalm" in body


@patch("web.services.lectionary_widget_service.TextFetcher")
def test_home_page_renders(mock_fetcher_class, isolated_client):
    mock_fetcher = mock_fetcher_class.return_value
    mock_fetcher.fetch_sunday_lectionary_readings.return_value = {}

    response = isolated_client.get("/")

    assert response.status_code == 200
    assert "<html" in response.text.lower()


def test_workbench_reflow_orders_sections_correctly(client):
    response = client.get("/generate")
    assert response.status_code == 200
    body = response.text
    exploring_idx = body.find("What are you exploring?")
    engine_idx = body.find("Choose an Engine")
    profile_idx = body.find("Select Your Profile")
    news_idx = body.find("News Integration")
    assert exploring_idx != -1, "Missing 'What are you exploring?' heading"
    assert engine_idx != -1, "Missing 'Choose an Engine' heading"
    assert profile_idx != -1, "Missing 'Select Your Profile' heading"
    assert news_idx != -1, "Missing 'News Integration' heading"
    assert exploring_idx < engine_idx < profile_idx < news_idx, (
        "Sections are not in the expected Workbench order: "
        "What are you exploring? -> Choose an Engine -> Select Your Profile -> News Integration"
    )


@patch("web.services.lectionary_widget_service.TextFetcher")
@patch("web.services.signals_service.TextFetcher")
@patch("web.services.signals_service.extract_themes")
def test_signals_page_renders(mock_extract_themes, mock_signals_fetcher_class, mock_readings_fetcher_class, isolated_client):
    mock_readings_fetcher_class.return_value.fetch_sunday_lectionary_readings.return_value = {
        "gospel": "Luke 14:1-14",
        "epistle": "Hebrews 13:1-8, 15-16",
        "ot": "Jeremiah 2:4-13",
        "psalm": "Psalm 81:1, 10-16",
    }
    mock_signals_fetcher_class.return_value.fetch.return_value = "full passage text"
    mock_extract_themes.side_effect = lambda claude, reference, text: ["hospitality"]

    response = isolated_client.get("/signals")

    assert response.status_code == 200
    assert "Signals" in response.text


def test_sidebar_links_to_signals(isolated_client):
    response = isolated_client.get("/engines")
    assert response.status_code == 200
    assert 'href="/signals"' in response.text
