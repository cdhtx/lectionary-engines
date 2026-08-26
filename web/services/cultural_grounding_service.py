"""
Cultural Grounding Service

Orchestrates real cultural-artifact grounding for study generation:
extracts themes from a passage, queries ResonanceEngine (Wikipedia/TMDB)
for both the classic (1977-1999) and contemporary eras, and formats the
results into an injectable system-prompt block.

Kept separate from web/routes/resonance.py's own ResonanceEngine instance -
that one is driven by a user-typed theme list on the standalone Resonance
page; this one is driven by themes extracted automatically during study
generation, and doesn't need a Claude client of its own (find_resonances()
is pure adapter lookups - no synthesis call here).
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lectionary_engines.claude_client import ClaudeClient
from lectionary_engines.cultural.resonance_engine import ResonanceEngine
from lectionary_engines.theme_extractor import extract_themes
from lectionary_engines.protocols.cultural_grounding import build_grounding_block

CLASSIC_ERA_START = 1977
CLASSIC_ERA_END = 1999
CONTEMPORARY_YEARS_BACK = 15
ARTIFACTS_PER_SOURCE = 6

_resonance_engine: Optional[ResonanceEngine] = None


def get_resonance_engine(tmdb_api_key: Optional[str] = None) -> ResonanceEngine:
    """Singleton ResonanceEngine for grounding lookups (no Claude client needed)."""
    global _resonance_engine
    if _resonance_engine is None:
        _resonance_engine = ResonanceEngine(
            config={"api_key": tmdb_api_key} if tmdb_api_key else {}
        )
    return _resonance_engine


async def build_grounding_for_passage(
    claude: ClaudeClient,
    reference: str,
    text: str,
    tmdb_api_key: Optional[str] = None,
) -> str:
    """
    Extract themes from a passage and ground them in real cultural
    artifacts across both the classic and contemporary eras.

    Args:
        claude: ClaudeClient for the (cheap) theme-extraction call
        reference: Biblical reference
        text: Biblical text to extract themes from
        tmdb_api_key: Optional TMDB API key override

    Returns:
        A markdown block to append to an engine's system prompt, or an
        empty string if theme extraction or both era lookups turned up
        nothing. Never raises - this is a supporting lookup and study
        generation should never be blocked by it failing.
    """
    themes = extract_themes(claude, reference, text)
    if not themes:
        return ""

    engine = get_resonance_engine(tmdb_api_key)
    current_year = datetime.now().year

    classic_artifacts = await _safe_find_resonances(
        engine, themes, CLASSIC_ERA_START, CLASSIC_ERA_END
    )
    contemporary_artifacts = await _safe_find_resonances(
        engine, themes, current_year - CONTEMPORARY_YEARS_BACK, current_year
    )

    return build_grounding_block(classic_artifacts, contemporary_artifacts)


async def _safe_find_resonances(
    engine: ResonanceEngine, themes: List[str], year_start: int, year_end: int
):
    """
    find_resonances() already swallows per-adapter exceptions internally
    (asyncio.gather(..., return_exceptions=True)); this is defense in depth
    against anything unexpected at the call site itself.
    """
    try:
        return await engine.find_resonances(
            themes=themes,
            limit_per_source=ARTIFACTS_PER_SOURCE,
            year_start=year_start,
            year_end=year_end,
        )
    except Exception:
        return []
