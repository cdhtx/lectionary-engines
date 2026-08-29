#!/usr/bin/env python3
"""
One-time backfill: populates content_theme for existing Study/
WorkshopPrep/CurrentsAnalysis/CulturalResonance rows created before
Tier 4 shipped.

CulturalResonance rows already have their themes in the existing
`themes` JSON column - backfilled by parsing that, no new Claude calls.
The other three types have no persisted themes yet - backfilled by
calling extract_themes() against their content, the same cheap Haiku
call generation now makes automatically for new rows.

Idempotent: skips any (content_type, content_id) that already has
content_theme rows, so it's safe to re-run.

Run: python3 web/scripts/backfill_content_themes.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lectionary_engines.claude_client import ClaudeClient
from lectionary_engines.theme_extractor import extract_themes
from web.config import WebConfig
from web.database import SessionLocal
from web.models import ContentTheme
from web.models import CulturalResonance, CurrentsAnalysis, Study, WorkshopPrep
from web.services.library_service import record_content_themes


def _already_backfilled(db, content_type: str, content_id: int) -> bool:
    return (
        db.query(ContentTheme)
        .filter(ContentTheme.content_type == content_type, ContentTheme.content_id == content_id)
        .first()
        is not None
    )


def backfill_resonance(db) -> int:
    """No Claude calls - CulturalResonance.themes already has the data."""
    count = 0
    for resonance in db.query(CulturalResonance).all():
        if _already_backfilled(db, "resonance", resonance.id):
            continue
        raw_themes = json.loads(resonance.themes) if resonance.themes else []
        themes = [str(t) for t in raw_themes if isinstance(t, (str, int, float))]
        if themes:
            record_content_themes(db, "resonance", resonance.id, themes)
            count += 1
    db.commit()
    return count


def backfill_study(db, claude: ClaudeClient) -> int:
    count = 0
    for study in db.query(Study).all():
        if _already_backfilled(db, "study", study.id):
            continue
        themes = extract_themes(claude, study.reference, study.content)
        if themes:
            record_content_themes(db, "study", study.id, themes)
            db.commit()
            count += 1
    return count


def backfill_workshop(db, claude: ClaudeClient) -> int:
    count = 0
    for prep in db.query(WorkshopPrep).all():
        if _already_backfilled(db, "workshop", prep.id):
            continue
        themes = extract_themes(claude, prep.reference, prep.content)
        if themes:
            record_content_themes(db, "workshop", prep.id, themes)
            db.commit()
            count += 1
    return count


def backfill_currents(db, claude: ClaudeClient) -> int:
    count = 0
    for analysis in db.query(CurrentsAnalysis).all():
        if _already_backfilled(db, "currents", analysis.id):
            continue
        reference = analysis.headline_summary or "Current Event"
        text = analysis.story_context or analysis.content
        themes = extract_themes(claude, reference, text)
        if themes:
            record_content_themes(db, "currents", analysis.id, themes)
            db.commit()
            count += 1
    return count


def main():
    config = WebConfig.load()
    claude = ClaudeClient(config.anthropic_api_key)
    db = SessionLocal()

    try:
        resonance_count = backfill_resonance(db)
        print(f"Resonance: backfilled {resonance_count} rows (no Claude calls)")

        study_count = backfill_study(db, claude)
        print(f"Study: backfilled {study_count} rows")

        workshop_count = backfill_workshop(db, claude)
        print(f"WorkshopPrep: backfilled {workshop_count} rows")

        currents_count = backfill_currents(db, claude)
        print(f"CurrentsAnalysis: backfilled {currents_count} rows")
    finally:
        db.close()


if __name__ == "__main__":
    main()
