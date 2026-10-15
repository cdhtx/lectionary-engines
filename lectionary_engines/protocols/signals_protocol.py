"""
Signals protocol - prompt and output validation for cross-canon signals.

A signal is a theme that runs through Scripture, connected to where it
shows up in the world now, plus books worth chasing down. The model must
ground the contemporary example and every book in web search results.
"""

import json
from typing import Dict, List

CATEGORIES = ("world", "art", "culture", "news", "religion", "science")

REQUIRED_TEXT_FIELDS = (
    "title",
    "theme",
    "signal_detected",
    "connection",
    "nature_of_connection",
    "intratextual",
    "modern_illustration",
)

DIG_DEEPER_FIELDS = ("title", "author", "kind", "why")

SYSTEM_PROMPT = """You write "signals" for a biblical interpretation app used by thoughtful readers of Scripture.

A signal is a pattern running through the biblical text that most readers have not noticed, connected to where it shows up in the world right now. The reader should think: I have never seen that before.

Each signal has these parts:
- title: a short, specific title.
- theme: two to five words naming the pattern, used later to avoid repeats.
- signal_detected: the pattern, stated plainly, in two or three sentences.
- connection: what it connects to. Name the passages, figures, or ideas linked, with references.
- nature_of_connection: how they are connected (echo, inversion, reversal, fulfillment, tension, shared image, and so on) and why the link is easy to miss.
- intratextual: where else the pattern recurs inside the biblical text itself, with specific references.
- modern_illustration: where this is visible now, in the world, art, culture, news, religion, or science. Describe one concrete, real example and say how it echoes the pattern.
- modern_illustration_category: exactly one of world, art, culture, news, religion, science.
- dig_deeper: three to five books or works the reader can chase down, mixing fiction, nonfiction, and literature. Each has title, author, kind (fiction, nonfiction, or literature), and why (one sentence on why it is worth reading).

Rules:
- Prefer a connection a thoughtful reader would not expect. Reject the obvious one.
- Use web search. The modern illustration and every book must come from search results you actually saw. Never name a book, author, event, or work you could not confirm exists.
- If you cannot find a verifiable modern illustration and at least two verifiable books, return {"error": "reason"} and nothing else.
- Write plainly and concretely. Do not use em dashes. Avoid hype and filler.
- Return one JSON object and nothing else. No text before or after it."""


class SignalParseError(Exception):
    """The model's response was not a usable signal."""


def build_user_prompt(recent: List[Dict[str, str]]) -> str:
    """Prompt for the next signal. `recent` is a list of {"title", "theme"} dicts."""
    prompt = "Find and write the next signal."
    if recent:
        lines = "\n".join(f"- {r['theme']} ({r['title']})" for r in recent)
        prompt += (
            "\n\nAvoid these themes and anything close to them, because they were already used:\n"
            + lines
        )
    return prompt


def _nonblank(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def parse_signal(text: str) -> Dict:
    """Extract and validate the signal JSON from the model's response text."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise SignalParseError("no JSON object in response")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as e:
        raise SignalParseError(f"invalid JSON: {e}")
    if not isinstance(data, dict):
        raise SignalParseError("response JSON is not an object")
    if "error" in data and not data.get("title"):
        raise SignalParseError(f"model returned no signal: {data['error']}")

    for field in REQUIRED_TEXT_FIELDS:
        if not _nonblank(data.get(field)):
            raise SignalParseError(f"missing or blank field: {field}")
    if data.get("modern_illustration_category") not in CATEGORIES:
        raise SignalParseError("modern_illustration_category is not one of the allowed values")

    dig = data.get("dig_deeper")
    if not isinstance(dig, list) or len(dig) < 2:
        raise SignalParseError("dig_deeper needs at least two entries")
    for entry in dig:
        if not isinstance(entry, dict) or not all(_nonblank(entry.get(f)) for f in DIG_DEEPER_FIELDS):
            raise SignalParseError("dig_deeper entry is missing title, author, kind, or why")

    cleaned = {f: data[f].strip() for f in REQUIRED_TEXT_FIELDS}
    cleaned["modern_illustration_category"] = data["modern_illustration_category"]
    cleaned["dig_deeper"] = [{f: e[f].strip() for f in DIG_DEEPER_FIELDS} for e in dig]
    return cleaned
