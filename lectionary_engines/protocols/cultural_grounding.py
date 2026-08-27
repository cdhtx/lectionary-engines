"""
Cultural Grounding Injection

Real, API-sourced cultural artifacts (Wikipedia, TMDB - via ResonanceEngine)
get folded into an engine's system prompt as preferred material, instead of
leaving "cultural artifacts" entirely to Claude's own recall, which risks
confidently invented specifics that aren't real.

This supplements, not replaces, the intensity-scaled cultural-artifacts
instruction protocol_builder.py already injects from
UserProfile.cultural_artifacts_level - that instruction sets the density
and tone; this block gives Claude real, specific things to reach for first.
"""

from typing import Dict, List, Optional

from ..cultural.base_adapter import CulturalArtifact

# Human-readable labels for search_topics() category keys (see
# WikipediaAdapter.CROSS_DISCIPLINARY_QUERY_TEMPLATES), in display order.
CROSS_DISCIPLINARY_LABELS = {
    "etymology": "Etymology & Word Origins",
    "biography": "Biography",
    "travel": "Travel & Geography",
    "art": "Art",
    "literature": "Literature & Poetry",
}


def _format_artifacts(artifacts: List[CulturalArtifact], label: str) -> str:
    if not artifacts:
        return ""

    lines = [f"**{label}:**"]
    for artifact in artifacts[:8]:
        themes = ", ".join(artifact.themes[:4]) if artifact.themes else ""
        description = artifact.quote_or_description[:220].strip()
        line = f"- *{artifact.title}* ({artifact.year}, {artifact.creator})"
        if description:
            line += f" — {description}"
        if themes:
            line += f" [themes: {themes}]"
        lines.append(line)

    return "\n".join(lines)


def _format_cross_disciplinary(artifacts: List[CulturalArtifact], label: str) -> str:
    """
    Same shape as _format_artifacts(), but omits the year - these aren't
    era-bound the way pop culture is, so search_topics() doesn't set a
    meaningful one (see WikipediaAdapter.search_topics).
    """
    if not artifacts:
        return ""

    lines = [f"**{label}:**"]
    for artifact in artifacts[:6]:
        description = artifact.quote_or_description[:220].strip()
        line = f"- *{artifact.title}*"
        if description:
            line += f" — {description}"
        lines.append(line)

    return "\n".join(lines)


def build_grounding_block(
    classic_artifacts: List[CulturalArtifact],
    contemporary_artifacts: List[CulturalArtifact],
    cross_disciplinary: Optional[Dict[str, List[CulturalArtifact]]] = None,
) -> str:
    """
    Build a system-prompt-appendable block listing real cultural artifacts.

    Args:
        classic_artifacts: Artifacts found for the 1977-1999 era
        contemporary_artifacts: Artifacts found for the contemporary era
        cross_disciplinary: Optional dict from WikipediaAdapter.search_topics()
            - category key -> artifacts (etymology, biography, travel, art,
            literature). Not era-scoped.

    Returns:
        Markdown block to append to an engine's system prompt, or an empty
        string if nothing was found anywhere (callers should skip appending
        it entirely in that case - the intensity-scaled instruction still
        applies on its own).
    """
    pop_culture_sections = [
        section
        for section in (
            _format_artifacts(classic_artifacts, "Classic era (1977-1999)"),
            _format_artifacts(contemporary_artifacts, "Contemporary"),
        )
        if section
    ]

    cross_disciplinary_sections = []
    if cross_disciplinary:
        for category, label in CROSS_DISCIPLINARY_LABELS.items():
            formatted = _format_cross_disciplinary(cross_disciplinary.get(category, []), label)
            if formatted:
                cross_disciplinary_sections.append(formatted)

    all_sections = pop_culture_sections + cross_disciplinary_sections
    if not all_sections:
        return ""

    joined_sections = "\n\n".join(all_sections)

    return f"""

## REAL CULTURAL ARTIFACTS (grounded, verified)

The following are real, specific material retrieved from Wikipedia and TMDB based on this passage's themes — not invented from memory. When you include a cultural or cross-disciplinary reference in this study, prefer pulling from this list over generating one from your own recall; these are verifiable and specific, and a reader could look each one up.

Don't just namedrop an entry in passing. Pick at least one artifact from this list and actually develop it — a specific scene, lyric, biographical detail, word history, or literary passage, held alongside the text long enough to do real interpretive work, not a one-clause aside. A study that mentions five things briefly is weaker than one that wrestles with two of them closely.

{joined_sections}

If none of these fit naturally, you may still draw on your own knowledge — but a real, specific entry from this list beats a generic invented one every time.
"""
