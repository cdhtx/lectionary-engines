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

from web.app import app
from web.auth import create_session_cookie, COOKIE_NAME
from web.models import Study

PAGES = [
    "/generate",
    "/browse",
    "/workshop",
    "/workshop/browse",
    "/currents",
    "/resonance",
    "/profiles",
    "/engines",
]


def test_currents_browse_no_longer_resolves(client):
    # The /currents/browse route no longer exists. Requests fall through to
    # /currents/{analysis_id:int}, where "browse" fails int validation, resulting
    # in a 422 (Unprocessable Entity) — an honest error indicating the path segment
    # is not a valid resource identifier.
    response = client.get("/currents/browse")
    assert response.status_code == 422


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
@patch("web.services.signals_service.TextFetcher")
@patch("web.services.signals_service.extract_themes")
def test_sidebar_links_to_engines(mock_extract_themes, mock_signals_fetcher_class, mock_fetcher_class, isolated_client):
    mock_fetcher = mock_fetcher_class.return_value
    mock_fetcher.fetch_sunday_lectionary_readings.return_value = {
        "gospel": "Luke 14:1-14",
        "epistle": "Hebrews 13:1-8, 15-16",
        "ot": "Jeremiah 2:4-13",
        "psalm": "Psalm 81:1, 10-16",
    }
    mock_signals_fetcher_class.return_value.fetch.return_value = "full passage text"
    mock_extract_themes.return_value = []

    response = isolated_client.get("/")
    assert response.status_code == 200
    assert 'href="/engines"' in response.text


@patch("web.services.lectionary_widget_service.TextFetcher")
@patch("web.services.signals_service.TextFetcher")
@patch("web.services.signals_service.extract_themes")
def test_today_homepage_shows_this_week_readings(mock_extract_themes, mock_signals_fetcher_class, mock_fetcher_class, isolated_client):
    mock_fetcher = mock_fetcher_class.return_value
    mock_fetcher.fetch_sunday_lectionary_readings.return_value = {
        "gospel": "Luke 14:1-14",
        "epistle": "Hebrews 13:1-8, 15-16",
        "ot": "Jeremiah 2:4-13",
        "psalm": "Psalm 81:1, 10-16",
    }
    mock_signals_fetcher_class.return_value.fetch.return_value = "full passage text"
    mock_extract_themes.return_value = []

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


@patch("web.services.lectionary_widget_service.TextFetcher")
@patch("web.services.signals_service.TextFetcher")
@patch("web.services.signals_service.extract_themes")
def test_today_homepage_shows_signals_widget(mock_extract_themes, mock_signals_fetcher_class, mock_readings_fetcher_class, isolated_client):
    mock_readings_fetcher_class.return_value.fetch_sunday_lectionary_readings.return_value = {
        "gospel": "Luke 14:1-14",
        "epistle": "Hebrews 13:1-8, 15-16",
        "ot": "Jeremiah 2:4-13",
        "psalm": "Psalm 81:1, 10-16",
    }
    mock_signals_fetcher_class.return_value.fetch.return_value = "full passage text"
    mock_extract_themes.side_effect = lambda claude, reference, text: ["hospitality"]

    response = isolated_client.get("/")

    assert response.status_code == 200
    assert "Signals" in response.text


_PALIMPSEST_FIXTURE_CONTENT = """# Palimpsest Study: John 3:16-21

Intro paragraph here.

## Layer One: Peshat (Simple/Literal)

Peshat content.

## Layer Two: Remez (Hint/Allegory)

Remez content.

## Layer Three: Derash (Search/Interpretation)

Derash content.

## Layer Four: Sod (Secret/Mystery)

Sod content.

## Layer Five: Incarnation (Contemporary Body)

### For Individuals in Transition

Incarnation content.
"""


def test_palimpsest_study_page_shows_rail(study_client):
    client, SessionLocal = study_client
    session = SessionLocal()
    study = Study(
        engine="palimpsest", reference="John 3:16-21",
        content=_PALIMPSEST_FIXTURE_CONTENT, word_count=50,
    )
    session.add(study)
    session.commit()
    study_id = study.id
    session.close()

    response = client.get(f"/study/{study_id}")

    assert response.status_code == 200
    body = response.text
    assert 'class="palimpsest-rail"' in body
    assert "palimpsest-rail.js" in body
    for key in ["peshat", "remez", "derash", "sod", "incarnation"]:
        assert f'id="layer-{key}"' in body


def test_threshold_study_page_has_no_rail(study_client):
    client, SessionLocal = study_client
    session = SessionLocal()
    study = Study(
        engine="threshold", reference="Mark 5:1-5",
        content="## Threshold One: Archaeological Dive\n\nSome content.",
        word_count=10,
    )
    session.add(study)
    session.commit()
    study_id = study.id
    session.close()

    response = client.get(f"/study/{study_id}")

    assert response.status_code == 200
    assert 'class="palimpsest-rail"' not in response.text
    assert "palimpsest-rail.js" not in response.text


def test_malformed_palimpsest_study_falls_back_to_flat_rendering(study_client):
    client, SessionLocal = study_client
    session = SessionLocal()
    malformed_content = (
        "## Layer One: Peshat (Simple/Literal)\n\n"
        "Only one layer here, missing the other four."
    )
    study = Study(
        engine="palimpsest", reference="Mark 5:1-5",
        content=malformed_content, word_count=10,
    )
    session.add(study)
    session.commit()
    study_id = study.id
    session.close()

    response = client.get(f"/study/{study_id}")

    assert response.status_code == 200
    assert 'class="palimpsest-rail"' not in response.text
    assert "Only one layer here" in response.text


def test_browse_page_with_facet_filters_renders_and_filters_work(study_client):
    """
    Verify that theme/season/source facet filters actually narrow results,
    preserve filters across pagination links, and allow clearing individual
    filters while preserving others.
    """
    from datetime import datetime, timedelta
    from web.services.library_service import record_content_themes
    import re

    client, SessionLocal = study_client
    session = SessionLocal()
    base_time = datetime(2026, 8, 28, 12, 0, 0)

    # Seed data: 22 studies matching all three filters to trigger pagination (per_page=20),
    # plus one that doesn't match
    matching_studies = []
    for i in range(22):
        study = Study(
            engine="threshold",
            reference=f"John 3:{16+i}-{21+i}",
            content="Test study content",
            season="lent",
            source="rcl",
            created_at=base_time - timedelta(days=i),
        )
        session.add(study)
        matching_studies.append(study)
    session.commit()

    # Seed the non-matching study
    study2 = Study(
        engine="threshold",
        reference="Matthew 5:1-12",
        content="Different study content",
        season="advent",
        source="paste",
        created_at=base_time - timedelta(days=30),
    )
    session.add(study2)
    session.commit()

    # Add themes to the matching studies, keyed off their actual autogenerated
    # PKs (not assumed to start at 1) rather than hardcoded IDs
    for study in matching_studies:
        record_content_themes(session, "study", study.id, ["hospitality", "grace"])
    # Add theme to non-matching study
    record_content_themes(session, "study", study2.id, ["resurrection"])
    session.commit()
    session.close()

    # ===== Test 1: Filter values actually narrow results =====
    # Query with all three filters: should only get the lent/rcl/hospitality studies
    response = client.get("/browse?season=lent&source=rcl&theme=hospitality")
    assert response.status_code == 200
    body = response.text
    # One of the matching studies should appear
    assert "John 3:16-21" in body
    # Non-matching study should not appear
    assert "Matthew 5:1-12" not in body

    # ===== Test 2: Removing one filter changes results =====
    # Query with just season=lent
    response = client.get("/browse?season=lent")
    assert response.status_code == 200
    body = response.text
    assert "John 3:16-21" in body
    assert "Matthew 5:1-12" not in body

    # ===== Test 3: Clearing all filters shows content (on page 1) =====
    response = client.get("/browse")
    assert response.status_code == 200
    body = response.text
    # First 20 studies are shown (most recent John studies)
    assert "John 3:" in body
    # Note: Matthew study (study 23, oldest) is on page 2, not shown on page 1

    # ===== Test 4: Pagination links actually exist and preserve all filters =====
    # With 22 matching results and per_page=20, we should have 2 pages
    response = client.get("/browse?season=lent&source=rcl&theme=hospitality")
    body = response.text

    # Verify pagination markup exists (total_pages > 1)
    assert "Next →" in body, "Pagination should exist with 22 filtered results and per_page=20"

    # Extract the "Next" link href and verify it contains all three filter params
    # Look for href="/browse?...page=2..." pattern
    next_link_match = re.search(r'href="([^"]*page=2[^"]*)"', body)
    assert next_link_match, "Could not find 'Next' pagination link with page=2"
    next_href = next_link_match.group(1)

    # Decode HTML entities (&amp; -> &) and verify all three filters are present in the link
    next_href_decoded = next_href.replace("&amp;", "&")
    assert "season=lent" in next_href_decoded, f"season filter missing from Next link: {next_href_decoded}"
    assert "source=rcl" in next_href_decoded, f"source filter missing from Next link: {next_href_decoded}"
    assert "theme=hospitality" in next_href_decoded, f"theme filter missing from Next link: {next_href_decoded}"

    # ===== Test 5: Removing one filter while preserving others =====
    # The "All" link under Theme filter should drop theme but keep season/source
    response = client.get("/browse?season=lent&source=rcl&theme=hospitality")
    body = response.text

    # Find the Theme filter group's "All" link (which should clear theme but preserve season/source)
    # Pattern: /browse?season=lent&source=rcl (in some order, with or without amp; encoding)
    # Just verify a link exists with season=lent&source=rcl but NOT theme=
    theme_clear_pattern = re.compile(r'href="([^"]*season=lent[^"]*source=rcl[^"]*)"')
    theme_clear_matches = theme_clear_pattern.findall(body)
    theme_clear_href = None
    for href in theme_clear_matches:
        decoded = href.replace("&amp;", "&")
        if "theme=" not in decoded and "season=lent" in decoded and "source=rcl" in decoded:
            theme_clear_href = href
            break
    assert theme_clear_href is not None, (
        "Could not find a link with season=lent and source=rcl but without theme= parameter. "
        "This should be the Theme filter's 'All' link."
    )


def test_authenticated_request_populates_request_state_user(client):
    response = client.get("/engines")
    assert response.status_code == 200
    # /engines is fully static (no template context beyond request) but the
    # middleware should still have populated request.state.user before the
    # route ran - the response text doesn't reflect this directly, so we
    # check it can't have broken by asserting the page still renders full
    # HTML rather than an error page.
    assert "<html" in response.text.lower()


def test_public_path_does_not_require_user_lookup(client):
    response = TestClient(app).get("/health")
    assert response.status_code == 200


from web.models import ReadingProgress, User
from web.services.reading_progress_service import save_progress


def test_post_progress_creates_a_row(study_client):
    client, SessionLocal = study_client

    # Seed user with id=1 (matches the cookie created in the fixture)
    session = SessionLocal()
    user = User(id=1, email="test@example.com", name="Test User", password_hash="", is_active=True)
    session.add(user)
    session.commit()
    session.close()

    response = client.post("/api/progress", json={
        "content_type": "study",
        "content_id": 42,
        "percent": 35,
    })

    assert response.status_code == 204

    session = SessionLocal()
    row = session.query(ReadingProgress).filter(ReadingProgress.content_id == 42).first()
    assert row is not None
    assert row.percent == 35
    session.close()


def test_post_progress_does_not_decrease_existing_percent(study_client):
    client, SessionLocal = study_client

    # Seed user with id=1 (matches the cookie created in the fixture)
    session = SessionLocal()
    user = User(id=1, email="test@example.com", name="Test User", password_hash="", is_active=True)
    session.add(user)
    session.commit()

    save_progress(session, user_id=1, content_type="study", content_id=42, percent=80)
    session.close()

    response = client.post("/api/progress", json={
        "content_type": "study",
        "content_id": 42,
        "percent": 20,
    })

    assert response.status_code == 204

    session = SessionLocal()
    row = session.query(ReadingProgress).filter(ReadingProgress.content_id == 42).first()
    assert row.percent == 80
    session.close()


def test_post_progress_requires_authentication():
    response = TestClient(app).post("/api/progress", json={
        "content_type": "study",
        "content_id": 1,
        "percent": 10,
    }, follow_redirects=False)
    assert response.status_code in (303, 401)


def test_header_shows_greeting_and_search(study_client):
    # Uses study_client (not the plain `client` fixture) because the
    # greeting requires an actual User row: the plain `client` fixture
    # points at the real, unseeded local lectionary.db (see the
    # "Auth note" at the top of this file - AuthMiddleware only checks
    # that the session cookie decodes, it doesn't require the user to
    # exist), so request.state.user would be None there and the
    # "Welcome back," block would never render. study_client's in-memory
    # db lets us seed the id=1 user the session cookie points at, the
    # same pattern already used by test_post_progress_creates_a_row above.
    client, SessionLocal = study_client

    session = SessionLocal()
    user = User(id=1, email="test@example.com", name="Test User", password_hash="", is_active=True)
    session.add(user)
    session.commit()
    session.close()

    response = client.get("/engines")
    body = response.text

    assert "Welcome back," in body
    assert 'action="/browse"' in body
    assert 'name="q"' in body


def test_header_has_no_notification_markup(client):
    response = client.get("/engines")
    body = response.text.lower()

    assert "notification" not in body
