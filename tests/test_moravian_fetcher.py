"""
Tests for TextFetcher.fetch_moravian() staleness handling.

Incident 2026-10-12: moravian.org hadn't published Monday's entry yet, so
/daily_texts/ still showed Sunday's. fetch_moravian() only collected the
Psalm/OT/NT readings from a paragraph naming *today's* weekday, so it found
none, but happily returned Sunday's Watchword/Doctrinal Text as if they were
today's. These tests pin the fixed behavior against real saved moravian.org
pages (tests/fixtures/) so no network is needed.
"""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lectionary_engines.text_fetcher import StaleMoravianEntry, TextFetcher

FIXTURES = Path(__file__).parent / "fixtures"
INDEX_HTML = (FIXTURES / "moravian_index.html").read_text()  # newest entry: Sunday, Oct 11 2026
MONDAY_OCT_5_HTML = (FIXTURES / "moravian_monday-october-5-2026.html").read_text()

BASE = "https://www.moravian.org/daily_texts/"
MONDAY_OCT_12 = date(2026, 10, 12)
MONDAY_OCT_5 = date(2026, 10, 5)


def _response(status, text=""):
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    resp.raise_for_status.side_effect = None if status < 400 else Exception(f"HTTP {status}")
    return resp


def _fake_get(pages):
    """requests.get stand-in: `pages` maps URL -> html; anything else is a 404."""
    def get(url, **kwargs):
        if url in pages:
            return _response(200, pages[url])
        return _response(404)
    return get


@pytest.fixture
def fetcher():
    f = TextFetcher()
    f.fetch = MagicMock(side_effect=lambda ref, translation=None: f"<text of {ref}>")
    return f


def test_raises_stale_entry_when_newest_entry_is_not_today(fetcher):
    # Today's dated page 404s; /daily_texts/ still shows Sunday Oct 11.
    with patch("lectionary_engines.text_fetcher.requests.get", side_effect=_fake_get({BASE: INDEX_HTML})):
        with pytest.raises(StaleMoravianEntry) as exc:
            fetcher.fetch_moravian(today=MONDAY_OCT_12)

    assert exc.value.entry_date == date(2026, 10, 11)
    assert exc.value.today == MONDAY_OCT_12
    fetcher.fetch.assert_not_called()  # don't burn Bible Gateway calls on text we may not use


def test_allow_stale_returns_newest_entry_with_its_own_readings(fetcher):
    with patch("lectionary_engines.text_fetcher.requests.get", side_effect=_fake_get({BASE: INDEX_HTML})):
        reference, text = fetcher.fetch_moravian(allow_stale=True, today=MONDAY_OCT_12)

    # The Psalm/OT/NT readings come from the entry's own date line, not from
    # matching today's weekday - this is the original bug.
    for ref in ("Isaiah 25:1-9", "Psalm 23", "Philippians 4:1-9", "Matthew 22:1-14"):
        assert ref in reference
        assert f"<text of {ref}>" in text
    # Watchword + Doctrinal Text are still included.
    assert "Judges 8:23" in reference
    assert "John 20:28" in reference
    # The study can never silently pass yesterday's text off as today's.
    assert "Sunday, October 11, 2026" in text
    assert "Sunday, October 11" in reference


def test_uses_todays_dated_page_when_it_exists(fetcher):
    pages = {
        BASE: INDEX_HTML,
        BASE + "monday-october-5-2026/": MONDAY_OCT_5_HTML,
    }
    with patch("lectionary_engines.text_fetcher.requests.get", side_effect=_fake_get(pages)):
        reference, text = fetcher.fetch_moravian(today=MONDAY_OCT_5)  # no allow_stale needed

    for ref in ("Psalm 116:1–7", "1 Samuel 24:1–25:17", "John 5:16–30"):
        assert ref in reference
    assert "Monday, October 5, 2026" in text
    # Monday's page also embeds next Sunday's block in its sidebar; none of
    # that should leak into Monday's readings.
    assert "Isaiah 25:1-9" not in reference


def test_moravian_status_reports_whether_todays_entry_is_published(fetcher):
    with patch("lectionary_engines.text_fetcher.requests.get", side_effect=_fake_get({BASE: INDEX_HTML})):
        stale = fetcher.moravian_status(today=MONDAY_OCT_12)
    assert stale == {"entry_date": "2026-10-11", "today": "2026-10-12", "is_current": False}

    pages = {BASE: INDEX_HTML, BASE + "monday-october-5-2026/": MONDAY_OCT_5_HTML}
    with patch("lectionary_engines.text_fetcher.requests.get", side_effect=_fake_get(pages)):
        current = fetcher.moravian_status(today=MONDAY_OCT_5)
    assert current == {"entry_date": "2026-10-05", "today": "2026-10-05", "is_current": True}
