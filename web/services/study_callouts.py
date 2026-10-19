"""
Turns labeled blockquotes in rendered study HTML into styled callouts.

Studies are asked (see lectionary_engines/protocols/format_protocol.py) to
write callouts as blockquotes that start with a bold label:

    > **Key insight:** the main point.

markdown renders that as <blockquote><p><strong>Key insight:</strong> ...
This adds a CSS class to the blockquote. It stays a blockquote, so older
studies, studies that ignore the format, and the PDF export all still work.
"""

import re

CALLOUT_CLASSES = {
    "key insight": "callout-insight",
    "core line": "callout-pull",
    "try this": "callout-practice",
    "sit with this": "callout-question",
}

_PATTERN = re.compile(
    r"<blockquote>(\s*<p>\s*<strong>\s*([^<:]{1,30}?)\s*:?\s*</strong>)",
    re.IGNORECASE,
)


def decorate_callouts(html: str) -> str:
    def _replace(match):
        css = CALLOUT_CLASSES.get(match.group(2).strip().rstrip(":").lower())
        if not css:
            return match.group(0)
        return f'<blockquote class="callout {css}">{match.group(1)}'

    return _PATTERN.sub(_replace, html)
