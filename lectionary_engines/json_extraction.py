"""
Pulls a JSON value out of an LLM response that's supposed to be JSON-only
but sometimes isn't - wrapped in markdown code fences, or followed by
trailing prose the model added despite being told not to (observed live:
Haiku returning `{"index": 7}` followed by an explanation it wasn't asked
for, which a naive fence-stripping regex fails to parse since the string
no longer ends with a clean closing fence).

Used anywhere a lightweight Claude call is expected to return structured
JSON (theme extraction, headline selection).
"""

import json
from typing import Any, Optional


def extract_first_json(text: str) -> Optional[Any]:
    """
    Parse the first complete JSON value (object or array) found in text.

    Handles clean JSON, JSON wrapped in ``` / ```json fences, and JSON
    followed by trailing prose - by locating the first `{` or `[` and
    decoding exactly one JSON value from there, ignoring everything before
    and after it.

    Returns None if no valid JSON value could be extracted.
    """
    if not text:
        return None

    candidates = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not candidates:
        return None
    start = min(candidates)

    try:
        value, _ = json.JSONDecoder().raw_decode(text, start)
        return value
    except (json.JSONDecodeError, ValueError):
        return None
