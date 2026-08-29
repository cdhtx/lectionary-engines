"""
Tests that content generation persists Tier 4 taxonomy data:
reading_date/season (RCL-sourced Study/WorkshopPrep only) and
content_theme rows (every content type, every source).

Each generation route's expensive/external step (the engine's Claude
call, TextFetcher fetches) is mocked at the service-getter level so
these tests exercise real route wiring and real DB writes against an
in-memory SQLite DB, without any network or Claude API call.
"""

from unittest.mock import MagicMock, patch

from web.models import ContentTheme, Study


@patch("web.routes.studies.extract_themes")
@patch("web.routes.studies.get_generator_service")
def test_rcl_sourced_study_gets_reading_date_and_season(mock_get_generator, mock_extract_themes, study_client):
    client, SessionLocal = study_client

    mock_generator = MagicMock()
    mock_generator.fetch_rcl.return_value = ("John 3:16-21", "For God so loved the world")
    mock_generator.generate_study.return_value = {
        "engine": "threshold",
        "reference": "John 3:16-21",
        "content": "study content",
        "metadata": {"word_count": 42},
        "biblical_text": "For God so loved the world",
    }
    mock_get_generator.return_value = mock_generator
    mock_extract_themes.return_value = ["hospitality", "grace"]

    response = client.post("/generate", data={
        "engine": "threshold",
        "source": "rcl",
        "rcl_reading": "gospel",
        "translation": "NRSVue",
        "run_validation": "false",
    }, follow_redirects=False)

    assert response.status_code == 303

    db = SessionLocal()
    study = db.query(Study).one()
    assert study.reading_date is not None
    assert study.season is not None
    themes = {t.theme for t in db.query(ContentTheme).filter(ContentTheme.content_type == "study").all()}
    assert themes == {"hospitality", "grace"}
    db.close()


@patch("web.routes.studies.extract_themes")
@patch("web.routes.studies.get_generator_service")
def test_pasted_study_has_no_reading_date_or_season_but_still_gets_themes(
    mock_get_generator, mock_extract_themes, study_client
):
    client, SessionLocal = study_client

    mock_generator = MagicMock()
    mock_generator.generate_study.return_value = {
        "engine": "threshold",
        "reference": "John 3:16-21",
        "content": "study content",
        "metadata": {"word_count": 42},
        "biblical_text": "For God so loved the world",
    }
    mock_get_generator.return_value = mock_generator
    mock_extract_themes.return_value = ["hospitality"]

    response = client.post("/generate", data={
        "engine": "threshold",
        "source": "paste",
        "reference": "John 3:16-21",
        "text": "For God so loved the world",
        "translation": "NRSVue",
        "run_validation": "false",
    }, follow_redirects=False)

    assert response.status_code == 303

    db = SessionLocal()
    study = db.query(Study).one()
    assert study.reading_date is None
    assert study.season is None
    themes = {t.theme for t in db.query(ContentTheme).filter(ContentTheme.content_type == "study").all()}
    assert themes == {"hospitality"}
    db.close()
