"""
Tests for the Today homepage's "This Week in the Lectionary" cache layer.

fetch_rcl() makes a live, uncached HTTP call to an external site - every
test here mocks it. No test in this file should make a real network call.
"""

from datetime import date
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


@patch("web.services.lectionary_widget_service.TextFetcher")
def test_cache_miss_fetches_and_stores(mock_fetcher_class, db):
    mock_fetcher = mock_fetcher_class.return_value
    mock_fetcher.fetch_rcl.side_effect = lambda reading_type: (f"{reading_type}-ref", f"{reading_type}-text")

    result = get_this_week_readings(db)

    assert result["gospel"] == {"reference": "gospel-ref", "text": "gospel-text"}
    assert result["epistle"] == {"reference": "epistle-ref", "text": "epistle-text"}
    assert result["ot"] == {"reference": "ot-ref", "text": "ot-text"}
    assert result["psalm"] == {"reference": "psalm-ref", "text": "psalm-text"}
    assert mock_fetcher.fetch_rcl.call_count == 4

    cached_rows = db.query(LectionaryReadingCache).all()
    assert len(cached_rows) == 4
    assert {row.reading_type for row in cached_rows} == {"gospel", "epistle", "ot", "psalm"}


@patch("web.services.lectionary_widget_service.TextFetcher")
def test_cache_hit_skips_fetch(mock_fetcher_class, db):
    mock_fetcher = mock_fetcher_class.return_value
    mock_fetcher.fetch_rcl.side_effect = lambda reading_type: (f"{reading_type}-ref", f"{reading_type}-text")

    # First call populates the cache.
    get_this_week_readings(db)
    assert mock_fetcher.fetch_rcl.call_count == 4

    # Second call on the same day should hit the cache, not fetch again.
    mock_fetcher.fetch_rcl.reset_mock()
    result = get_this_week_readings(db)

    assert result["gospel"] == {"reference": "gospel-ref", "text": "gospel-text"}
    assert mock_fetcher.fetch_rcl.call_count == 0


@patch("web.services.lectionary_widget_service.TextFetcher")
def test_one_failed_fetch_does_not_block_the_others(mock_fetcher_class, db):
    mock_fetcher = mock_fetcher_class.return_value

    def side_effect(reading_type):
        if reading_type == "psalm":
            raise Exception("Vanderbilt site unreachable")
        return (f"{reading_type}-ref", f"{reading_type}-text")

    mock_fetcher.fetch_rcl.side_effect = side_effect

    result = get_this_week_readings(db)

    assert "psalm" not in result
    assert result["gospel"] == {"reference": "gospel-ref", "text": "gospel-text"}
    assert result["epistle"] == {"reference": "epistle-ref", "text": "epistle-text"}
    assert result["ot"] == {"reference": "ot-ref", "text": "ot-text"}

    cached_rows = db.query(LectionaryReadingCache).all()
    assert len(cached_rows) == 3
    assert "psalm" not in {row.reading_type for row in cached_rows}
