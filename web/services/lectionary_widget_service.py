"""
Today homepage's "This Week in the Lectionary" widget: fetches and caches
the upcoming Sunday's RCL service readings (Gospel, Epistle, Hebrew
Scripture, Psalm).

Uses TextFetcher.fetch_sunday_lectionary_readings(), which targets
Vanderbilt's Sunday-specific lectionary texts page - not fetch_rcl(),
which serves the *daily office* reading and (confirmed during Tier 1b
review) does not reliably expose four distinct, correctly-labeled
readings: weekdays wrap multiple readings in one link with no Gospel at
all, and Sundays have none.

Cached by the *Sunday's* date (the readings' effective date), not
"today" - Monday through Saturday of the same week all want the same
upcoming Sunday's readings, so they share one cache row instead of
re-fetching daily.

The whole fetch can fail outright (network/site down) or partially (one
pericope missing/malformed on a given Sunday's page) - both are handled
without crashing the homepage: a total failure returns {}, a partial
parse returns whatever readings were found.
"""

import logging
from datetime import date, timedelta
from typing import Dict

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from lectionary_engines.text_fetcher import TextFetcher
from web.models import LectionaryReadingCache

logger = logging.getLogger(__name__)


def _upcoming_sunday(today: date) -> date:
    days_until_sunday = (6 - today.weekday()) % 7  # Monday=0 ... Sunday=6
    return today + timedelta(days=days_until_sunday)


def get_this_week_readings(db: Session) -> Dict[str, dict]:
    """
    Returns a dict keyed by reading type ("gospel", "epistle", "ot",
    "psalm"). Each present key's value is {"reference": str}. A key is
    absent if that reading could not be parsed from the Sunday texts
    page, or if the entire fetch failed and nothing was cached yet for
    this Sunday.
    """
    sunday = _upcoming_sunday(date.today())

    cached_rows = (
        db.query(LectionaryReadingCache)
        .filter(LectionaryReadingCache.reading_date == sunday)
        .all()
    )
    if cached_rows:
        return {row.reading_type: {"reference": row.reference} for row in cached_rows}

    fetcher = TextFetcher()
    try:
        readings = fetcher.fetch_sunday_lectionary_readings()
    except Exception as e:
        logger.warning(f"Failed to fetch this week's lectionary readings: {e}")
        return {}

    results: Dict[str, dict] = {}
    for reading_type, reference in readings.items():
        row = LectionaryReadingCache(
            reading_date=sunday,
            reading_type=reading_type,
            reference=reference,
        )
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            # Another concurrent request already cached this reading type
            # for this Sunday - back off and use its row instead of ours.
            db.rollback()
            existing = (
                db.query(LectionaryReadingCache)
                .filter(
                    LectionaryReadingCache.reading_date == sunday,
                    LectionaryReadingCache.reading_type == reading_type,
                )
                .first()
            )
            if existing:
                reference = existing.reference

        results[reading_type] = {"reference": reference}

    return results
