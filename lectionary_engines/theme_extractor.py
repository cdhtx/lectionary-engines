"""
Theme Extraction

A cheap, structured pass that turns a biblical passage into a short list
of searchable theme keywords. This is the shared input for two features:

  - Cultural artifact grounding (resonance_grounding.py) - themes are
    passed to ResonanceEngine.find_resonances() to pull real artifacts.
  - Auto news integration (currents_service.py) - themes are used to pick
    the most relevant fetched headline.

Uses a fast/cheap model (same Haiku model as validation_protocol.py) since
this is a supporting lookup, not the study itself.
"""

from typing import List

from .claude_client import ClaudeClient
from .json_extraction import extract_first_json

MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """You extract searchable keywords from biblical passages, for downstream search - matching cultural artifacts (via literal movie-title and article-title search) and news headlines (via semantic comparison) to the text's themes.

Return ONLY a JSON array of 5-8 keywords, one to two words each ("healing", "betrayal", "outsider", "second chances", "public shame"). No preamble, no markdown code fences, no explanation.

These need to work as literal search terms against real movie titles and Wikipedia articles, not just as accurate descriptions - so favor concrete, common nouns and short phrases over abstract or wordy ones. "restoration" and "forgiveness" are searchable; "the challenge of unearned grace" is not. Include at least one keyword about a universal human experience the text touches (loss, shame, courage, waiting, belonging), not just its theological vocabulary - that's what makes it possible to find real-world resonances beyond religious media."""


def extract_themes(claude: ClaudeClient, reference: str, text: str) -> List[str]:
    """
    Extract 5-8 short, search-friendly keywords from a biblical passage.

    Args:
        claude: ClaudeClient instance to call
        reference: Biblical reference (for context only)
        text: Biblical text to extract themes from

    Returns:
        List of theme strings. Empty list on any failure - callers should
        treat that as "skip the feature that needed themes," not an error,
        since this is a supporting lookup and generation should never be
        blocked by it.
    """
    try:
        raw = claude.complete(
            system_prompt=SYSTEM_PROMPT,
            user_message=f"Reference: {reference}\n\nText:\n{text[:3000]}",
            model=MODEL,
            max_tokens=300,
            temperature=0.3,
        )
        themes = extract_first_json(raw)
        if not isinstance(themes, list):
            return []
        return [str(t).strip() for t in themes if str(t).strip()][:8]
    except Exception:
        return []
