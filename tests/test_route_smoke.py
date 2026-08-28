"""
Smoke tests: every parameter-free page renders.

base.html is shared by every page in the app, so a mistake there breaks
everything at once. These tests make that immediate and obvious.

Auth note: AuthMiddleware only checks that the session cookie decodes -
it does not verify the user exists - so a signed cookie is sufficient.
"""

import pytest
from fastapi.testclient import TestClient

from web.app import app
from web.auth import create_session_cookie, COOKIE_NAME

PAGES = [
    "/",
    "/generate",
    "/browse",
    "/workshop",
    "/workshop/browse",
    "/currents",
    "/currents/browse",
    "/resonance",
    "/profiles",
]


@pytest.fixture
def client():
    c = TestClient(app)
    c.cookies.set(COOKIE_NAME, create_session_cookie(1))
    return c


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
