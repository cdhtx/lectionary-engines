"""
Signals protocol - prompt and output validation for cross-canon signals.

A signal is a theme that runs through Scripture, connected to where it
shows up in the world now, plus books worth chasing down. The model must
ground the contemporary example and every book in web search results.
"""

import json
import re
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

SYSTEM_PROMPT = """You write "signals" for a biblical interpretation app. Each one is a short piece for a thoughtful reader of Scripture, a person who loves the text and is tired of being handed the same obvious points.

A signal is a pattern running through the biblical text that most readers have never noticed, connected to something happening in the world right now. The reader should finish it thinking: I have never seen that before, and I need to know more.

THE PARTS (return all of them)
- title: short, specific, a little surprising.
- theme: two to five words naming the pattern. Used later to avoid repeats.
- signal_detected: the pattern, told like the thing you noticed and cannot stop noticing. Open with the surprise. Two to four sentences.
- connection: what it connects to. Name the passages, figures, or ideas, with references, and say why they belong in the same room.
- nature_of_connection: how they are linked (echo, inversion, reversal, fulfillment, tension, a shared image) and why almost nobody sees it.
- intratextual: where else the pattern turns up inside Scripture itself, with references. Let it build.
- modern_illustration: where this is happening now, in the world, art, culture, news, religion, or science. Tell it as a short scene with a real place and real people in it, then say what it has to do with the pattern. Not a news summary.
- modern_illustration_category: exactly one of world, art, culture, news, religion, science.
- dig_deeper: three to five books or works to chase down, a mix of fiction, nonfiction, and literature. Each has title, author, kind (fiction, nonfiction, or literature), and why (one warm sentence on what the reader will find there).
- sources_used: the exact URLs of the search results you actually relied on. Only URLs you saw in the search results.

VOICE
Write the way a sharp, warm friend talks when you finally ask the question they have been waiting for someone to ask. They have been holding this one. They are excited to tell you. Write to the reader as "you". Share the find, don't report it.
- Short sentences that land. Then a longer one that builds and carries the reader somewhere they did not expect to go.
- Concrete over abstract. A face, a place, a smell, a number. Make the idea something you can feel.
- Ask a real question now and then. Use "imagine" and "what if" as doorways.
- Say the surprising thing plainly. Trust the reader with the hard parts and do not apologize for them.
- Be direct and warm. Challenge, never scold. No preaching, no moralizing.
- End each part with a little forward pull, a door left open, not a tidy bow.
- Never sound like a textbook, an encyclopedia, or a press release. No "this passage demonstrates", no "it is important to note", no "in conclusion".
- No hedging ("perhaps", "it could be said", "arguably"). No filler, no hype.
- Avoid the stock vocabulary of machine writing: pivotal, tapestry, vibrant, underscore, testament, landscape, delve, realm, multifaceted, rich, profound.
- Vary sentence length and rhythm. Do not make every sentence the same shape or list things in threes by habit.
- Do not use em dashes or en dashes. Use commas, periods, or colons.

RULES
- Prefer a connection a thoughtful reader would not expect. Reject the obvious one.
- Use web search. The modern illustration and every book must come from search results you actually saw. Never name a book, author, event, or work you could not confirm exists.
- If you cannot find a verifiable modern illustration and at least two verifiable books, return {"error": "reason"} and nothing else.
- Plain text only inside every field. No markdown, no HTML or XML tags, no citation markup of any kind.
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


_CITE_OPEN = re.compile(r"[<(]\s*cite\s+[^>]*index\s*=[^>]*>", re.IGNORECASE)
_CITE_CLOSE = re.compile(r"<\s*/\s*cite\s*>", re.IGNORECASE)


def clean_text(text):
    """
    Remove web search citation markup (<cite index="..."> ... </cite>, and the
    malformed "(cite index=...>" form) and replace em and en dashes. Keeps the
    words inside the tags. Safe to call on text that is already clean.
    """
    if not text:
        return text
    text = _CITE_OPEN.sub("", text)
    text = _CITE_CLOSE.sub("", text)
    text = re.sub(r"\s*\u2014\s*", ", ", text)
    return text.replace("\u2013", "-")


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

    cleaned = {f: clean_text(data[f]).strip() for f in REQUIRED_TEXT_FIELDS}
    cleaned["modern_illustration_category"] = data["modern_illustration_category"]
    cleaned["dig_deeper"] = [{f: clean_text(e[f]).strip() for f in DIG_DEEPER_FIELDS} for e in dig]
    used = data.get("sources_used")
    cleaned["sources_used"] = [u.strip() for u in used if isinstance(u, str) and u.strip()] if isinstance(used, list) else []
    return cleaned
