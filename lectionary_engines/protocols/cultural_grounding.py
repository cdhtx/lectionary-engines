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

from typing import List

from ..cultural.base_adapter import CulturalArtifact


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


def build_grounding_block(
    classic_artifacts: List[CulturalArtifact],
    contemporary_artifacts: List[CulturalArtifact],
) -> str:
    """
    Build a system-prompt-appendable block listing real cultural artifacts.

    Args:
        classic_artifacts: Artifacts found for the 1977-1999 era
        contemporary_artifacts: Artifacts found for the contemporary era

    Returns:
        Markdown block to append to an engine's system prompt, or an empty
        string if no artifacts were found in either era (callers should
        skip appending it entirely in that case - the intensity-scaled
        instruction still applies on its own).
    """
    sections = [
        section
        for section in (
            _format_artifacts(classic_artifacts, "Classic era (1977-1999)"),
            _format_artifacts(contemporary_artifacts, "Contemporary"),
        )
        if section
    ]

    if not sections:
        return ""

    joined_sections = "\n\n".join(sections)

    return f"""

## REAL CULTURAL ARTIFACTS (grounded, verified)

The following are real, specific cultural artifacts retrieved from Wikipedia and TMDB based on this passage's themes — not invented from memory. When you include a cultural reference in this study, prefer pulling from this list over generating one from your own recall; these are verifiable and specific, and a reader could look each one up.

{joined_sections}

If none of these fit naturally, you may still draw on your own knowledge — but a real, specific artifact from this list beats a generic invented one every time.
"""
