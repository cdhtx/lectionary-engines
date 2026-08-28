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

from datetime import date
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from web.models import Base, LectionaryThemeCache
from web.services.signals_service import _get_themes_for_reading, get_this_week_signals


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


@patch("web.services.signals_service.get_this_week_readings")
@patch("web.services.signals_service.TextFetcher")
@patch("web.services.signals_service.extract_themes")
def test_pair_order_and_reading_assignment_deterministic_regardless_of_input_dict_order(
    mock_extract_themes, mock_signals_fetcher_class, mock_get_this_week_readings, db
):
    """
    get_this_week_readings() reads from an unordered DB query, so its
    returned dict's key order isn't guaranteed to be the same across
    requests (especially on Postgres in production). Two pairs here tie at
    1 shared theme each (gospel/ot share "a", epistle/psalm share "b") -
    exactly the case where an unstable tie-break would let pair order and
    reading_a/reading_b assignment vary between requests. Calling
    get_this_week_signals() twice, once with the readings dict in canonical
    order and once in reversed order (simulating two requests that got rows
    back in different order), must produce identical output both times.
    """
    mock_signals_fetcher_class.return_value.fetch.return_value = "full passage text"

    def themes_by_reference(claude, reference, text):
        return {
            "Luke 14:1-14": ["a"],
            "Hebrews 13:1-8, 15-16": ["b"],
            "Jeremiah 2:4-13": ["a"],
            "Psalm 81:1, 10-16": ["b"],
        }[reference]

    mock_extract_themes.side_effect = themes_by_reference

    readings_canonical_order = {
        "gospel": {"reference": "Luke 14:1-14"},
        "epistle": {"reference": "Hebrews 13:1-8, 15-16"},
        "ot": {"reference": "Jeremiah 2:4-13"},
        "psalm": {"reference": "Psalm 81:1, 10-16"},
    }
    readings_reversed_order = {
        "psalm": {"reference": "Psalm 81:1, 10-16"},
        "ot": {"reference": "Jeremiah 2:4-13"},
        "epistle": {"reference": "Hebrews 13:1-8, 15-16"},
        "gospel": {"reference": "Luke 14:1-14"},
    }

    mock_get_this_week_readings.return_value = readings_canonical_order
    result_1 = get_this_week_signals(db, claude=Mock())

    # Clear the theme cache so the second call re-extracts rather than
    # short-circuiting on the cache-hit path populated by the first call.
    db.query(LectionaryThemeCache).delete()
    db.commit()

    mock_get_this_week_readings.return_value = readings_reversed_order
    result_2 = get_this_week_signals(db, claude=Mock())

    assert len(result_1) == 2
    assert result_1 == result_2
    assert [(c["reading_a_type"], c["reading_b_type"]) for c in result_1] == [
        ("epistle", "psalm"),
        ("gospel", "ot"),
    ]


@patch("web.services.signals_service.TextFetcher")
@patch("web.services.signals_service.extract_themes")
def test_concurrent_cache_write_race_handled_gracefully(
    mock_extract_themes, mock_signals_fetcher_class, db
):
    """
    Verify the race condition handling: when two requests both get a cache
    miss for the same (sunday, reading_type) and race to write, the loser
    (who encounters IntegrityError) rolls back, re-queries, and returns the
    winner's cached themes instead of raising.

    The trick: we mock db.commit to raise IntegrityError, but during that
    mock we also insert the "winner's" row so the re-query finds it.
    """
    import json
    from sqlalchemy.exc import IntegrityError

    sunday = date(2026, 8, 31)
    reading_type = "gospel"
    reference = "Luke 14:1-14"

    # Themes the "other concurrent request" will have cached
    other_request_themes = ["faith", "trust"]
    # Themes this call freshly extracts (different, so we can verify the
    # function returned the winner's themes, not the loser's freshly-computed ones)
    my_themes = ["computed", "themes"]

    mock_signals_fetcher_class.return_value.fetch.return_value = "full passage text"
    mock_extract_themes.return_value = my_themes

    # Mock db.commit to simulate the race: raise IntegrityError, but first
    # insert the "other request's" row so the re-query in the except block finds it
    original_commit = db.commit

    def mock_commit_with_race():
        # Simulate the other request winning the race by inserting its row first
        db.expunge_all()  # Clear session state
        other_row = LectionaryThemeCache(
            reading_date=sunday,
            reading_type=reading_type,
            themes=json.dumps(other_request_themes),
        )
        db.add(other_row)
        original_commit()  # Actually commit the other request's row to the database

        # Now raise IntegrityError as if our insert failed due to the constraint
        raise IntegrityError("statement", "params", "orig")

    with patch.object(db, 'commit', side_effect=mock_commit_with_race):
        result = _get_themes_for_reading(
            db, claude=Mock(), sunday=sunday, reading_type=reading_type, reference=reference
        )

    # The function should have returned the other request's cached themes,
    # not the freshly extracted ones. This proves the except-block was reached.
    assert result == other_request_themes
    assert result != my_themes
