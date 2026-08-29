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


from web.models import WorkshopPrep


@patch("web.routes.workshop.extract_themes")
@patch("web.routes.workshop.get_workshop_engine")
@patch("web.routes.workshop.get_text_fetcher")
def test_rcl_sourced_workshop_gets_reading_date_and_season(
    mock_get_text_fetcher, mock_get_workshop_engine, mock_extract_themes, study_client
):
    client, SessionLocal = study_client

    mock_fetcher = MagicMock()
    mock_fetcher.fetch_rcl.return_value = ("Luke 14:1-14", "Sabbath hospitality text")
    mock_get_text_fetcher.return_value = mock_fetcher

    mock_engine = MagicMock()
    mock_engine.claude = MagicMock()
    mock_engine.generate.return_value = {
        "lens": "apostolic_journalist",
        "lens_name": "The Apostolic Journalist",
        "reference": "Luke 14:1-14",
        "content": "workshop content",
        "metadata": {"word_count": 30},
    }
    mock_get_workshop_engine.return_value = mock_engine
    mock_extract_themes.return_value = ["hospitality"]

    response = client.post("/workshop/generate", data={
        "lens": "apostolic_journalist",
        "source": "rcl",
        "rcl_reading": "gospel",
        "translation": "NRSVue",
    }, follow_redirects=False)

    assert response.status_code == 303

    db = SessionLocal()
    prep = db.query(WorkshopPrep).one()
    assert prep.reading_date is not None
    assert prep.season is not None
    themes = {t.theme for t in db.query(ContentTheme).filter(ContentTheme.content_type == "workshop").all()}
    assert themes == {"hospitality"}
    db.close()


from web.models import CurrentsAnalysis


@patch("web.routes.currents.extract_themes")
@patch("web.routes.currents.get_currents_service")
def test_currents_analysis_gets_content_theme_rows(mock_get_service, mock_extract_themes, study_client):
    client, SessionLocal = study_client

    mock_service = MagicMock()
    mock_service.analyze_story.return_value = {
        "date": "August 28, 2026",
        "headline_summary": "A Test Headline",
        "content": "analysis content",
        "word_count": 50,
    }
    mock_get_service.return_value = mock_service
    mock_extract_themes.return_value = ["justice", "community"]

    response = client.post("/currents/analyze", data={
        "story_context": "Some news story about justice and community.",
    }, follow_redirects=False)

    assert response.status_code == 303

    db = SessionLocal()
    assert db.query(CurrentsAnalysis).count() == 1
    themes = {t.theme for t in db.query(ContentTheme).filter(ContentTheme.content_type == "currents").all()}
    assert themes == {"justice", "community"}
    db.close()


@patch("web.routes.resonance.get_resonance_engine")
def test_resonance_find_gets_content_theme_rows(mock_get_engine, study_client):
    client, SessionLocal = study_client

    mock_engine = MagicMock()
    mock_engine.claude = MagicMock()  # truthy, so the "claude" mining_mode branch is taken
    mock_engine.mine_artifacts.return_value = "resonance content"
    mock_get_engine.return_value = mock_engine

    response = client.post("/resonance/find", data={
        "themes": "Hospitality, Empire",
        "mining_mode": "claude",
    }, follow_redirects=False)

    assert response.status_code == 303

    db = SessionLocal()
    themes = {t.theme for t in db.query(ContentTheme).filter(ContentTheme.content_type == "resonance").all()}
    assert themes == {"hospitality", "empire"}
    db.close()
