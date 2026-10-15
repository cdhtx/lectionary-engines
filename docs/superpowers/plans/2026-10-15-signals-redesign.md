# Signals Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the weekly keyword-overlap Signals with stored, researched cross-canon signals that are generated automatically every two days and shown three at a time with a way to explore more.

**Architecture:** A `Signal` table stores each signal. One generator function makes a single Claude call with the web search tool, validates the JSON it returns, and saves a row. An hourly asyncio loop started from the FastAPI lifespan asks the database whether the newest signal is 48+ hours old and generates one if so. `/signals` and the Today widget read from the database only.

**Tech Stack:** FastAPI, SQLAlchemy, Jinja2, Anthropic Python SDK 1.0.0 (`web_search_20250305` server tool), pytest.

**Spec:** `docs/superpowers/specs/2026-10-15-signals-redesign-design.md`

## Global Constraints

- Default model `claude-sonnet-5-5`, overridable with the `SIGNALS_MODEL` environment variable.
- `SIGNALS_ENABLED=false` turns the scheduled generation off. Any other value, or unset, means on.
- No Claude call and no network call happens while rendering a page. Pages read the database only.
- Web search tool is `web_search_20250305` (older variant; live test used about half the input tokens of `web_search_20260209`).
- `max_tokens=16000` for generation, `stop_reason == "max_tokens"` is a failure and saves nothing.
- A signal is due when the newest `Signal.created_at` is 48 hours old or more, or no signal exists. Timestamps are naive UTC (`datetime.utcnow`), matching the other models.
- `/signals` shows 3 signals at a time. "Explore more" adds 3 more per click. Hard cap of 60 shown.
- No em dashes in the generation prompt or in any user-facing copy (house style).
- Tests make no real network or Claude API call.
- Keep `extract_themes`, `lectionary_engines/liturgical_calendar.py` and `lectionary_widget_service`. Other features use them.
- The old `lectionary_theme_cache` table is left in the database. Only the ORM model is removed.

## Review Focus

- The model wraps its JSON in prose or code fences: parsing must still find the object.
- Web search returns an error object instead of a result list: sources must not crash and must count as no sources.
- The response is cut off (`max_tokens`) or paused (`pause_turn`): nothing is saved.
- Two hourly checks overlap: only one signal is generated.
- `/signals?n=abc`, `?n=-5`, `?n=9999`: no error page, value is clamped to 3-60.
- Signal text containing `<script>`: it must render escaped.
- No signals yet: `/signals` and the Today widget show an empty state, not an error.
- Fresh deploy with an empty table: the first check generates one signal right away (intended, costs one generation).

---

## File Structure

- Create `lectionary_engines/protocols/signals_protocol.py`: prompt text, `build_user_prompt`, `parse_signal`, `SignalParseError`.
- Create `web/services/signal_generator.py`: `generate_signal`.
- Create `web/services/signals_scheduler.py`: `signals_enabled`, `signal_is_due`, `run_if_due`, `signals_loop`.
- Create `web/scripts/generate_signal.py`: run one generation by hand.
- Modify `web/models.py`: add `Signal`, remove `LectionaryThemeCache`.
- Modify `web/app.py`: start/stop the loop in `lifespan`, home route reads `Signal`.
- Modify `web/routes/signals.py`, `web/templates/signals.html`, `web/templates/index.html`, `web/static/css/styles.css`.
- Delete `web/services/signals_service.py`, `tests/test_signals_service.py`.
- Modify `tests/conftest.py`, `tests/test_route_smoke.py`.
- Create tests: `tests/test_signal_model.py`, `tests/test_signals_protocol.py`, `tests/test_signal_generator.py`, `tests/test_signals_scheduler.py`, `tests/test_signals_pages.py`.

---

### Task 1: Signal model

**Files:**
- Modify: `web/models.py` (add class after `LectionaryThemeCache`, which Task 5 removes)
- Test: `tests/test_signal_model.py`

**Interfaces:**
- Produces: `web.models.Signal` with columns `id, created_at, title, theme, signal_detected, connection, nature_of_connection, intratextual, modern_illustration, modern_illustration_category, dig_deeper (JSON text), sources (JSON text), model, input_tokens, output_tokens, search_count` and properties `dig_deeper_list -> list[dict]`, `sources_list -> list[dict]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_signal_model.py
import json
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from web.models import Base, Signal


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_signal_round_trips_json_fields_and_defaults_created_at():
    db = _db()
    db.add(Signal(
        title="The Unfinished Meal",
        theme="hospitality",
        signal_detected="s",
        connection="c",
        nature_of_connection="n",
        intratextual="i",
        modern_illustration="m",
        modern_illustration_category="culture",
        dig_deeper=json.dumps([{"title": "Gilead", "author": "M. Robinson", "kind": "fiction", "why": "w"}]),
        sources=json.dumps([{"title": "T", "url": "https://example.com"}]),
        model="claude-sonnet-5-5",
        input_tokens=10, output_tokens=20, search_count=2,
    ))
    db.commit()

    row = db.query(Signal).one()
    assert isinstance(row.created_at, datetime)
    assert row.dig_deeper_list[0]["title"] == "Gilead"
    assert row.sources_list[0]["url"] == "https://example.com"


def test_signal_json_properties_tolerate_empty_or_bad_json():
    s = Signal(title="t", theme="x", signal_detected="s", connection="c",
               nature_of_connection="n", intratextual="i", modern_illustration="m",
               modern_illustration_category="art", dig_deeper="not json", sources=None)
    assert s.dig_deeper_list == []
    assert s.sources_list == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source venv/bin/activate && pytest tests/test_signal_model.py -v`
Expected: FAIL with `ImportError: cannot import name 'Signal'`

- [ ] **Step 3: Write minimal implementation**

Add `import json` at the top of `web/models.py` (with the other imports), then add this class directly after `LectionaryThemeCache`:

```python
class Signal(Base):
    """
    A researched cross-canon signal: a theme that runs through Scripture,
    where it shows up in the world now, and books to chase down. Generated
    by web/services/signal_generator.py roughly every two days.
    """

    __tablename__ = "signals"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    title = Column(String(200), nullable=False)
    theme = Column(String(200), nullable=False)  # short label, fed back to the model to avoid repeats
    signal_detected = Column(Text, nullable=False)
    connection = Column(Text, nullable=False)
    nature_of_connection = Column(Text, nullable=False)
    intratextual = Column(Text, nullable=False)
    modern_illustration = Column(Text, nullable=False)
    modern_illustration_category = Column(String(30), nullable=False)
    dig_deeper = Column(Text, nullable=False, default="[]")  # JSON list of {title, author, kind, why}
    sources = Column(Text, nullable=False, default="[]")  # JSON list of {title, url}
    model = Column(String(80))
    input_tokens = Column(Integer)
    output_tokens = Column(Integer)
    search_count = Column(Integer)

    @staticmethod
    def _load_list(raw):
        try:
            value = json.loads(raw or "[]")
        except (TypeError, ValueError):
            return []
        return value if isinstance(value, list) else []

    @property
    def dig_deeper_list(self):
        return self._load_list(self.dig_deeper)

    @property
    def sources_list(self):
        return self._load_list(self.sources)

    def __repr__(self):
        return f"<Signal(id={self.id}, title='{self.title}')>"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_signal_model.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add web/models.py tests/test_signal_model.py
git commit -m "feat: add Signal model"
```

---

### Task 2: Signals protocol (prompt and output validation)

**Files:**
- Create: `lectionary_engines/protocols/signals_protocol.py`
- Test: `tests/test_signals_protocol.py`

**Interfaces:**
- Produces: `CATEGORIES: tuple[str, ...]`, `SYSTEM_PROMPT: str`, `build_user_prompt(recent: list[dict]) -> str` (each dict has `title` and `theme`), `parse_signal(text: str) -> dict` returning keys `title, theme, signal_detected, connection, nature_of_connection, intratextual, modern_illustration, modern_illustration_category, dig_deeper` (list of dicts with `title, author, kind, why`), and `class SignalParseError(Exception)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_signals_protocol.py
import json

import pytest

from lectionary_engines.protocols.signals_protocol import (
    SignalParseError,
    build_user_prompt,
    parse_signal,
)


def _valid():
    return {
        "title": "The Unfinished Meal",
        "theme": "hospitality",
        "signal_detected": "A pattern.",
        "connection": "Genesis 18 and Luke 24.",
        "nature_of_connection": "Inversion.",
        "intratextual": "Also Judges 19.",
        "modern_illustration": "A 2026 report on a refugee kitchen.",
        "modern_illustration_category": "news",
        "dig_deeper": [
            {"title": "Gilead", "author": "Marilynne Robinson", "kind": "fiction", "why": "Hospitality as grace."},
            {"title": "Making Room", "author": "Christine Pohl", "kind": "nonfiction", "why": "History of the practice."},
        ],
    }


def test_parse_accepts_valid_json():
    assert parse_signal(json.dumps(_valid()))["title"] == "The Unfinished Meal"


def test_parse_finds_json_inside_prose_and_code_fences():
    text = "Here is the signal:\n```json\n" + json.dumps(_valid()) + "\n```\nHope that helps."
    assert parse_signal(text)["theme"] == "hospitality"


@pytest.mark.parametrize("field", [
    "title", "theme", "signal_detected", "connection",
    "nature_of_connection", "intratextual", "modern_illustration",
])
def test_parse_rejects_missing_or_blank_text_field(field):
    data = _valid()
    data[field] = "  "
    with pytest.raises(SignalParseError):
        parse_signal(json.dumps(data))


def test_parse_rejects_unknown_category():
    data = _valid()
    data["modern_illustration_category"] = "sports"
    with pytest.raises(SignalParseError):
        parse_signal(json.dumps(data))


def test_parse_requires_two_complete_dig_deeper_entries():
    data = _valid()
    data["dig_deeper"] = data["dig_deeper"][:1]
    with pytest.raises(SignalParseError):
        parse_signal(json.dumps(data))
    data = _valid()
    del data["dig_deeper"][0]["author"]
    with pytest.raises(SignalParseError):
        parse_signal(json.dumps(data))


def test_parse_rejects_non_json_and_error_object():
    with pytest.raises(SignalParseError):
        parse_signal("I could not find anything.")
    with pytest.raises(SignalParseError):
        parse_signal(json.dumps({"error": "no verifiable example found"}))


def test_user_prompt_lists_recent_themes_to_avoid():
    prompt = build_user_prompt([{"title": "Old One", "theme": "exile"}])
    assert "exile" in prompt and "Old One" in prompt


def test_user_prompt_without_history_has_no_avoid_list():
    assert "Avoid" not in build_user_prompt([])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_signals_protocol.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lectionary_engines.protocols.signals_protocol'`

- [ ] **Step 3: Write minimal implementation**

```python
# lectionary_engines/protocols/signals_protocol.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_signals_protocol.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add lectionary_engines/protocols/signals_protocol.py tests/test_signals_protocol.py
git commit -m "feat: add signals protocol prompt and parser"
```

---

### Task 3: Signal generator

**Files:**
- Create: `web/services/signal_generator.py`
- Test: `tests/test_signal_generator.py`

**Interfaces:**
- Consumes: `Signal` (Task 1); `SYSTEM_PROMPT`, `build_user_prompt`, `parse_signal`, `SignalParseError` (Task 2).
- Produces: `generate_signal(db: Session, client, model: str | None = None) -> Signal | None`, where `client` is an `anthropic.Anthropic` instance. Also constants `DEFAULT_SIGNALS_MODEL = "claude-sonnet-5-5"`, `MAX_ATTEMPTS = 2`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_signal_generator.py
import json
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from web.models import Base, Signal
from web.services.signal_generator import DEFAULT_SIGNALS_MODEL, generate_signal


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _valid_json(theme="hospitality"):
    return json.dumps({
        "title": "The Unfinished Meal",
        "theme": theme,
        "signal_detected": "A pattern.",
        "connection": "Genesis 18 and Luke 24.",
        "nature_of_connection": "Inversion.",
        "intratextual": "Also Judges 19.",
        "modern_illustration": "A report on a refugee kitchen.",
        "modern_illustration_category": "news",
        "dig_deeper": [
            {"title": "Gilead", "author": "Marilynne Robinson", "kind": "fiction", "why": "Grace."},
            {"title": "Making Room", "author": "Christine Pohl", "kind": "nonfiction", "why": "History."},
        ],
    })


def _response(text, results=None, stop_reason="end_turn", search_requests=1):
    results = results if results is not None else [NS(type="web_search_result", title="Src", url="https://example.com/a")]
    return NS(
        content=[
            NS(type="web_search_tool_result", content=results),
            NS(type="text", text=text),
        ],
        stop_reason=stop_reason,
        usage=NS(input_tokens=1000, output_tokens=500, server_tool_use=NS(web_search_requests=search_requests)),
    )


class FakeClient:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def test_saves_valid_signal_with_sources_and_usage(db):
    client = FakeClient(_response(_valid_json()))
    signal = generate_signal(db, client)

    assert signal is not None
    row = db.query(Signal).one()
    assert row.title == "The Unfinished Meal"
    assert row.model == DEFAULT_SIGNALS_MODEL
    assert row.sources_list == [{"title": "Src", "url": "https://example.com/a"}]
    assert (row.input_tokens, row.output_tokens, row.search_count) == (1000, 500, 1)
    call = client.calls[0]
    assert call["model"] == DEFAULT_SIGNALS_MODEL
    assert call["max_tokens"] == 16000
    assert call["tools"][0]["type"] == "web_search_20250305"


def test_model_override_and_env(db, monkeypatch):
    monkeypatch.setenv("SIGNALS_MODEL", "claude-opus-5-5")
    client = FakeClient(_response(_valid_json()))
    generate_signal(db, client)
    assert client.calls[0]["model"] == "claude-opus-5-5"


def test_retries_once_after_bad_json_then_saves(db):
    client = FakeClient(_response("not json"), _response(_valid_json()))
    assert generate_signal(db, client) is not None
    assert len(client.calls) == 2
    assert db.query(Signal).count() == 1


def test_two_failures_save_nothing(db):
    client = FakeClient(_response("not json"), _response("still not json"))
    assert generate_signal(db, client) is None
    assert db.query(Signal).count() == 0


@pytest.mark.parametrize("stop_reason", ["max_tokens", "pause_turn"])
def test_truncated_or_paused_response_saves_nothing(db, stop_reason):
    client = FakeClient(
        _response(_valid_json(), stop_reason=stop_reason),
        _response(_valid_json(), stop_reason=stop_reason),
    )
    assert generate_signal(db, client) is None
    assert db.query(Signal).count() == 0


def test_no_sources_saves_nothing(db):
    client = FakeClient(_response(_valid_json(), results=[]), _response(_valid_json(), results=[]))
    assert generate_signal(db, client) is None


def test_search_error_object_counts_as_no_sources(db):
    error_obj = NS(type="web_search_tool_result_error", error_code="unavailable")
    client = FakeClient(_response(_valid_json(), results=error_obj), _response(_valid_json(), results=error_obj))
    assert generate_signal(db, client) is None


def test_recent_themes_are_sent_to_the_model(db):
    db.add(Signal(title="Old", theme="exile", signal_detected="s", connection="c",
                  nature_of_connection="n", intratextual="i", modern_illustration="m",
                  modern_illustration_category="art"))
    db.commit()
    client = FakeClient(_response(_valid_json("a new theme")))
    generate_signal(db, client)
    assert "exile" in client.calls[0]["messages"][0]["content"]


def test_api_error_returns_none_without_raising(db):
    import anthropic

    class Boom:
        messages = None

        def __init__(self):
            self.messages = self

        def create(self, **kwargs):
            raise anthropic.APIConnectionError(request=NS())

    assert generate_signal(db, Boom()) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_signal_generator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'web.services.signal_generator'`

- [ ] **Step 3: Write minimal implementation**

```python
# web/services/signal_generator.py
"""
Generates one cross-canon signal: a single Claude call with the web search
tool, validated and saved as a Signal row. Nothing is saved unless the
response is complete, parses, and cites at least one search source.
"""

import json
import logging
import os
from typing import List, Optional

import anthropic
from sqlalchemy.orm import Session

from lectionary_engines.protocols.signals_protocol import (
    SYSTEM_PROMPT,
    SignalParseError,
    build_user_prompt,
    parse_signal,
)
from web.models import Signal

logger = logging.getLogger(__name__)

DEFAULT_SIGNALS_MODEL = "claude-sonnet-5-5"
MAX_TOKENS = 16000  # thinking counts against this, so keep real headroom
MAX_ATTEMPTS = 2
RECENT_LIMIT = 30
SEARCH_MAX_USES = 8
MAX_SOURCES = 12

WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": SEARCH_MAX_USES}


def _collect_sources(response) -> List[dict]:
    """Unique {title, url} pairs from the response's web search results."""
    seen, sources = set(), []
    for block in response.content:
        if block.type != "web_search_tool_result":
            continue
        results = block.content
        if not isinstance(results, list):  # an error object, not a result list
            continue
        for r in results:
            url = getattr(r, "url", None)
            if url and url not in seen:
                seen.add(url)
                sources.append({"title": getattr(r, "title", "") or url, "url": url})
    return sources[:MAX_SOURCES]


def generate_signal(db: Session, client, model: Optional[str] = None) -> Optional[Signal]:
    """
    Generate and save one signal. `client` is an anthropic.Anthropic instance.
    Returns the saved Signal, or None if nothing usable was produced (the
    reason is logged and the next scheduled check will try again).
    """
    model = model or os.getenv("SIGNALS_MODEL") or DEFAULT_SIGNALS_MODEL
    recent = db.query(Signal).order_by(Signal.created_at.desc()).limit(RECENT_LIMIT).all()
    user_prompt = build_user_prompt([{"title": s.title, "theme": s.theme} for s in recent])

    input_tokens = output_tokens = searches = 0
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=[WEB_SEARCH_TOOL],
                messages=[{"role": "user", "content": user_prompt}],
            )
        except anthropic.APIError as e:
            logger.warning("Signal generation API error (attempt %s): %s", attempt, e)
            return None

        usage = response.usage
        input_tokens += usage.input_tokens or 0
        output_tokens += usage.output_tokens or 0
        tool_usage = getattr(usage, "server_tool_use", None)
        searches += getattr(tool_usage, "web_search_requests", 0) or 0

        if response.stop_reason != "end_turn":
            logger.warning("Signal generation attempt %s stopped with %s; discarding", attempt, response.stop_reason)
            continue

        sources = _collect_sources(response)
        if not sources:
            logger.warning("Signal generation attempt %s had no web search sources; discarding", attempt)
            continue

        text = "".join(b.text for b in response.content if b.type == "text")
        try:
            data = parse_signal(text)
        except SignalParseError as e:
            logger.warning("Signal generation attempt %s unusable: %s", attempt, e)
            continue

        signal = Signal(
            title=data["title"],
            theme=data["theme"],
            signal_detected=data["signal_detected"],
            connection=data["connection"],
            nature_of_connection=data["nature_of_connection"],
            intratextual=data["intratextual"],
            modern_illustration=data["modern_illustration"],
            modern_illustration_category=data["modern_illustration_category"],
            dig_deeper=json.dumps(data["dig_deeper"]),
            sources=json.dumps(sources),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            search_count=searches,
        )
        db.add(signal)
        db.commit()
        return signal

    logger.warning("Signal generation produced nothing usable after %s attempts", MAX_ATTEMPTS)
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_signal_generator.py -v`
Expected: PASS (all). If `test_api_error_returns_none_without_raising` fails constructing `APIConnectionError`, replace the raised exception with `anthropic.APIError("boom", request=NS(), body=None)`.

- [ ] **Step 5: Commit**

```bash
git add web/services/signal_generator.py tests/test_signal_generator.py
git commit -m "feat: add signal generator with web search"
```

---

### Task 4: Scheduler, lifespan hook, and manual run script

**Files:**
- Create: `web/services/signals_scheduler.py`, `web/scripts/generate_signal.py`
- Modify: `web/app.py` (`lifespan`, lines 36-56), `tests/conftest.py`
- Test: `tests/test_signals_scheduler.py`

**Interfaces:**
- Consumes: `Signal` (Task 1), `generate_signal` (Task 3).
- Produces: `signals_enabled() -> bool`, `signal_is_due(db, now=None) -> bool`, `run_if_due(session_factory=SessionLocal, client_factory=None) -> bool`, `async signals_loop(interval=CHECK_INTERVAL_SECONDS)`, constants `SIGNAL_INTERVAL = timedelta(hours=48)`, `CHECK_INTERVAL_SECONDS = 3600`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_signals_scheduler.py
import asyncio
import threading
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from web.models import Base, Signal
from web.services import signals_scheduler
from web.services.signals_scheduler import run_if_due, signal_is_due, signals_enabled, signals_loop

NOW = datetime(2026, 10, 15, 12, 0, 0)


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _add_signal(factory, age_hours):
    db = factory()
    db.add(Signal(title="t", theme="x", signal_detected="s", connection="c", nature_of_connection="n",
                  intratextual="i", modern_illustration="m", modern_illustration_category="art",
                  created_at=NOW - timedelta(hours=age_hours)))
    db.commit()
    db.close()


def test_due_when_no_signals(session_factory):
    db = session_factory()
    assert signal_is_due(db, now=NOW) is True


def test_not_due_at_47_hours(session_factory):
    _add_signal(session_factory, 47)
    assert signal_is_due(session_factory(), now=NOW) is False


def test_due_at_49_hours(session_factory):
    _add_signal(session_factory, 49)
    assert signal_is_due(session_factory(), now=NOW) is True


def test_newest_signal_is_what_counts(session_factory):
    _add_signal(session_factory, 100)
    _add_signal(session_factory, 1)
    assert signal_is_due(session_factory(), now=NOW) is False


def test_run_if_due_generates_when_due_and_skips_when_not(session_factory):
    with patch("web.services.signals_scheduler.generate_signal") as gen:
        gen.return_value = object()
        assert run_if_due(session_factory, client_factory=lambda: "client") is True
        assert gen.call_count == 1

    _add_signal(session_factory, 1)
    with patch("web.services.signals_scheduler.generate_signal") as gen:
        assert run_if_due(session_factory, client_factory=lambda: "client") is False
        gen.assert_not_called()


def test_run_if_due_returns_false_when_generation_fails(session_factory):
    with patch("web.services.signals_scheduler.generate_signal", return_value=None):
        assert run_if_due(session_factory, client_factory=lambda: "client") is False


def test_overlapping_checks_generate_only_once(session_factory):
    started = threading.Event()
    release = threading.Event()
    calls = []

    def slow_generate(db, client):
        calls.append(1)
        started.set()
        release.wait(timeout=5)
        return object()

    with patch("web.services.signals_scheduler.generate_signal", side_effect=slow_generate):
        t = threading.Thread(target=run_if_due, args=(session_factory, lambda: "c"))
        t.start()
        assert started.wait(timeout=5)
        second = run_if_due(session_factory, client_factory=lambda: "c")  # lock is held
        release.set()
        t.join(timeout=5)

    assert second is False
    assert len(calls) == 1


def test_signals_enabled_reads_env(monkeypatch):
    monkeypatch.delenv("SIGNALS_ENABLED", raising=False)
    assert signals_enabled() is True
    monkeypatch.setenv("SIGNALS_ENABLED", "false")
    assert signals_enabled() is False
    monkeypatch.setenv("SIGNALS_ENABLED", "TRUE")
    assert signals_enabled() is True


def test_loop_survives_a_failing_check_and_keeps_going():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return False

    async def fake_sleep(_):
        if len(calls) >= 2:
            raise asyncio.CancelledError()

    async def run():
        with patch("web.services.signals_scheduler.run_if_due", side_effect=flaky), \
             patch("web.services.signals_scheduler.asyncio.sleep", side_effect=fake_sleep):
            with pytest.raises(asyncio.CancelledError):
                await signals_loop(interval=0)

    asyncio.run(run())
    assert len(calls) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_signals_scheduler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'web.services.signals_scheduler'`

- [ ] **Step 3: Write minimal implementation**

```python
# web/services/signals_scheduler.py
"""
Keeps the Signals feed fresh: an hourly check inside the web process asks
the database whether the newest signal is 48+ hours old and generates one
if so. "Is a signal due" is answered from the database, so redeploys and
restarts lose nothing; the next check catches up.
"""

import asyncio
import logging
import os
import threading
from datetime import datetime, timedelta
from typing import Callable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from web.database import SessionLocal
from web.models import Signal
from web.services.signal_generator import generate_signal

logger = logging.getLogger(__name__)

SIGNAL_INTERVAL = timedelta(hours=48)
CHECK_INTERVAL_SECONDS = 3600

_generation_lock = threading.Lock()


def signals_enabled() -> bool:
    return os.getenv("SIGNALS_ENABLED", "true").lower() != "false"


def signal_is_due(db: Session, now: Optional[datetime] = None) -> bool:
    now = now or datetime.utcnow()
    newest = db.query(func.max(Signal.created_at)).scalar()
    return newest is None or now - newest >= SIGNAL_INTERVAL


def _default_client():
    from lectionary_engines.claude_client import ClaudeClient
    from web.config import WebConfig

    return ClaudeClient(WebConfig.load().anthropic_api_key).client


def run_if_due(session_factory=SessionLocal, client_factory: Optional[Callable] = None) -> bool:
    """
    Generate one signal if one is due. Returns True only if a new signal was
    saved. If another check is already generating, returns False immediately.
    """
    if not _generation_lock.acquire(blocking=False):
        return False
    try:
        db = session_factory()
        try:
            if not signal_is_due(db):
                return False
            client = (client_factory or _default_client)()
            return generate_signal(db, client) is not None
        finally:
            db.close()
    finally:
        _generation_lock.release()


async def signals_loop(interval: float = CHECK_INTERVAL_SECONDS):
    """Check for a due signal, then sleep. A failed check is logged, never raised."""
    while True:
        try:
            await run_in_threadpool(run_if_due)
        except Exception:
            logger.exception("Signals check failed")
        await asyncio.sleep(interval)
```

```python
# web/scripts/generate_signal.py
"""
Generate one signal right now, ignoring the two-day schedule.

Usage: python -m web.scripts.generate_signal
Prints the new signal, or says nothing usable was produced (see the log).
"""

import logging

from web.database import SessionLocal, init_db
from web.services.signal_generator import generate_signal
from web.services.signals_scheduler import _default_client


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    init_db()
    db = SessionLocal()
    try:
        signal = generate_signal(db, _default_client())
        if signal is None:
            print("No usable signal was produced. See the log above.")
            return 1
        print(f"\n{signal.title}  [{signal.modern_illustration_category}]  model={signal.model}")
        print(f"tokens in/out: {signal.input_tokens}/{signal.output_tokens}  searches: {signal.search_count}\n")
        print(f"Signal detected: {signal.signal_detected}\n")
        print(f"Connection: {signal.connection}\n")
        print(f"Nature of the connection: {signal.nature_of_connection}\n")
        print(f"Intratextual: {signal.intratextual}\n")
        print(f"Modern illustration: {signal.modern_illustration}\n")
        for b in signal.dig_deeper_list:
            print(f"  - {b['title']} by {b['author']} ({b['kind']}): {b['why']}")
        for s in signal.sources_list:
            print(f"  source: {s['title']} {s['url']}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
```

Edit `web/app.py`: add `import asyncio` and `import contextlib` near the other top imports, then replace the `lifespan` body so it reads:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan - startup and shutdown events
    """
    from .services.signals_scheduler import signals_enabled, signals_loop

    # Startup: Initialize database
    print("Starting Lectionary Engines Web Application...")
    init_db()
    print(f"API Key configured: {'✓' if config.anthropic_api_key else '✗'}")
    print(f"Default translation: {config.default_translation}")
    print(f"Default engine: {config.default_engine}")
    print(f"Server running at http://{config.web_host}:{config.web_port}")

    signals_task = asyncio.create_task(signals_loop()) if signals_enabled() else None

    yield

    # Shutdown: stop the signals loop, then close database connections
    print("Shutting down...")
    if signals_task:
        signals_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await signals_task
    close_db()
```

Add to `tests/conftest.py` (after the imports) so no test run can start the loop or spend money:

```python
@pytest.fixture(autouse=True)
def _signals_disabled(monkeypatch):
    monkeypatch.setenv("SIGNALS_ENABLED", "false")
```

Note: `test_signals_enabled_reads_env` sets the variable itself, so the autouse fixture does not interfere.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_signals_scheduler.py -v`
Expected: PASS. Then run `python -c "import web.app"` and expect no error. Clean up `test_not_due_at_47_hours_due_at_49` if the unused `other` line triggers a lint warning: delete the `other = ...` line and its comment.

- [ ] **Step 5: Commit**

```bash
git add web/services/signals_scheduler.py web/scripts/generate_signal.py web/app.py tests/conftest.py tests/test_signals_scheduler.py
git commit -m "feat: schedule signal generation every two days"
```

---

### Task 5: Signals pages, Today widget, and removal of the old code

**Files:**
- Modify: `web/routes/signals.py` (replace whole file), `web/templates/signals.html` (replace whole file), `web/templates/index.html:50-80` (Signals section), `web/app.py` (home route, imports), `web/static/css/styles.css:2661-2720`, `web/models.py` (remove `LectionaryThemeCache`), `tests/test_route_smoke.py`
- Delete: `web/services/signals_service.py`, `tests/test_signals_service.py`
- Test: `tests/test_signals_pages.py`

**Interfaces:**
- Consumes: `Signal` (Task 1).
- Produces: `GET /signals?n=<int>` (3 shown by default, step 3, max 60) and the Today widget showing the latest 3.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_signals_pages.py
import json
from datetime import datetime, timedelta

from web.models import Signal


def _signal(i, title=None, **overrides):
    fields = dict(
        title=title or f"Signal {i}",
        theme=f"theme {i}",
        signal_detected=f"detected {i}",
        connection=f"connection {i}",
        nature_of_connection=f"nature {i}",
        intratextual=f"intratextual {i}",
        modern_illustration=f"illustration {i}",
        modern_illustration_category="culture",
        dig_deeper=json.dumps([{"title": f"Book {i}", "author": "Author", "kind": "fiction", "why": "Because."}]),
        sources=json.dumps([{"title": "Source", "url": "https://example.com/s"}]),
        created_at=datetime(2026, 10, 1) + timedelta(days=i),
    )
    fields.update(overrides)
    return Signal(**fields)


def _seed(SessionLocal, count, **overrides):
    s = SessionLocal()
    for i in range(count):
        s.add(_signal(i, **overrides))
    s.commit()
    s.close()


def test_signals_page_empty_state(study_client):
    client, _ = study_client
    response = client.get("/signals")
    assert response.status_code == 200
    assert "first signal is on its way" in response.text


def test_signals_page_shows_three_newest_with_all_five_parts(study_client):
    client, SessionLocal = study_client
    _seed(SessionLocal, 5)

    body = client.get("/signals").text

    assert "Signal 4" in body and "Signal 3" in body and "Signal 2" in body
    assert "Signal 1" not in body and "Signal 0" not in body
    assert body.index("Signal 4") < body.index("Signal 3") < body.index("Signal 2")
    for label in ("Signal detected", "Connection", "Nature of the connection",
                  "Intratextual", "Modern illustration", "Dig deeper"):
        assert label in body
    assert "Book 4" in body
    assert "https://example.com/s" in body
    assert "/signals?n=6" in body  # explore more


def test_explore_more_reveals_next_three_and_hides_link_at_the_end(study_client):
    client, SessionLocal = study_client
    _seed(SessionLocal, 5)

    body = client.get("/signals?n=6").text
    assert "Signal 0" in body and "Signal 1" in body
    assert "Explore more" not in body


def test_exactly_three_signals_has_no_explore_more(study_client):
    client, SessionLocal = study_client
    _seed(SessionLocal, 3)
    assert "Explore more" not in client.get("/signals").text


def test_bad_n_values_are_clamped_not_errors(study_client):
    client, SessionLocal = study_client
    _seed(SessionLocal, 5)
    for value in ("abc", "-5", "0", "9999", ""):
        response = client.get(f"/signals?n={value}")
        assert response.status_code == 200, value
    assert "Signal 0" not in client.get("/signals?n=-5").text  # fell back to 3


def test_signal_text_is_escaped(study_client):
    client, SessionLocal = study_client
    s = SessionLocal()
    s.add(_signal(1, title="<script>alert(1)</script>"))
    s.commit()
    s.close()
    body = client.get("/signals").text
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body


def test_today_widget_shows_latest_three_and_links_to_all(study_client):
    client, SessionLocal = study_client
    _seed(SessionLocal, 5)

    body = client.get("/").text

    assert "Signal 4" in body and "Signal 2" in body
    assert "Signal 1" not in body
    assert 'href="/signals"' in body


def test_today_widget_empty_state(study_client):
    client, _ = study_client
    response = client.get("/")
    assert response.status_code == 200
    assert "first signal is on its way" in response.text


def test_pages_never_call_claude(study_client):
    from unittest.mock import patch

    client, SessionLocal = study_client
    _seed(SessionLocal, 1)
    with patch("web.services.signal_generator.generate_signal") as gen, \
         patch("lectionary_engines.claude_client.anthropic.Anthropic") as anth:
        client.get("/signals")
        client.get("/")
    gen.assert_not_called()
    anth.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_signals_pages.py -v`
Expected: FAIL (old page renders keyword signals, no "first signal is on its way")

- [ ] **Step 3: Write the implementation**

Replace `web/routes/signals.py` entirely:

```python
"""
Signals routes - the feed of researched cross-canon signals.
Read-only: signals are generated by the scheduler, never during a page view.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Signal

router = APIRouter()

WEB_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))

PAGE_SIZE = 3
MAX_SHOWN = 60


def _parse_shown(raw: str) -> int:
    """How many signals to show. Anything unparseable falls back to one page."""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return PAGE_SIZE
    return max(PAGE_SIZE, min(value, MAX_SHOWN))


@router.get("/signals")
def signals_page(request: Request, n: str = "", db: Session = Depends(get_db)):
    shown = _parse_shown(n)
    total = db.query(func.count(Signal.id)).scalar()
    signals = (
        db.query(Signal)
        .order_by(Signal.created_at.desc(), Signal.id.desc())
        .limit(shown)
        .all()
    )
    has_more = total > len(signals) and shown < MAX_SHOWN
    return templates.TemplateResponse("signals.html", {
        "request": request,
        "signals": signals,
        "has_more": has_more,
        "next_n": shown + PAGE_SIZE,
    })
```

Replace `web/templates/signals.html` entirely:

```html
{% extends "base.html" %}

{% block title %}Signals | Lectionary Engines{% endblock %}

{% block content %}
<div class="container">
    <div class="page-header">
        <h1>Signals</h1>
        <p>Patterns running through Scripture that you may not have noticed, and where they show up now.</p>
    </div>

    {% if signals %}
    <div class="signals-list">
        {% for signal in signals %}
        <article class="signal-card">
            <p class="signal-meta">{{ signal.created_at.strftime("%B %-d, %Y") }} &middot; {{ signal.modern_illustration_category|title }}</p>
            <h2 class="signal-title">{{ signal.title }}</h2>

            <div class="signal-part"><h3>Signal detected</h3><p>{{ signal.signal_detected }}</p></div>
            <div class="signal-part"><h3>Connection</h3><p>{{ signal.connection }}</p></div>
            <div class="signal-part"><h3>Nature of the connection</h3><p>{{ signal.nature_of_connection }}</p></div>
            <div class="signal-part"><h3>Intratextual</h3><p>{{ signal.intratextual }}</p></div>
            <div class="signal-part"><h3>Modern illustration</h3><p>{{ signal.modern_illustration }}</p></div>

            {% if signal.dig_deeper_list %}
            <div class="signal-part signal-dig">
                <h3>Dig deeper</h3>
                <ul>
                    {% for book in signal.dig_deeper_list %}
                    <li><strong>{{ book.title }}</strong> by {{ book.author }} <span class="signal-kind">({{ book.kind }})</span>. {{ book.why }}</li>
                    {% endfor %}
                </ul>
            </div>
            {% endif %}

            {% if signal.sources_list %}
            <p class="signal-sources">Sources:
                {% for source in signal.sources_list %}
                <a href="{{ source.url }}" target="_blank" rel="noopener noreferrer">{{ source.title }}</a>{% if not loop.last %}, {% endif %}
                {% endfor %}
            </p>
            {% endif %}
        </article>
        {% endfor %}
    </div>

    {% if has_more %}
    <div class="signals-more">
        <a href="/signals?n={{ next_n }}" class="btn btn-secondary">Explore more signals</a>
    </div>
    {% endif %}
    {% else %}
    <div class="empty-state">
        <h2>The first signal is on its way</h2>
        <p>A new signal is generated about every two days. Check back soon.</p>
    </div>
    {% endif %}
</div>
{% endblock %}
```

In `web/templates/index.html`, replace the Signals `<section>` (from `<section class="signals-section dashboard-panel">` through its closing `</section>`; the `{% else %}` empty-state block and the `{% endif %}` belong to it) with:

```html
            <section class="signals-section dashboard-panel">
                <h2><svg class="section-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"><path d="M12 2l1.8 7.2L21 11l-7.2 1.8L12 20l-1.8-7.2L3 11l7.2-1.8L12 2z"/></svg>Signals</h2>
                {% if signals %}
                <p class="section-subtitle">Latest patterns running through Scripture</p>
                <div class="signals-list">
                    {% for signal in signals %}
                    <div class="signal-card">
                        <p class="signal-meta">{{ signal.modern_illustration_category|title }}</p>
                        <h3 class="signal-title">{{ signal.title }}</h3>
                        <p>{{ signal.signal_detected }}</p>
                    </div>
                    {% endfor %}
                </div>
                <div class="section-footer">
                    <a href="/signals" class="btn btn-link">Explore all signals →</a>
                </div>
                {% else %}
                <div class="empty-state">
                    <p>The first signal is on its way.</p>
                </div>
                {% endif %}
            </section>
```

Open the file first and match the exact current start and end of that section so no neighbouring markup is lost.

In `web/app.py` `home()`: change `from .models import Base, Study, User` (line 24) to `from .models import Base, Signal, Study, User`; delete the lines `from lectionary_engines.claude_client import ClaudeClient`, `from .services.signals_service import get_this_week_signals`, `claude = ClaudeClient(config.anthropic_api_key)`; and replace the `signals = get_this_week_signals(...)` line with:

```python
    signals = db.query(Signal).order_by(Signal.created_at.desc(), Signal.id.desc()).limit(3).all()
```

In `web/static/css/styles.css`, delete the now-unused `.signal-pair`, `.signal-arrow` and `.signal-themes` rules (around lines 2700-2720) and add after `.signal-card`:

```css
.signal-meta {
    font-family: var(--font-body);
    font-size: 0.8rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--color-ink-muted);
    margin-bottom: var(--space-xs);
}

.signal-title {
    font-family: var(--font-editorial);
    font-size: 1.4rem;
    margin: 0 0 var(--space-md);
}

.signal-part {
    margin-bottom: var(--space-md);
}

.signal-part h3 {
    font-size: 0.8rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--color-ink-muted);
    margin: 0 0 var(--space-xs);
}

.signal-part p {
    margin: 0;
}

.signal-dig ul {
    margin: 0;
    padding-left: var(--space-lg);
}

.signal-kind {
    color: var(--color-ink-muted);
}

.signal-sources {
    font-size: 0.85rem;
    color: var(--color-ink-muted);
    margin: var(--space-md) 0 0;
}

.signals-more {
    text-align: center;
    margin: var(--space-lg) 0;
}

.signals-section .signal-title {
    font-size: 1.1rem;
    margin-bottom: var(--space-xs);
}
```

Remove `LectionaryThemeCache` from `web/models.py` (the whole class), then delete the old code and tests:

```bash
git rm web/services/signals_service.py tests/test_signals_service.py
```

Update `tests/test_route_smoke.py`. In each of these tests, delete the two decorators `@patch("web.services.signals_service.TextFetcher")` and `@patch("web.services.signals_service.extract_themes")`, remove the `mock_extract_themes` and `mock_signals_fetcher_class` parameters, and delete the lines that configure those two mocks (`mock_signals_fetcher_class.return_value.fetch.return_value = ...` and `mock_extract_themes.return_value/side_effect = ...`):
- `test_sidebar_links_to_engines`
- `test_today_homepage_shows_this_week_readings`
- `test_continue_your_studies_shows_progress_bar`
- `test_today_page_shows_quote_banner`

Example, `test_today_page_shows_quote_banner` becomes:

```python
@patch("web.services.lectionary_widget_service.TextFetcher")
def test_today_page_shows_quote_banner(mock_readings_fetcher_class, isolated_client):
    mock_readings_fetcher_class.return_value.fetch_sunday_lectionary_readings.return_value = {}

    response = isolated_client.get("/")
    assert "today-quote" in response.text
```

Delete `test_signals_page_renders` and `test_today_homepage_shows_signals_widget` from that file (replaced by `tests/test_signals_pages.py`). Keep `test_sidebar_links_to_signals`. Then:

```bash
grep -rn "signals_service\|LectionaryThemeCache\|get_this_week_signals" --include='*.py' --include='*.html' web tests lectionary_engines
```

Expected: no output other than a docstring mention in `lectionary_engines/liturgical_calendar.py` and `tests/test_liturgical_calendar.py` (leave those).

- [ ] **Step 4: Run the full suite**

Run: `pytest -q`
Expected: all pass. If `test_pages_never_call_claude` fails because the patch target does not exist, change `anthropic.Anthropic` patch to `patch("anthropic.Anthropic")`.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: show stored signals three at a time, remove keyword signals"
```

---

### Task 6: Live check and deploy

**Files:** none new (verification only).

- [ ] **Step 1: Generate one real signal locally and read it**

Run: `source venv/bin/activate && python -m web.scripts.generate_signal`
Expected: a signal prints with all five parts, 3-5 books, and sources. Read it. Check that each book and the modern example actually exist by opening two of the source links. Note the token counts and search count (this is the real cost per signal).

If it returns "No usable signal", read the log lines above it (they name the reason: no sources, bad JSON, truncated) and report them instead of changing code.

- [ ] **Step 2: Look at the pages**

Run: `uvicorn web.app:app --port 8000` with `SIGNALS_ENABLED=false`, open `/signals` and `/` with a logged-in session, and confirm three cards show, then "Explore more signals" appears only when more than three exist. Stop the server.

- [ ] **Step 3: Push and confirm the deploy**

```bash
git push
```

Then check the Railway deploy reaches SUCCESS (Railway MCP `list-deployments` for the `web` service). On first start with an empty table the loop generates one signal immediately; confirm a row appears by loading `/signals` after a minute or two.

- [ ] **Step 4: Report**

Tell the user the real tokens and searches per signal, the model used, and remind them to set a monthly spend limit in the Anthropic Console.
