"""
Tests for the one-time content_theme backfill script (Tier 4 -
populates content_theme for rows created before this tier shipped).
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from web.models import Base, ContentTheme, CulturalResonance, CurrentsAnalysis, Study, WorkshopPrep
from web.scripts.backfill_content_themes import (
    backfill_currents,
    backfill_resonance,
    backfill_study,
    backfill_workshop,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


def test_backfill_resonance_parses_existing_themes_json_with_no_claude_calls(db):
    db.add(CulturalResonance(themes='["hospitality", "empire"]', content="c"))
    db.commit()

    count = backfill_resonance(db)

    assert count == 1
    themes = {t.theme for t in db.query(ContentTheme).filter(ContentTheme.content_type == "resonance").all()}
    assert themes == {"hospitality", "empire"}


def test_backfill_resonance_skips_rows_already_backfilled(db):
    db.add(CulturalResonance(themes='["hospitality"]', content="c"))
    db.commit()
    backfill_resonance(db)

    count = backfill_resonance(db)  # second run

    assert count == 0
    assert db.query(ContentTheme).count() == 1


def test_backfill_resonance_coerces_non_string_theme_elements_to_strings(db):
    db.add(CulturalResonance(themes="[1, 2, 3]", content="c"))
    db.commit()

    count = backfill_resonance(db)

    assert count == 1
    themes = {t.theme for t in db.query(ContentTheme).all()}
    assert themes == {"1", "2", "3"}


def test_backfill_resonance_skips_malformed_json_row_without_aborting_the_run(db):
    bad = CulturalResonance(themes="not valid json{", content="bad")
    good = CulturalResonance(themes='["hospitality"]', content="good")
    db.add(bad)
    db.add(good)
    db.commit()

    count = backfill_resonance(db)  # must not raise

    assert count == 1
    assert db.query(ContentTheme).filter(ContentTheme.content_id == good.id).count() == 1
    assert db.query(ContentTheme).filter(ContentTheme.content_id == bad.id).count() == 0


@patch("web.scripts.backfill_content_themes.extract_themes")
def test_backfill_study_calls_extract_themes_once_per_unbackfilled_row(mock_extract_themes, db):
    db.add(Study(engine="threshold", reference="John 3:16", content="c1"))
    db.add(Study(engine="threshold", reference="Luke 14:1", content="c2"))
    db.commit()
    mock_extract_themes.return_value = ["grace"]

    count = backfill_study(db, claude=MagicMock())

    assert count == 2
    assert mock_extract_themes.call_count == 2
    assert db.query(ContentTheme).filter(ContentTheme.content_type == "study").count() == 2


@patch("web.scripts.backfill_content_themes.extract_themes")
def test_backfill_study_is_idempotent(mock_extract_themes, db):
    db.add(Study(engine="threshold", reference="John 3:16", content="c1"))
    db.commit()
    mock_extract_themes.return_value = ["grace"]
    backfill_study(db, claude=MagicMock())

    mock_extract_themes.reset_mock()
    count = backfill_study(db, claude=MagicMock())

    assert count == 0
    assert mock_extract_themes.call_count == 0


@patch("web.scripts.backfill_content_themes.extract_themes")
def test_backfill_workshop_calls_extract_themes_per_unbackfilled_row(mock_extract_themes, db):
    db.add(WorkshopPrep(lens="x", lens_name="X", reference="John 3:16", content="c1"))
    db.commit()
    mock_extract_themes.return_value = ["grace"]

    count = backfill_workshop(db, claude=MagicMock())

    assert count == 1
    assert db.query(ContentTheme).filter(ContentTheme.content_type == "workshop").count() == 1


@patch("web.scripts.backfill_content_themes.extract_themes")
def test_backfill_currents_calls_extract_themes_per_unbackfilled_row(mock_extract_themes, db):
    db.add(CurrentsAnalysis(
        analysis_date="Aug 28, 2026", headline_summary="A Headline",
        content="c1", story_context="story",
    ))
    db.commit()
    mock_extract_themes.return_value = ["justice"]

    count = backfill_currents(db, claude=MagicMock())

    assert count == 1
    assert db.query(ContentTheme).filter(ContentTheme.content_type == "currents").count() == 1
