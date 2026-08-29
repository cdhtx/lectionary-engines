"""
Liturgical calendar utilities shared across the app: computing which
Sunday is "this coming Sunday" (previously duplicated privately in both
lectionary_widget_service.py and signals_service.py - consolidated here
since Tier 4's reading_date/season capture needs the same calculation),
and bucketing a date into one of eight liturgical seasons for Study/
WorkshopPrep faceting.
"""

from datetime import date, timedelta

SEASONS = ["advent", "christmas", "epiphany", "lent", "holy_week", "easter", "pentecost", "ordinary_time"]


def _easter_sunday(year: int) -> date:
    """Gregorian Easter Sunday via the Meeus/Jones/Butcher algorithm."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _advent_start(year: int) -> date:
    """Advent Sunday: the Sunday between November 27 and December 3 inclusive."""
    nov27 = date(year, 11, 27)
    days_to_sunday = (6 - nov27.weekday()) % 7  # Monday=0 ... Sunday=6
    return nov27 + timedelta(days=days_to_sunday)


def upcoming_sunday(today: date) -> date:
    """The next Sunday on or after `today` (today itself, if today is a Sunday)."""
    days_until_sunday = (6 - today.weekday()) % 7
    return today + timedelta(days=days_until_sunday)


def season_for_date(d: date) -> str:
    """
    Buckets a date into one of SEASONS. Lent/Holy Week/Easter/Pentecost
    are moveable feasts computed from that year's Easter Sunday;
    Advent/Christmas/Epiphany are fixed-calendar-adjacent.

    'ordinary_time' covers only the post-Pentecost stretch through the
    day before the next Advent - the pre-Lent stretch (Jan 6 through the
    day before Ash Wednesday) is its own 'epiphany' bucket.
    """
    year = d.year

    if d.month == 1 and d.day <= 5:
        return "christmas"  # Jan 1-5: Christmastide begun by the previous year's Dec 25

    advent_start = _advent_start(year)
    if d.month == 12:
        if d < advent_start:
            return "ordinary_time"
        if d >= date(year, 12, 25):
            return "christmas"
        return "advent"

    if d >= advent_start:
        return "advent"

    easter = _easter_sunday(year)
    ash_wednesday = easter - timedelta(days=46)
    palm_sunday = easter - timedelta(days=7)
    pentecost = easter + timedelta(days=49)

    if date(year, 1, 6) <= d < ash_wednesday:
        return "epiphany"
    if ash_wednesday <= d < palm_sunday:
        return "lent"
    if palm_sunday <= d < easter:
        return "holy_week"
    if easter <= d < pentecost:
        return "easter"
    if d == pentecost:
        return "pentecost"
    return "ordinary_time"
