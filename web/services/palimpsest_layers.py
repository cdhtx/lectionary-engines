"""
Parses a Palimpsest study's flat markdown content into its five named
PaRDeS layers (Peshat, Remez, Derash, Sod, Incarnation), so the study
view can render each as an addressable section for spatial navigation
(a scroll-tracking rail). See
docs/superpowers/specs/2026-08-28-tier-3-palimpsest-design.md.

Palimpsest studies are the only engine's content this parses; Threshold
and Collision keep rendering as flat scroll (see the design spec's
"Scope decisions" section for why).
"""

import re
from typing import List, Optional, TypedDict


class ParsedLayer(TypedDict):
    key: str
    markdown: str


class ParsedPalimpsest(TypedDict):
    intro_markdown: str
    layers: List[ParsedLayer]


LAYER_KEYWORDS = ["Peshat", "Remez", "Derash", "Sod", "Incarnation"]

RAIL_LABELS = [
    {"key": "peshat", "label": "Peshat · Simple/Literal"},
    {"key": "remez", "label": "Remez · Hint/Allegory"},
    {"key": "derash", "label": "Derash · Search/Interpretation"},
    {"key": "sod", "label": "Sod · Secret/Mystery"},
    {"key": "incarnation", "label": "Incarnation · Contemporary Body"},
]

_HEADING_PATTERN = re.compile(
    r"^##\s+.*?\b(" + "|".join(LAYER_KEYWORDS) + r")\b.*$",
    re.MULTILINE | re.IGNORECASE,
)


def parse_palimpsest_layers(content: str) -> Optional[ParsedPalimpsest]:
    """
    Splits a Palimpsest study's markdown into its five PaRDeS layers.

    Returns None (not an error - callers should fall back to rendering
    `content` unsplit, exactly as today) unless all five keywords are
    found as distinct `##` headings, in the canonical order, with no
    duplicates and no extras.
    """
    matches = list(_HEADING_PATTERN.finditer(content))

    found_keywords = [m.group(1).lower() for m in matches]
    if found_keywords != [kw.lower() for kw in LAYER_KEYWORDS]:
        return None

    intro_markdown = content[: matches[0].start()].strip()

    layers: List[ParsedLayer] = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        layers.append({
            "key": LAYER_KEYWORDS[i].lower(),
            "markdown": content[start:end].strip(),
        })

    return {"intro_markdown": intro_markdown, "layers": layers}
