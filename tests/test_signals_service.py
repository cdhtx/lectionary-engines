"""
Tests for the Signals service: detects thematic overlap among this
week's four lectionary readings.

Two external dependencies are mocked in every test: TextFetcher (used
by both this service directly, for full-text fetching, and internally
by lectionary_widget_service.get_this_week_readings() for reference
fetching - two separate import bindings, both must be patched) and
extract_themes (the Claude call). No test in this file makes a real
network or Claude API call.
"""

from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from web.models import Base
from web.services.signals_service import get_this_week_signals


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


def _mock_readings_fetcher(mock_class):
    """Configures a mocked TextFetcher class for get_this_week_readings()'s
    internal fetch_sunday_lectionary_readings() call."""
    instance = mock_class.return_value
    instance.fetch_sunday_lectionary_readings.return_value = {
        "gospel": "Luke 14:1-14",
        "epistle": "Hebrews 13:1-8, 15-16",
        "ot": "Jeremiah 2:4-13",
        "psalm": "Psalm 81:1, 10-16",
    }
    return instance


@patch("web.services.lectionary_widget_service.TextFetcher")
@patch("web.services.signals_service.TextFetcher")
@patch("web.services.signals_service.extract_themes")
def test_two_readings_sharing_a_theme_produce_a_connection(
    mock_extract_themes, mock_signals_fetcher_class, mock_readings_fetcher_class, db
):
    _mock_readings_fetcher(mock_readings_fetcher_class)
    mock_signals_fetcher_class.return_value.fetch.return_value = "full passage text"

    def themes_by_reference(claude, reference, text):
        if reference == "Luke 14:1-14":
            return ["hospitality", "humility"]
        if reference == "Jeremiah 2:4-13":
            return ["unfaithfulness", "hospitality"]
        if reference == "Hebrews 13:1-8, 15-16":
            return ["epistle-only-theme"]
        return ["psalm-only-theme"]  # Psalm 81:1, 10-16

    mock_extract_themes.side_effect = themes_by_reference

    result = get_this_week_signals(db, claude=Mock())

    assert len(result) == 1
    connection = result[0]
    assert connection["reading_a_type"] == "gospel"
    assert connection["reading_b_type"] == "ot"
    assert connection["shared_themes"] == ["Hospitality"]


@patch("web.services.lectionary_widget_service.TextFetcher")
@patch("web.services.signals_service.TextFetcher")
@patch("web.services.signals_service.extract_themes")
def test_no_shared_themes_produces_no_connections(
    mock_extract_themes, mock_signals_fetcher_class, mock_readings_fetcher_class, db
):
    _mock_readings_fetcher(mock_readings_fetcher_class)
    mock_signals_fetcher_class.return_value.fetch.return_value = "full passage text"
    mock_extract_themes.side_effect = lambda claude, reference, text: [reference]  # every reading's theme is unique

    result = get_this_week_signals(db, claude=Mock())

    assert result == []


@patch("web.services.lectionary_widget_service.TextFetcher")
@patch("web.services.signals_service.TextFetcher")
@patch("web.services.signals_service.extract_themes")
def test_cache_hit_skips_fetch_and_extraction(
    mock_extract_themes, mock_signals_fetcher_class, mock_readings_fetcher_class, db
):
    _mock_readings_fetcher(mock_readings_fetcher_class)
    mock_signals_fetcher_class.return_value.fetch.return_value = "full passage text"
    mock_extract_themes.side_effect = lambda claude, reference, text: ["shared-theme"]

    get_this_week_signals(db, claude=Mock())  # first call populates the theme cache
    assert mock_extract_themes.call_count == 4

    mock_extract_themes.reset_mock()
    mock_signals_fetcher_class.return_value.fetch.reset_mock()

    result = get_this_week_signals(db, claude=Mock())  # second call should hit the cache

    assert mock_extract_themes.call_count == 0
    assert mock_signals_fetcher_class.return_value.fetch.call_count == 0
    assert len(result) == 6  # all C(4,2) pairs share "shared-theme"


@patch("web.services.lectionary_widget_service.TextFetcher")
@patch("web.services.signals_service.TextFetcher")
@patch("web.services.signals_service.extract_themes")
def test_extraction_failure_for_one_reading_does_not_block_others(
    mock_extract_themes, mock_signals_fetcher_class, mock_readings_fetcher_class, db
):
    _mock_readings_fetcher(mock_readings_fetcher_class)
    mock_signals_fetcher_class.return_value.fetch.return_value = "full passage text"

    def themes_or_fail(claude, reference, text):
        if reference == "Jeremiah 2:4-13":
            return []  # extract_themes returns [] on failure per its own docstring
        return ["hospitality"]

    mock_extract_themes.side_effect = themes_or_fail

    result = get_this_week_signals(db, claude=Mock())

    # gospel, epistle, psalm all share "hospitality" -> 3 pairs; "ot" (Jeremiah) excluded entirely
    assert len(result) == 3
    assert all("ot" not in (c["reading_a_type"], c["reading_b_type"]) for c in result)


@patch("web.services.lectionary_widget_service.TextFetcher")
@patch("web.services.signals_service.TextFetcher")
@patch("web.services.signals_service.extract_themes")
def test_fewer_than_two_reading_types_returns_empty_list(
    mock_extract_themes, mock_signals_fetcher_class, mock_readings_fetcher_class, db
):
    # get_this_week_readings() itself failed entirely (e.g. the Vanderbilt
    # site was down) - it returns {} in that case, per its own docstring.
    mock_readings_fetcher_class.return_value.fetch_sunday_lectionary_readings.return_value = {}

    result = get_this_week_signals(db, claude=Mock())

    assert result == []
    mock_signals_fetcher_class.return_value.fetch.assert_not_called()
    mock_extract_themes.assert_not_called()


@patch("web.services.lectionary_widget_service.TextFetcher")
@patch("web.services.signals_service.TextFetcher")
@patch("web.services.signals_service.extract_themes")
def test_results_sorted_by_shared_theme_count_descending(
    mock_extract_themes, mock_signals_fetcher_class, mock_readings_fetcher_class, db
):
    _mock_readings_fetcher(mock_readings_fetcher_class)
    mock_signals_fetcher_class.return_value.fetch.return_value = "full passage text"

    def themes_by_reference(claude, reference, text):
        return {
            "Luke 14:1-14": ["a", "b", "c"],
            "Jeremiah 2:4-13": ["a", "b"],
            "Hebrews 13:1-8, 15-16": ["a"],
            "Psalm 81:1, 10-16": ["z"],
        }[reference]

    mock_extract_themes.side_effect = themes_by_reference

    result = get_this_week_signals(db, claude=Mock())

    # gospel/ot share {a,b} (2), gospel/epistle share {a} (1), epistle/ot share {a} (1), psalm shares nothing
    assert len(result) == 3
    assert len(result[0]["shared_themes"]) == 2
    assert result[0]["reading_a_type"] == "gospel"
    assert result[0]["reading_b_type"] == "ot"
