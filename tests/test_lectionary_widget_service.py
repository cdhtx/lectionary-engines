"""
Tests for the Today homepage's "This Week in the Lectionary" cache layer.

fetch_sunday_lectionary_readings() makes live, uncached HTTP calls to an
external site - every test here mocks it. No test in this file should
make a real network call.
"""

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from web.models import Base, LectionaryReadingCache
from web.services.lectionary_widget_service import get_this_week_readings


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


SAMPLE_READINGS = {
    "gospel": "Luke 14:1-14",
    "epistle": "Hebrews 13:1-8, 15-16",
    "ot": "Jeremiah 2:4-13",
    "psalm": "Psalm 81:1, 10-16",
}


@patch("web.services.lectionary_widget_service.TextFetcher")
def test_cache_miss_fetches_and_stores(mock_fetcher_class, db):
    mock_fetcher = mock_fetcher_class.return_value
    mock_fetcher.fetch_sunday_lectionary_readings.return_value = dict(SAMPLE_READINGS)

    result = get_this_week_readings(db)

    assert result["gospel"] == {"reference": "Luke 14:1-14"}
    assert result["epistle"] == {"reference": "Hebrews 13:1-8, 15-16"}
    assert result["ot"] == {"reference": "Jeremiah 2:4-13"}
    assert result["psalm"] == {"reference": "Psalm 81:1, 10-16"}
    assert mock_fetcher.fetch_sunday_lectionary_readings.call_count == 1

    cached_rows = db.query(LectionaryReadingCache).all()
    assert len(cached_rows) == 4
    assert {row.reading_type for row in cached_rows} == {"gospel", "epistle", "ot", "psalm"}


@patch("web.services.lectionary_widget_service.TextFetcher")
def test_cache_hit_skips_fetch(mock_fetcher_class, db):
    mock_fetcher = mock_fetcher_class.return_value
    mock_fetcher.fetch_sunday_lectionary_readings.return_value = dict(SAMPLE_READINGS)

    get_this_week_readings(db)
    assert mock_fetcher.fetch_sunday_lectionary_readings.call_count == 1

    mock_fetcher.fetch_sunday_lectionary_readings.reset_mock()
    result = get_this_week_readings(db)

    assert result["gospel"] == {"reference": "Luke 14:1-14"}
    assert mock_fetcher.fetch_sunday_lectionary_readings.call_count == 0


@patch("web.services.lectionary_widget_service.TextFetcher")
def test_partial_parse_omits_only_the_missing_reading(mock_fetcher_class, db):
    mock_fetcher = mock_fetcher_class.return_value
    partial = dict(SAMPLE_READINGS)
    del partial["psalm"]
    mock_fetcher.fetch_sunday_lectionary_readings.return_value = partial

    result = get_this_week_readings(db)

    assert "psalm" not in result
    assert result["gospel"] == {"reference": "Luke 14:1-14"}
    assert result["epistle"] == {"reference": "Hebrews 13:1-8, 15-16"}
    assert result["ot"] == {"reference": "Jeremiah 2:4-13"}

    cached_rows = db.query(LectionaryReadingCache).all()
    assert len(cached_rows) == 3
    assert "psalm" not in {row.reading_type for row in cached_rows}


@patch("web.services.lectionary_widget_service.TextFetcher")
def test_whole_fetch_failure_returns_empty_dict_not_an_exception(mock_fetcher_class, db):
    mock_fetcher = mock_fetcher_class.return_value
    mock_fetcher.fetch_sunday_lectionary_readings.side_effect = Exception("Vanderbilt site unreachable")

    result = get_this_week_readings(db)

    assert result == {}
    assert db.query(LectionaryReadingCache).count() == 0
