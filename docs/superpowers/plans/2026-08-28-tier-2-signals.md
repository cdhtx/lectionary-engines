# Tier 2 — Signals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect thematic overlap among this week's four lectionary readings and surface it as "Signals" — a dedicated page plus a widget on the Today homepage.

**Architecture:** A new cache table + service extracts and caches theme keywords per reading (mirroring the Today homepage's `LectionaryReadingCache` pattern), then does a cheap in-Python pairwise comparison — no new external infrastructure. A new route/page and a Today homepage widget both consume the same service function.

**Tech Stack:** SQLAlchemy, FastAPI, Jinja2, pytest, the existing `lectionary_engines.theme_extractor.extract_themes()` and `lectionary_engines.text_fetcher.TextFetcher`.

## Global Constraints

- **Readings vs. readings only, not readings vs. studies.** No `Study.themes` column, no historical backfill. This piece only compares this week's own four readings against each other.
- **Overlap = exact, case-insensitive keyword match.** No stemming, no semantic/fuzzy matching.
- **`ClaudeClient` is instantiated by the route, not the service** — matching the existing pattern in `web/routes/workshop.py`/`web/routes/resonance.py` (`ClaudeClient(config.anthropic_api_key)`).
- **New table, not a new column.** `Base.metadata.create_all()` creates it automatically — no `COLUMN_MIGRATIONS` entry in `web/database.py`.
- **The existing test suite must stay green** (122 tests at branch point — confirm via `python3 -m pytest tests/ -v` before starting, don't assume the exact number if it's drifted).

---

### Task 1: Theme cache model and `get_this_week_signals()` service

**Files:**
- Modify: `web/models.py` (add `LectionaryThemeCache`)
- Create: `web/services/signals_service.py`
- Test: `tests/test_signals_service.py`

**Interfaces:**
- Consumes: `web.services.lectionary_widget_service.get_this_week_readings(db)` (existing, returns `{"gospel": {"reference": str}, ...}`, keys absent on failure); `lectionary_engines.text_fetcher.TextFetcher` (existing, `.fetch(reference: str) -> str`); `lectionary_engines.theme_extractor.extract_themes(claude, reference, text) -> List[str]` (existing, returns `[]` on failure); `lectionary_engines.claude_client.ClaudeClient` (existing).
- Produces: `web.models.LectionaryThemeCache` (new model); `get_this_week_signals(db: Session, claude: ClaudeClient) -> list[dict]` — each dict `{"reading_a_type": str, "reading_a_label": str, "reading_a_reference": str, "reading_b_type": str, "reading_b_label": str, "reading_b_reference": str, "shared_themes": list[str]}`, sorted by `len(shared_themes)` descending. Task 2 and Task 3 both consume this function and this exact return shape directly.

- [ ] **Step 1: Add the model**

In `web/models.py`, add this class at the end of the file (after `LectionaryReadingCache`):

```python
class LectionaryThemeCache(Base):
    """
    Caches each of the upcoming Sunday's four readings' extracted theme
    keywords, so Signals doesn't re-fetch full text and re-call Claude
    on every page load. Mirrors LectionaryReadingCache's day-granularity
    caching pattern.
    """

    __tablename__ = "lectionary_theme_cache"

    id = Column(Integer, primary_key=True)
    reading_date = Column(Date, nullable=False, index=True)
    reading_type = Column(String(20), nullable=False)  # "gospel", "ot", "psalm", "epistle"
    themes = Column(Text, nullable=False)  # JSON array of theme keyword strings
    fetched_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("reading_date", "reading_type", name="uq_theme_date_type"),
    )

    def __repr__(self):
        return f"<LectionaryThemeCache(reading_date='{self.reading_date}', reading_type='{self.reading_type}')>"
```

`Date`, `UniqueConstraint`, and `datetime` are already imported in `web/models.py` (added for `LectionaryReadingCache`) — no new imports needed for this step.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_signals_service.py`:

```python
"""
Tests for the Signals service: detects thematic overlap among this
week's four lectionary readings.

Two external dependencies are mocked in every test: TextFetcher (used
by both this service directly, for full-text fetching, and internally
by lectionary_widget_service.get_this_week_readings() for reference
fetching - two separate import bindings, both must be patched) and
extract_themes (the Claude call). No test in this file makes a real
network or Claude API call.
"""

from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from web.models import Base
from web.services.signals_service import get_this_week_signals


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


def _mock_readings_fetcher(mock_class):
    """Configures a mocked TextFetcher class for get_this_week_readings()'s
    internal fetch_sunday_lectionary_readings() call."""
    instance = mock_class.return_value
    instance.fetch_sunday_lectionary_readings.return_value = {
        "gospel": "Luke 14:1-14",
        "epistle": "Hebrews 13:1-8, 15-16",
        "ot": "Jeremiah 2:4-13",
        "psalm": "Psalm 81:1, 10-16",
    }
    return instance


@patch("web.services.lectionary_widget_service.TextFetcher")
@patch("web.services.signals_service.TextFetcher")
@patch("web.services.signals_service.extract_themes")
def test_two_readings_sharing_a_theme_produce_a_connection(
    mock_extract_themes, mock_signals_fetcher_class, mock_readings_fetcher_class, db
):
    _mock_readings_fetcher(mock_readings_fetcher_class)
    mock_signals_fetcher_class.return_value.fetch.return_value = "full passage text"

    def themes_by_reference(claude, reference, text):
        if reference == "Luke 14:1-14":
            return ["hospitality", "humility"]
        if reference == "Jeremiah 2:4-13":
            return ["unfaithfulness", "hospitality"]
        if reference == "Hebrews 13:1-8, 15-16":
            return ["epistle-only-theme"]
        return ["psalm-only-theme"]  # Psalm 81:1, 10-16

    mock_extract_themes.side_effect = themes_by_reference

    result = get_this_week_signals(db, claude=Mock())

    assert len(result) == 1
    connection = result[0]
    assert connection["reading_a_type"] == "gospel"
    assert connection["reading_b_type"] == "ot"
    assert connection["shared_themes"] == ["Hospitality"]


@patch("web.services.lectionary_widget_service.TextFetcher")
@patch("web.services.signals_service.TextFetcher")
@patch("web.services.signals_service.extract_themes")
def test_no_shared_themes_produces_no_connections(
    mock_extract_themes, mock_signals_fetcher_class, mock_readings_fetcher_class, db
):
    _mock_readings_fetcher(mock_readings_fetcher_class)
    mock_signals_fetcher_class.return_value.fetch.return_value = "full passage text"
    mock_extract_themes.side_effect = lambda claude, reference, text: [reference]  # every reading's theme is unique

    result = get_this_week_signals(db, claude=Mock())

    assert result == []


@patch("web.services.lectionary_widget_service.TextFetcher")
@patch("web.services.signals_service.TextFetcher")
@patch("web.services.signals_service.extract_themes")
def test_cache_hit_skips_fetch_and_extraction(
    mock_extract_themes, mock_signals_fetcher_class, mock_readings_fetcher_class, db
):
    _mock_readings_fetcher(mock_readings_fetcher_class)
    mock_signals_fetcher_class.return_value.fetch.return_value = "full passage text"
    mock_extract_themes.side_effect = lambda claude, reference, text: ["shared-theme"]

    get_this_week_signals(db, claude=Mock())  # first call populates the theme cache
    assert mock_extract_themes.call_count == 4

    mock_extract_themes.reset_mock()
    mock_signals_fetcher_class.return_value.fetch.reset_mock()

    result = get_this_week_signals(db, claude=Mock())  # second call should hit the cache

    assert mock_extract_themes.call_count == 0
    assert mock_signals_fetcher_class.return_value.fetch.call_count == 0
    assert len(result) == 6  # all C(4,2) pairs share "shared-theme"


@patch("web.services.lectionary_widget_service.TextFetcher")
@patch("web.services.signals_service.TextFetcher")
@patch("web.services.signals_service.extract_themes")
def test_extraction_failure_for_one_reading_does_not_block_others(
    mock_extract_themes, mock_signals_fetcher_class, mock_readings_fetcher_class, db
):
    _mock_readings_fetcher(mock_readings_fetcher_class)
    mock_signals_fetcher_class.return_value.fetch.return_value = "full passage text"

    def themes_or_fail(claude, reference, text):
        if reference == "Jeremiah 2:4-13":
            return []  # extract_themes returns [] on failure per its own docstring
        return ["hospitality"]

    mock_extract_themes.side_effect = themes_or_fail

    result = get_this_week_signals(db, claude=Mock())

    # gospel, epistle, psalm all share "hospitality" -> 3 pairs; "ot" (Jeremiah) excluded entirely
    assert len(result) == 3
    assert all("ot" not in (c["reading_a_type"], c["reading_b_type"]) for c in result)


@patch("web.services.lectionary_widget_service.TextFetcher")
@patch("web.services.signals_service.TextFetcher")
@patch("web.services.signals_service.extract_themes")
def test_fewer_than_two_reading_types_returns_empty_list(
    mock_extract_themes, mock_signals_fetcher_class, mock_readings_fetcher_class, db
):
    # get_this_week_readings() itself failed entirely (e.g. the Vanderbilt
    # site was down) - it returns {} in that case, per its own docstring.
    mock_readings_fetcher_class.return_value.fetch_sunday_lectionary_readings.return_value = {}

    result = get_this_week_signals(db, claude=Mock())

    assert result == []
    mock_signals_fetcher_class.return_value.fetch.assert_not_called()
    mock_extract_themes.assert_not_called()


@patch("web.services.lectionary_widget_service.TextFetcher")
@patch("web.services.signals_service.TextFetcher")
@patch("web.services.signals_service.extract_themes")
def test_results_sorted_by_shared_theme_count_descending(
    mock_extract_themes, mock_signals_fetcher_class, mock_readings_fetcher_class, db
):
    _mock_readings_fetcher(mock_readings_fetcher_class)
    mock_signals_fetcher_class.return_value.fetch.return_value = "full passage text"

    def themes_by_reference(claude, reference, text):
        return {
            "Luke 14:1-14": ["a", "b", "c"],
            "Jeremiah 2:4-13": ["a", "b"],
            "Hebrews 13:1-8, 15-16": ["a"],
            "Psalm 81:1, 10-16": ["z"],
        }[reference]

    mock_extract_themes.side_effect = themes_by_reference

    result = get_this_week_signals(db, claude=Mock())

    # gospel/ot share {a,b} (2), gospel/epistle share {a} (1), epistle/ot share {a} (1), psalm shares nothing
    assert len(result) == 3
    assert len(result[0]["shared_themes"]) == 2
    assert result[0]["reading_a_type"] == "gospel"
    assert result[0]["reading_b_type"] == "ot"
```

- [ ] **Step 3: Run the tests to confirm they fail**

```bash
python3 -m pytest tests/test_signals_service.py -v
```

Expected: FAIL — `web.services.signals_service` does not exist yet.

- [ ] **Step 4: Create the service**

Create `web/services/signals_service.py`:

```python
"""
Signals: detects thematic overlap among this week's four lectionary
readings (not readings vs. past studies - Study has no persisted theme
data, and this piece is scoped to what works from day one - see the
design spec for the full reasoning).

Reuses lectionary_widget_service.get_this_week_readings() for this
week's references, extracts theme keywords per reading (cached by
Sunday date, mirroring LectionaryReadingCache's pattern via a separate
LectionaryThemeCache table), and finds pairs that share at least one
theme (exact, case-insensitive match - no stemming or semantic
matching).
"""

import json
import logging
from datetime import date, timedelta
from itertools import combinations
from typing import List

from sqlalchemy.orm import Session

from lectionary_engines.claude_client import ClaudeClient
from lectionary_engines.text_fetcher import TextFetcher
from lectionary_engines.theme_extractor import extract_themes
from web.models import LectionaryThemeCache
from web.services.lectionary_widget_service import get_this_week_readings

logger = logging.getLogger(__name__)

READING_LABELS = {
    "gospel": "Gospel",
    "epistle": "Epistle",
    "ot": "Hebrew Scripture",
    "psalm": "Psalm",
}


def _upcoming_sunday(today: date) -> date:
    days_until_sunday = (6 - today.weekday()) % 7  # Monday=0 ... Sunday=6
    return today + timedelta(days=days_until_sunday)


def _get_themes_for_reading(
    db: Session, claude: ClaudeClient, sunday: date, reading_type: str, reference: str
) -> List[str]:
    cached = (
        db.query(LectionaryThemeCache)
        .filter(
            LectionaryThemeCache.reading_date == sunday,
            LectionaryThemeCache.reading_type == reading_type,
        )
        .first()
    )
    if cached:
        return json.loads(cached.themes)

    try:
        fetcher = TextFetcher()
        text = fetcher.fetch(reference)
        themes = extract_themes(claude, reference, text)
    except Exception as e:
        logger.warning(f"Failed to extract themes for '{reference}' ({reading_type}): {e}")
        themes = []

    row = LectionaryThemeCache(
        reading_date=sunday,
        reading_type=reading_type,
        themes=json.dumps(themes),
    )
    db.add(row)
    db.commit()

    return themes


def get_this_week_signals(db: Session, claude: ClaudeClient) -> list:
    """
    Returns a list of connection dicts, sorted by shared-theme count
    descending: [{"reading_a_type", "reading_a_label", "reading_a_reference",
    "reading_b_type", "reading_b_label", "reading_b_reference",
    "shared_themes"}, ...]. Empty list if fewer than 2 readings end up
    with a non-empty theme list, or no pair shares a theme.
    """
    this_week = get_this_week_readings(db)
    sunday = _upcoming_sunday(date.today())

    themes_by_type = {}
    for reading_type, reading in this_week.items():
        themes = _get_themes_for_reading(db, claude, sunday, reading_type, reading["reference"])
        if themes:
            themes_by_type[reading_type] = {
                "reference": reading["reference"],
                "themes": set(t.lower() for t in themes),
            }

    connections = []
    for type_a, type_b in combinations(themes_by_type.keys(), 2):
        shared = themes_by_type[type_a]["themes"] & themes_by_type[type_b]["themes"]
        if shared:
            connections.append({
                "reading_a_type": type_a,
                "reading_a_label": READING_LABELS[type_a],
                "reading_a_reference": themes_by_type[type_a]["reference"],
                "reading_b_type": type_b,
                "reading_b_label": READING_LABELS[type_b],
                "reading_b_reference": themes_by_type[type_b]["reference"],
                "shared_themes": sorted(t.title() for t in shared),
            })

    connections.sort(key=lambda c: len(c["shared_themes"]), reverse=True)
    return connections
```

- [ ] **Step 5: Run the tests to confirm they pass**

```bash
python3 -m pytest tests/test_signals_service.py -v
```

Expected: all 7 PASS. If a SQLAlchemy or mock-target error occurs, double-check the two separate `TextFetcher` patch targets (`web.services.lectionary_widget_service.TextFetcher` and `web.services.signals_service.TextFetcher`) are both applied — this is the most likely source of a confusing failure in this task, since it's easy to patch only one and have the other quietly hit a real (or unmocked-mock) call.

- [ ] **Step 6: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS, 0 failures.

- [ ] **Step 7: Commit**

```bash
git add web/models.py web/services/signals_service.py tests/test_signals_service.py
git commit -m "Add theme cache model and get_this_week_signals() service

New LectionaryThemeCache table (mirrors LectionaryReadingCache's
day-granularity caching) plus get_this_week_signals(), which extracts
theme keywords for this week's four readings and finds pairs sharing
at least one theme (exact, case-insensitive match, no stemming).

Scoped to readings-vs-readings, not readings-vs-studies - Study has no
persisted theme data, and this works from day one with zero historical
dependency. See docs/superpowers/specs/2026-08-28-tier-2-signals-design.md
for the full reasoning."
```

---

### Task 2: `/signals` route, page, and sidebar nav

**Files:**
- Create: `web/routes/signals.py`
- Create: `web/templates/signals.html`
- Modify: `web/app.py` (import + router registration)
- Modify: `web/templates/base.html` (sidebar nav)
- Modify: `tests/test_route_smoke.py`

**Interfaces:**
- Consumes: `get_this_week_signals(db, claude)` from Task 1, exact return shape as documented there.
- Produces: `GET /signals` route. Task 3 does not depend on this task — both Task 2 and Task 3 independently consume Task 1's service.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_route_smoke.py`:

```python
@patch("web.services.lectionary_widget_service.TextFetcher")
@patch("web.services.signals_service.TextFetcher")
@patch("web.services.signals_service.extract_themes")
def test_signals_page_renders(mock_extract_themes, mock_signals_fetcher_class, mock_readings_fetcher_class, isolated_client):
    mock_readings_fetcher_class.return_value.fetch_sunday_lectionary_readings.return_value = {
        "gospel": "Luke 14:1-14",
        "epistle": "Hebrews 13:1-8, 15-16",
        "ot": "Jeremiah 2:4-13",
        "psalm": "Psalm 81:1, 10-16",
    }
    mock_signals_fetcher_class.return_value.fetch.return_value = "full passage text"
    mock_extract_themes.side_effect = lambda claude, reference, text: ["hospitality"]

    response = isolated_client.get("/signals")

    assert response.status_code == 200
    assert "Signals" in response.text


def test_sidebar_links_to_signals(isolated_client):
    response = isolated_client.get("/engines")
    assert response.status_code == 200
    assert 'href="/signals"' in response.text
```

Note: `test_sidebar_links_to_signals` deliberately checks the sidebar via `/engines` (a fully static page with no external dependencies) rather than `/`, so it doesn't need to mock the Today homepage's own `TextFetcher`/`extract_themes` calls just to verify a sidebar link — the sidebar renders identically on every page via `base.html`.

- [ ] **Step 2: Run them to confirm they fail**

```bash
python3 -m pytest tests/test_route_smoke.py -v -k "signals"
```

Expected: both FAIL. `test_signals_page_renders` fails with a 404 (no route yet). `test_sidebar_links_to_signals` fails because `href="/signals"` doesn't exist yet.

- [ ] **Step 3: Create the router**

Create `web/routes/signals.py`:

```python
"""
Signals routes - thematic overlap among this week's lectionary readings
"""

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from pathlib import Path
from sqlalchemy.orm import Session

from lectionary_engines.claude_client import ClaudeClient

from ..config import WebConfig
from ..database import get_db
from ..services.signals_service import get_this_week_signals

router = APIRouter()

WEB_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))

config = WebConfig.load()


@router.get("/signals")
async def signals_page(request: Request, db: Session = Depends(get_db)):
    """
    Signals page - shows thematic overlap detected among this week's
    four lectionary readings.
    """
    claude = ClaudeClient(config.anthropic_api_key)
    connections = get_this_week_signals(db, claude)

    return templates.TemplateResponse("signals.html", {
        "request": request,
        "connections": connections,
    })
```

- [ ] **Step 4: Register the router in `web/app.py`**

In `web/app.py`, change the routes import line (currently `from .routes import studies, profiles, workshop, resonance, currents, engines`):

```python
from .routes import studies, profiles, workshop, resonance, currents, engines, signals
```

Then, immediately after the existing `app.include_router(engines.router, tags=["engines"])` line, add:

```python
app.include_router(signals.router, tags=["signals"])
```

- [ ] **Step 5: Add the sidebar nav link**

In `web/templates/base.html`, the sidebar nav currently reads:

```html
                <a href="/engines" class="sidebar-link {% if request.url.path.startswith('/engines') %}active{% endif %}">Engines</a>

                <div class="sidebar-divider"></div>
```

Change it to (one new line added, immediately after Engines, still before the divider):

```html
                <a href="/engines" class="sidebar-link {% if request.url.path.startswith('/engines') %}active{% endif %}">Engines</a>
                <a href="/signals" class="sidebar-link {% if request.url.path.startswith('/signals') %}active{% endif %}">Signals</a>

                <div class="sidebar-divider"></div>
```

- [ ] **Step 6: Create the template**

Create `web/templates/signals.html`:

```html
{% extends "base.html" %}

{% block title %}Signals | Lectionary Engines{% endblock %}

{% block content %}
<div class="container">
    <div class="page-header">
        <h1>Signals</h1>
        <p>Thematic connections detected among this week's four lectionary readings.</p>
    </div>

    {% if connections %}
    <div class="signals-list">
        {% for connection in connections %}
        <div class="signal-card">
            <div class="signal-pair">
                <span class="signal-reading">{{ connection.reading_a_label }}: {{ connection.reading_a_reference }}</span>
                <span class="signal-arrow">↔</span>
                <span class="signal-reading">{{ connection.reading_b_label }}: {{ connection.reading_b_reference }}</span>
            </div>
            <div class="signal-themes">
                {% for theme in connection.shared_themes %}
                <span class="theme-tag">{{ theme }}</span>
                {% endfor %}
            </div>
        </div>
        {% endfor %}
    </div>
    {% else %}
    <div class="empty-state">
        <h2>No connections detected this week</h2>
        <p>Check back next week, or explore the readings directly in the <a href="/">Today dashboard</a>.</p>
    </div>
    {% endif %}
</div>
{% endblock %}
```

`.theme-tag` already exists in `web/static/css/styles.css` (used by `resonance_result.html`) — reused as-is, no new CSS needed for it. `.empty-state` also already exists and is reused as-is.

- [ ] **Step 7: Add minimal CSS for the new `.signals-list`/`.signal-card` structure**

Add to `web/static/css/styles.css`, anywhere after the existing `.theme-tags` rule (search for `.theme-tags {` to find it):

```css
.signals-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-md);
}

.signal-card {
    background: rgba(255, 255, 255, 0.58);
    border: 1px solid var(--border-light);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-sm);
    padding: var(--space-lg);
}

.signal-pair {
    display: flex;
    align-items: center;
    gap: var(--space-sm);
    font-family: var(--font-editorial);
    font-size: 1.1rem;
    margin-bottom: var(--space-sm);
    flex-wrap: wrap;
}

.signal-arrow {
    color: var(--color-ink-muted);
}

.signal-themes {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-xs);
}
```

Every token used here (`--space-*`, `--radius-md`, `--shadow-sm`, `--border-light`, `--font-editorial`, `--color-ink-muted`) already exists in `:root` — do not invent new tokens, do not modify any existing rule.

- [ ] **Step 8: Run the tests to confirm they pass**

```bash
python3 -m pytest tests/test_route_smoke.py -v -k "signals"
```

Expected: both PASS.

- [ ] **Step 9: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS, 0 failures.

- [ ] **Step 10: Verify by eye**

Start the dev server (`uvicorn web.app:app --port 8123`, using the venv at the repo root), sign in, visit `/signals`. Confirm: the page renders, "Signals" appears in the sidebar between Engines and the first divider with the correct active-state highlight when you're on `/signals`. If your local DB/network access allows a real (unmocked) run, confirm connections show sensible reading pairs and theme tags, or the empty state if no overlap is found — if you don't have working browser tooling, curl the authenticated page and grep for expected content instead.

- [ ] **Step 11: Commit**

```bash
git add web/routes/signals.py web/templates/signals.html web/app.py web/templates/base.html web/static/css/styles.css tests/test_route_smoke.py
git commit -m "Add /signals page and sidebar nav link

New dedicated page showing thematic connections among this week's four
lectionary readings, using Task 1's get_this_week_signals(). Sidebar
gets a new Signals link in the primary nav group, after Engines and
before the first divider, matching the parent spec's IA ordering."
```

---

### Task 3: Today homepage Signals widget

**Files:**
- Modify: `web/app.py:105-123` (the `/` route)
- Modify: `web/templates/index.html`
- Modify: `tests/test_route_smoke.py`

**Interfaces:**
- Consumes: `get_this_week_signals(db, claude)` from Task 1, exact return shape as documented there.
- Produces: nothing consumed by later tasks — this is the last task in this plan.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_route_smoke.py`:

```python
@patch("web.services.lectionary_widget_service.TextFetcher")
@patch("web.services.signals_service.TextFetcher")
@patch("web.services.signals_service.extract_themes")
def test_today_homepage_shows_signals_widget(mock_extract_themes, mock_signals_fetcher_class, mock_readings_fetcher_class, isolated_client):
    mock_readings_fetcher_class.return_value.fetch_sunday_lectionary_readings.return_value = {
        "gospel": "Luke 14:1-14",
        "epistle": "Hebrews 13:1-8, 15-16",
        "ot": "Jeremiah 2:4-13",
        "psalm": "Psalm 81:1, 10-16",
    }
    mock_signals_fetcher_class.return_value.fetch.return_value = "full passage text"
    mock_extract_themes.side_effect = lambda claude, reference, text: ["hospitality"]

    response = isolated_client.get("/")

    assert response.status_code == 200
    assert "Signals" in response.text
```

- [ ] **Step 2: Run it to confirm it fails**

```bash
python3 -m pytest tests/test_route_smoke.py -v -k "test_today_homepage_shows_signals_widget"
```

Expected: FAIL — the current `index.html` has no "Signals" section.

- [ ] **Step 3: Update the `/` route**

In `web/app.py`, the current route reads:

```python
@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    """
    Today homepage - This Week in the Lectionary, engine cards, quick
    actions, and recent studies
    """
    from .services.lectionary_widget_service import get_this_week_readings

    # Get recent studies (last 5)
    recent_studies = db.query(Study).order_by(Study.created_at.desc()).limit(5).all()

    this_week = get_this_week_readings(db)

    return templates.TemplateResponse("index.html", {
        "request": request,
        "recent_studies": recent_studies,
        "this_week": this_week,
        "config": config
    })
```

Change it to:

```python
@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    """
    Today homepage - This Week in the Lectionary, Signals, engine cards,
    quick actions, and recent studies
    """
    from lectionary_engines.claude_client import ClaudeClient
    from .services.lectionary_widget_service import get_this_week_readings
    from .services.signals_service import get_this_week_signals

    # Get recent studies (last 5)
    recent_studies = db.query(Study).order_by(Study.created_at.desc()).limit(5).all()

    this_week = get_this_week_readings(db)

    claude = ClaudeClient(config.anthropic_api_key)
    signals = get_this_week_signals(db, claude)[:3]  # top 3 for the compact widget; full list on /signals

    return templates.TemplateResponse("index.html", {
        "request": request,
        "recent_studies": recent_studies,
        "this_week": this_week,
        "signals": signals,
        "config": config
    })
```

`config.anthropic_api_key` is already available — `config = WebConfig.load()` runs at module level near the top of `web/app.py` (the same `config` object the route already uses for `"config": config` in the template context).

- [ ] **Step 4: Fix two pre-existing tests that now exercise the new code path**

`test_sidebar_links_to_engines` and `test_today_homepage_shows_this_week_readings` (already in `tests/test_route_smoke.py`, from the earlier Today-homepage piece) both hit `GET /` with a real (non-empty) mocked `this_week` payload, and only patch `web.services.lectionary_widget_service.TextFetcher`. After Step 3, `/` also calls `get_this_week_signals()`, which — for a non-empty `this_week` — calls `TextFetcher().fetch(...)` and `extract_themes(...)` from the `web.services.signals_service` module. Left unpatched in these two tests, that means real network and Claude API calls on every test run. Add the same two extra patches Task 1/2's tests use.

Find this in `tests/test_route_smoke.py`:

```python
@patch("web.services.lectionary_widget_service.TextFetcher")
def test_sidebar_links_to_engines(mock_fetcher_class, isolated_client):
    mock_fetcher = mock_fetcher_class.return_value
    mock_fetcher.fetch_sunday_lectionary_readings.return_value = {
        "gospel": "Luke 14:1-14",
        "epistle": "Hebrews 13:1-8, 15-16",
        "ot": "Jeremiah 2:4-13",
        "psalm": "Psalm 81:1, 10-16",
    }

    response = isolated_client.get("/")
    assert response.status_code == 200
    assert 'href="/engines"' in response.text
```

Replace it with:

```python
@patch("web.services.lectionary_widget_service.TextFetcher")
@patch("web.services.signals_service.TextFetcher")
@patch("web.services.signals_service.extract_themes")
def test_sidebar_links_to_engines(mock_extract_themes, mock_signals_fetcher_class, mock_fetcher_class, isolated_client):
    mock_fetcher = mock_fetcher_class.return_value
    mock_fetcher.fetch_sunday_lectionary_readings.return_value = {
        "gospel": "Luke 14:1-14",
        "epistle": "Hebrews 13:1-8, 15-16",
        "ot": "Jeremiah 2:4-13",
        "psalm": "Psalm 81:1, 10-16",
    }
    mock_signals_fetcher_class.return_value.fetch.return_value = "full passage text"
    mock_extract_themes.return_value = []

    response = isolated_client.get("/")
    assert response.status_code == 200
    assert 'href="/engines"' in response.text
```

Then find:

```python
@patch("web.services.lectionary_widget_service.TextFetcher")
def test_today_homepage_shows_this_week_readings(mock_fetcher_class, isolated_client):
    mock_fetcher = mock_fetcher_class.return_value
    mock_fetcher.fetch_sunday_lectionary_readings.return_value = {
        "gospel": "Luke 14:1-14",
        "epistle": "Hebrews 13:1-8, 15-16",
        "ot": "Jeremiah 2:4-13",
        "psalm": "Psalm 81:1, 10-16",
    }

    response = isolated_client.get("/")

    assert response.status_code == 200
    body = response.text
    assert "Gospel" in body
    assert "Epistle" in body
    assert "Hebrew Scripture" in body
    assert "Psalm" in body
```

Replace it with:

```python
@patch("web.services.lectionary_widget_service.TextFetcher")
@patch("web.services.signals_service.TextFetcher")
@patch("web.services.signals_service.extract_themes")
def test_today_homepage_shows_this_week_readings(mock_extract_themes, mock_signals_fetcher_class, mock_fetcher_class, isolated_client):
    mock_fetcher = mock_fetcher_class.return_value
    mock_fetcher.fetch_sunday_lectionary_readings.return_value = {
        "gospel": "Luke 14:1-14",
        "epistle": "Hebrews 13:1-8, 15-16",
        "ot": "Jeremiah 2:4-13",
        "psalm": "Psalm 81:1, 10-16",
    }
    mock_signals_fetcher_class.return_value.fetch.return_value = "full passage text"
    mock_extract_themes.return_value = []

    response = isolated_client.get("/")

    assert response.status_code == 200
    body = response.text
    assert "Gospel" in body
    assert "Epistle" in body
    assert "Hebrew Scripture" in body
    assert "Psalm" in body
```

`test_home_page_renders` (the third `isolated_client` test hitting `/`) needs no change — it mocks `fetch_sunday_lectionary_readings.return_value = {}`, so `get_this_week_readings` returns `{}`, `get_this_week_signals`'s per-reading-type loop never runs, and neither `signals_service.TextFetcher` nor `extract_themes` is ever called.

- [ ] **Step 5: Add the widget to the template**

In `web/templates/index.html`, insert a new section immediately after the closing `</section>` of "This Week in the Lectionary" and before the `<section class="choose-engine-section">` opening tag:

```html
    <section class="signals-section">
        <h2>Signals</h2>
        {% if signals %}
        <div class="signals-list">
            {% for connection in signals %}
            <div class="signal-card">
                <div class="signal-pair">
                    <span class="signal-reading">{{ connection.reading_a_label }}: {{ connection.reading_a_reference }}</span>
                    <span class="signal-arrow">↔</span>
                    <span class="signal-reading">{{ connection.reading_b_label }}: {{ connection.reading_b_reference }}</span>
                </div>
                <div class="signal-themes">
                    {% for theme in connection.shared_themes %}
                    <span class="theme-tag">{{ theme }}</span>
                    {% endfor %}
                </div>
            </div>
            {% endfor %}
        </div>
        <div class="section-footer">
            <a href="/signals" class="btn btn-link">View all signals →</a>
        </div>
        {% else %}
        <div class="empty-state">
            <p>No connections detected this week.</p>
        </div>
        {% endif %}
    </section>
```

This reuses `.signals-list`/`.signal-card`/`.signal-pair`/`.signal-arrow`/`.signal-themes`/`.theme-tag`/`.empty-state` — all already defined by Task 2 (or, for `.theme-tag`/`.empty-state`, already pre-existing before this whole plan). No new CSS needed in this task. `.section-footer`/`.btn-link` already exist too (used by the "Continue Your Studies" section further down this same template).

- [ ] **Step 6: Run the test to confirm it passes**

```bash
python3 -m pytest tests/test_route_smoke.py -v -k "signals or this_week_readings or sidebar_links_to_engines"
```

Expected: all PASS — the new widget test, and the two pre-existing tests fixed in Step 4.

- [ ] **Step 7: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS, 0 failures.

- [ ] **Step 8: Verify by eye**

Start the dev server, sign in, visit `/`. Confirm the Signals section appears between "This Week in the Lectionary" and "Choose Your Engine," shows up to 3 connections (or the empty state), and "View all signals →" links to `/signals`.

- [ ] **Step 9: Commit**

```bash
git add web/app.py web/templates/index.html tests/test_route_smoke.py
git commit -m "Add Signals widget to the Today homepage

/ now shows up to 3 of this week's detected thematic connections
(from Task 1's get_this_week_signals()), reusing the .signal-card
styling Task 2 already added, with a link to the full /signals page.
This fills the widget slot the Today homepage piece deliberately left
empty for Signals."
```

---
