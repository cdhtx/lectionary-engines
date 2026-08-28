"""
Signals: detects thematic overlap among this week's four lectionary
readings (not readings vs. past studies - Study has no persisted theme
data, and this piece is scoped to what works from day one - see the
design spec for the full reasoning).

Reuses lectionary_widget_service.get_this_week_readings() for this
week's references, extracts theme keywords per reading (cached by
Sunday date, mirroring LectionaryReadingCache's pattern via a separate
LectionaryThemeCache table), and finds pairs that share at least one
theme (exact, case-insensitive match - no stemming or semantic
matching).
"""

import json
import logging
from datetime import date, timedelta
from itertools import combinations
from typing import List

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from lectionary_engines.claude_client import ClaudeClient
from lectionary_engines.text_fetcher import TextFetcher
from lectionary_engines.theme_extractor import extract_themes
from web.models import LectionaryThemeCache
from web.services.lectionary_widget_service import get_this_week_readings

logger = logging.getLogger(__name__)

READING_LABELS = {
    "gospel": "Gospel",
    "epistle": "Epistle",
    "ot": "Hebrew Scripture",
    "psalm": "Psalm",
}


def _upcoming_sunday(today: date) -> date:
    days_until_sunday = (6 - today.weekday()) % 7  # Monday=0 ... Sunday=6
    return today + timedelta(days=days_until_sunday)


def _get_themes_for_reading(
    db: Session, claude: ClaudeClient, sunday: date, reading_type: str, reference: str
) -> List[str]:
    cached = (
        db.query(LectionaryThemeCache)
        .filter(
            LectionaryThemeCache.reading_date == sunday,
            LectionaryThemeCache.reading_type == reading_type,
        )
        .first()
    )
    if cached:
        return json.loads(cached.themes)

    try:
        fetcher = TextFetcher()
        text = fetcher.fetch(reference)
        themes = extract_themes(claude, reference, text)
    except Exception as e:
        logger.warning(f"Failed to extract themes for '{reference}' ({reading_type}): {e}")
        themes = []

    row = LectionaryThemeCache(
        reading_date=sunday,
        reading_type=reading_type,
        themes=json.dumps(themes),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        # Another concurrent request already cached this reading type
        # for this Sunday - back off and use its row instead of ours.
        db.rollback()
        existing = (
            db.query(LectionaryThemeCache)
            .filter(
                LectionaryThemeCache.reading_date == sunday,
                LectionaryThemeCache.reading_type == reading_type,
            )
            .first()
        )
        if existing:
            themes = json.loads(existing.themes)

    return themes


def get_this_week_signals(db: Session, claude: ClaudeClient) -> list:
    """
    Returns a list of connection dicts, sorted by shared-theme count
    descending: [{"reading_a_type", "reading_a_label", "reading_a_reference",
    "reading_b_type", "reading_b_label", "reading_b_reference",
    "shared_themes"}, ...]. Empty list if fewer than 2 readings end up
    with a non-empty theme list, or no pair shares a theme.
    """
    this_week = get_this_week_readings(db)
    sunday = _upcoming_sunday(date.today())

    themes_by_type = {}
    for reading_type, reading in this_week.items():
        themes = _get_themes_for_reading(db, claude, sunday, reading_type, reading["reference"])
        if themes:
            themes_by_type[reading_type] = {
                "reference": reading["reference"],
                "themes": set(t.lower() for t in themes),
            }

    connections = []
    for type_a, type_b in combinations(themes_by_type.keys(), 2):
        shared = themes_by_type[type_a]["themes"] & themes_by_type[type_b]["themes"]
        if shared:
            connections.append({
                "reading_a_type": type_a,
                "reading_a_label": READING_LABELS[type_a],
                "reading_a_reference": themes_by_type[type_a]["reference"],
                "reading_b_type": type_b,
                "reading_b_label": READING_LABELS[type_b],
                "reading_b_reference": themes_by_type[type_b]["reference"],
                "shared_themes": sorted(t.title() for t in shared),
            })

    connections.sort(key=lambda c: len(c["shared_themes"]), reverse=True)
    return connections
