"""
Today homepage's "This Week in the Lectionary" widget: fetches and caches
one day's four RCL readings (Gospel, Epistle, Old Testament, Psalm).

fetch_rcl() makes a live, uncached HTTP scrape of Vanderbilt Divinity
Library's site per call - calling it 4x on every homepage load, with no
caching, would make the app's most-visited page depend on an external
site's uptime and latency. This module adds a day-granularity DB cache in
front of it (see web.models.LectionaryReadingCache).

A single reading type's fetch failure does not prevent the other three
from succeeding - the homepage shows a partial widget rather than none at
all, and never fails outright because of a Vanderbilt outage.
"""

import logging
from datetime import date
from typing import Dict

from sqlalchemy.orm import Session

from lectionary_engines.text_fetcher import TextFetcher
from web.models import LectionaryReadingCache

logger = logging.getLogger(__name__)

READING_TYPES = ["gospel", "epistle", "ot", "psalm"]


def get_this_week_readings(db: Session) -> Dict[str, dict]:
    """
    Returns a dict keyed by reading type ("gospel", "epistle", "ot",
    "psalm"). Each present key's value is {"reference": str, "text": str}.
    A key is absent if that reading type's fetch failed today and there
    was no cached row to fall back on.
    """
    today = date.today()
    results: Dict[str, dict] = {}
    fetcher = TextFetcher()

    for reading_type in READING_TYPES:
        cached = (
            db.query(LectionaryReadingCache)
            .filter(
                LectionaryReadingCache.reading_date == today,
                LectionaryReadingCache.reading_type == reading_type,
            )
            .first()
        )
        if cached:
            results[reading_type] = {"reference": cached.reference, "text": cached.text}
            continue

        try:
            reference, text = fetcher.fetch_rcl(reading_type)
        except Exception as e:
            logger.warning(f"Failed to fetch RCL reading '{reading_type}': {e}")
            continue

        row = LectionaryReadingCache(
            reading_date=today,
            reading_type=reading_type,
            reference=reference,
            text=text,
        )
        db.add(row)
        db.commit()

        results[reading_type] = {"reference": reference, "text": text}

    return results
