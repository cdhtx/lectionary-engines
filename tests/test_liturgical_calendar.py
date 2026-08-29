"""
Tests for the shared liturgical calendar utilities: season_for_date()
(buckets a date into one of eight liturgical seasons, for Study/
WorkshopPrep faceting) and upcoming_sunday() (the single shared
implementation of a calculation previously duplicated privately in
lectionary_widget_service.py and signals_service.py).
"""

from datetime import date, timedelta

from lectionary_engines.liturgical_calendar import (
    _advent_start,
    _easter_sunday,
    season_for_date,
    upcoming_sunday,
)


def test_easter_sunday_matches_known_reference_dates():
    known = {
        2024: date(2024, 3, 31),
        2025: date(2025, 4, 20),
        2026: date(2026, 4, 5),
        2027: date(2027, 3, 28),
        2028: date(2028, 4, 16),
    }
    for year, expected in known.items():
        assert _easter_sunday(year) == expected


def test_advent_start_falls_within_nov_27_to_dec_3_and_is_a_sunday():
    for year in range(2024, 2031):
        d = _advent_start(year)
        assert (d.month, d.day) in [(11, 27), (11, 28), (11, 29), (11, 30), (12, 1), (12, 2), (12, 3)]
        assert d.weekday() == 6  # Sunday


def test_season_boundaries_for_2026():
    assert season_for_date(date(2026, 1, 3)) == "christmas"
    assert season_for_date(date(2026, 1, 6)) == "epiphany"
    assert season_for_date(date(2026, 2, 1)) == "epiphany"
    assert season_for_date(date(2026, 2, 18)) == "lent"          # Ash Wednesday
    assert season_for_date(date(2026, 3, 15)) == "lent"
    assert season_for_date(date(2026, 3, 29)) == "holy_week"     # Palm Sunday
    assert season_for_date(date(2026, 4, 4)) == "holy_week"      # Holy Saturday
    assert season_for_date(date(2026, 4, 5)) == "easter"         # Easter Sunday
    assert season_for_date(date(2026, 5, 1)) == "easter"
    assert season_for_date(date(2026, 5, 24)) == "pentecost"
    assert season_for_date(date(2026, 5, 25)) == "ordinary_time"
    assert season_for_date(date(2026, 10, 1)) == "ordinary_time"
    assert season_for_date(date(2026, 11, 20)) == "ordinary_time"
    assert season_for_date(date(2026, 11, 29)) == "advent"       # Advent Sunday
    assert season_for_date(date(2026, 12, 20)) == "advent"
    assert season_for_date(date(2026, 12, 24)) == "advent"
    assert season_for_date(date(2026, 12, 25)) == "christmas"
    assert season_for_date(date(2027, 1, 4)) == "christmas"


def test_ordinary_time_ends_the_day_before_advent_begins():
    for year in range(2024, 2031):
        advent_start = _advent_start(year)
        assert season_for_date(advent_start) == "advent"
        assert season_for_date(advent_start - timedelta(days=1)) == "ordinary_time"


def test_upcoming_sunday_from_various_weekdays():
    assert upcoming_sunday(date(2026, 8, 24)) == date(2026, 8, 30)  # Monday
    assert upcoming_sunday(date(2026, 8, 26)) == date(2026, 8, 30)  # Wednesday
    assert upcoming_sunday(date(2026, 8, 30)) == date(2026, 8, 30)  # Sunday itself
