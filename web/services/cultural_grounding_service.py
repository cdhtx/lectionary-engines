"""
Cultural Grounding Service

Orchestrates real grounding for study generation, given a passage's
extracted themes: pop-culture artifacts (Wikipedia/TMDB) across both the
classic (1977-1999) and contemporary eras, plus cross-disciplinary
reference material (etymology, biography, travel, art, literature) via
general Wikipedia topic search. Formats the combined results into an
injectable system-prompt block.

Kept separate from web/routes/resonance.py's own ResonanceEngine instance -
that one is driven by a user-typed theme list on the standalone Resonance
page; this one is driven by themes extracted automatically during study
generation, and doesn't need a Claude client of its own (find_resonances()
and search_topics() are pure adapter lookups - no synthesis call here).

Themes are passed in rather than extracted here, since callers that also
need themes for another purpose (auto news headline matching) should
extract once and reuse the same list - not pay for a second Haiku call.
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lectionary_engines.cultural.base_adapter import CulturalArtifact
from lectionary_engines.cultural.resonance_engine import ResonanceEngine
from lectionary_engines.cultural.wikipedia_adapter import WikipediaAdapter
from lectionary_engines.protocols.cultural_grounding import build_grounding_block

CLASSIC_ERA_START = 1977
CLASSIC_ERA_END = 1999
CONTEMPORARY_YEARS_BACK = 15
ARTIFACTS_PER_SOURCE = 6
CROSS_DISCIPLINARY_LIMIT_PER_CATEGORY = 3

_resonance_engine: Optional[ResonanceEngine] = None


def get_resonance_engine(tmdb_api_key: Optional[str] = None) -> ResonanceEngine:
    """Singleton ResonanceEngine for grounding lookups (no Claude client needed)."""
    global _resonance_engine
    if _resonance_engine is None:
        _resonance_engine = ResonanceEngine(
            config={"api_key": tmdb_api_key} if tmdb_api_key else {}
        )
    return _resonance_engine


def _get_wikipedia_adapter(engine: ResonanceEngine) -> Optional[WikipediaAdapter]:
    """Reuse the ResonanceEngine's own WikipediaAdapter instance rather than
    constructing a second one - search_topics() needs no config beyond
    what that instance already has."""
    for adapter in engine.adapters:
        if isinstance(adapter, WikipediaAdapter):
            return adapter
    return None


async def build_grounding_for_passage(
    themes: List[str],
    tmdb_api_key: Optional[str] = None,
) -> str:
    """
    Ground extracted passage themes in real material.

    Args:
        themes: Pre-extracted theme keywords (see theme_extractor.py)
        tmdb_api_key: Optional TMDB API key override

    Returns:
        A markdown block to append to an engine's system prompt, or an
        empty string if no themes were given or nothing was found anywhere.
        Never raises - this is a supporting lookup and study generation
        should never be blocked by it failing.
    """
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
    cross_disciplinary = await _safe_search_topics(engine, themes)

    return build_grounding_block(classic_artifacts, contemporary_artifacts, cross_disciplinary)


async def _safe_find_resonances(
    engine: ResonanceEngine, themes: List[str], year_start: int, year_end: int
) -> List[CulturalArtifact]:
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


async def _safe_search_topics(
    engine: ResonanceEngine, themes: List[str]
) -> Dict[str, List[CulturalArtifact]]:
    """Same defense-in-depth as _safe_find_resonances, for the cross-disciplinary lookup."""
    wiki = _get_wikipedia_adapter(engine)
    if wiki is None:
        return {}
    try:
        return await wiki.search_topics(themes, limit_per_category=CROSS_DISCIPLINARY_LIMIT_PER_CATEGORY)
    except Exception:
        return {}
