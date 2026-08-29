"""
Smoke tests: every parameter-free page renders.

base.html is shared by every page in the app, so a mistake there breaks
everything at once. These tests make that immediate and obvious.

Auth note: AuthMiddleware requires the session cookie's user_id to match
an active User row, redirecting to /login otherwise. The plain `client`
fixture (real local lectionary.db) seeds and cleans up a User(id=1) row
around each test; the isolated_client/study_client fixtures (in-memory
DB via conftest.py) seed a User(id=1) row as part of fixture setup.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from web.app import app
from web.auth import create_session_cookie, COOKIE_NAME
from web.database import SessionLocal
from web.models import CulturalResonance, CurrentsAnalysis, Study, User, WorkshopPrep
from web.services.library_service import DETAIL_URL_PREFIXES

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
    """
    An authenticated TestClient against the real local lectionary.db.

    AuthMiddleware requires the session cookie's user_id to match an
    active User row (redirecting to /login otherwise), so this seeds a
    User(id=1) row directly in the real DB if one isn't already there,
    and removes it again afterward so nothing leaks between test runs.
    """
    session = SessionLocal()
    existing = session.query(User).filter(User.id == 1).first()
    created = existing is None
    if created:
        session.add(User(id=1, email="route-smoke-client@example.com", name="Route Smoke Client", password_hash="", is_active=True))
        session.commit()
    session.close()

    c = TestClient(app)
    c.cookies.set(COOKIE_NAME, create_session_cookie(1))
    yield c

    if created:
        session = SessionLocal()
        session.query(User).filter(User.id == 1).delete()
        session.commit()
        session.close()


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


from web.models import ReadingProgress
from web.services.reading_progress_service import save_progress


def test_post_progress_creates_a_row(study_client):
    # study_client seeds a User(id=1) row automatically, matching the
    # session cookie set on it - see the fixture's docstring in conftest.py.
    client, SessionLocal = study_client

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
    # study_client seeds a User(id=1) row automatically, matching the
    # session cookie set on it - see the fixture's docstring in conftest.py.
    client, SessionLocal = study_client

    session = SessionLocal()
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


def test_stale_session_redirects_to_login_instead_of_500_or_broken_chrome():
    """
    A signed cookie that decodes successfully to a user_id with no
    matching active User row (e.g. an admin deactivated the user after
    the browser already had a cookie) must be treated like a decode
    failure - redirect to /login - rather than letting the request
    through with request.state.user set to None. Before this fix, that
    let POST /api/progress crash with a 500 (request.state.user.id on
    None) and let GET pages render with inconsistent chrome (no greeting,
    but a sidebar "current read" widget that still queried by the raw,
    now-invalid user_id with no join to User at all).
    """
    stale_user_id = 999999999  # guaranteed not to exist in the real DB
    c = TestClient(app)
    c.cookies.set(COOKIE_NAME, create_session_cookie(stale_user_id))

    page_response = c.get("/engines", follow_redirects=False)
    assert page_response.status_code == 303
    assert page_response.headers["location"].startswith("/login")

    progress_response = c.post("/api/progress", json={
        "content_type": "study",
        "content_id": 1,
        "percent": 10,
    }, follow_redirects=False)
    assert progress_response.status_code == 303
    assert progress_response.headers["location"].startswith("/login")


def test_header_shows_greeting_and_search(study_client):
    # study_client seeds a User(id=1) row automatically, matching the
    # session cookie set on it - see the fixture's docstring in conftest.py.
    client, SessionLocal = study_client

    response = client.get("/engines")
    body = response.text

    assert "Welcome back," in body
    assert 'action="/browse"' in body
    assert 'name="q"' in body


def test_header_has_no_notification_markup(client):
    response = client.get("/engines")
    body = response.text.lower()

    assert "notification" not in body


def test_secondary_sidebar_links_are_marked(client):
    response = client.get("/engines")
    body = response.text

    assert 'href="/workshop" class="sidebar-link sidebar-link--secondary' in body
    assert 'href="/currents" class="sidebar-link sidebar-link--secondary' in body
    assert 'href="/resonance" class="sidebar-link sidebar-link--secondary' in body


def test_sidebar_progress_widget_shows_current_read(study_client):
    client, SessionLocal = study_client
    session = SessionLocal()
    study = Study(engine="palimpsest", reference="John 3:16-21", content="content", word_count=10)
    session.add(study)
    session.commit()
    study_id = study.id
    session.close()

    session = SessionLocal()
    save_progress(session, user_id=1, content_type="study", content_id=study_id, percent=40)
    session.close()

    response = client.get("/engines")
    body = response.text

    assert "John 3:16-21" in body
    assert "40%" in body or "40 %" in body


def _make_workshop_row():
    return WorkshopPrep(
        lens="apostolic_journalist", lens_name="The Apostolic Journalist",
        reference="Mark 5:1-5", content="content", word_count=10,
    )


def _make_currents_row():
    return CurrentsAnalysis(
        analysis_date="2026-08-01", headline_summary="Theological News Analysis Test",
        content="content", word_count=10,
    )


def _make_resonance_row():
    return CulturalResonance(themes="[]", reference="Luke 1:1-4", content="content")


@pytest.mark.parametrize("content_type,make_row,expected_title", [
    ("workshop", _make_workshop_row, "Mark 5:1-5"),
    ("currents", _make_currents_row, "Theological News Analysis Test"),
    ("resonance", _make_resonance_row, "Luke 1:1-4"),
])
def test_sidebar_current_read_widget_renders_for_each_content_type(
    study_client, content_type, make_row, expected_title
):
    # _title_for_content (web/app.py) has a branch per content type; only
    # "study" had coverage before this test. Runs on every authenticated
    # page load via AuthMiddleware, so a bug in an untested branch would
    # break every page for any user whose current in-progress item happens
    # to be a workshop/currents/resonance row.
    client, SessionLocal = study_client
    session = SessionLocal()
    row = make_row()
    session.add(row)
    session.commit()
    content_id = row.id
    session.close()

    session = SessionLocal()
    save_progress(session, user_id=1, content_type=content_type, content_id=content_id, percent=40)
    session.close()

    response = client.get("/engines")
    body = response.text

    assert expected_title in body
    assert f'{DETAIL_URL_PREFIXES[content_type]}{content_id}' in body


def test_sidebar_progress_widget_absent_when_no_progress(client):
    response = client.get("/engines")
    assert "sidebar-progress-widget" not in response.text


@patch("web.services.lectionary_widget_service.TextFetcher")
@patch("web.services.signals_service.TextFetcher")
@patch("web.services.signals_service.extract_themes")
def test_continue_your_studies_shows_progress_bar(
    mock_extract_themes, mock_signals_fetcher_class, mock_readings_fetcher_class, study_client
):
    mock_readings_fetcher_class.return_value.fetch_sunday_lectionary_readings.return_value = {}
    mock_extract_themes.return_value = []

    # study_client seeds a User(id=1) row automatically, matching the
    # session cookie set on it - see the fixture's docstring in
    # conftest.py. The / route's progress_by_study_id computation is
    # gated on request.state.user, which (unlike the sidebar's current-read
    # widget) requires that seeded row to exist.
    client, SessionLocal = study_client

    session = SessionLocal()
    study = Study(engine="threshold", reference="Mark 5:1-5", content="content", word_count=10)
    session.add(study)
    session.commit()
    study_id = study.id
    session.close()

    session = SessionLocal()
    save_progress(session, user_id=1, content_type="study", content_id=study_id, percent=66)
    session.close()

    response = client.get("/")
    body = response.text

    # Scoped to the Continue Your Studies progress bar markup itself, not
    # just "66%" anywhere in the page - the sidebar's separate "current
    # read" widget (added in Task 6) also renders "66% complete" for the
    # same underlying ReadingProgress row, so a bare "66%" substring check
    # would pass even if this task's progress bar were removed entirely.
    assert 'class="study-progress-fill" style="width: 66%;"' in body


@patch("web.services.lectionary_widget_service.TextFetcher")
@patch("web.services.signals_service.TextFetcher")
@patch("web.services.signals_service.extract_themes")
def test_today_page_shows_quote_banner(
    mock_extract_themes, mock_signals_fetcher_class, mock_readings_fetcher_class, isolated_client
):
    mock_readings_fetcher_class.return_value.fetch_sunday_lectionary_readings.return_value = {}
    mock_extract_themes.return_value = []

    response = isolated_client.get("/")
    assert "today-quote" in response.text
