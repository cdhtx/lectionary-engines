# Tier 1b — Today Homepage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the homepage's static hero+grid with a "Today" dashboard: This Week in the Lectionary (cached RCL readings), compact engine cards linking to `/engines`, Quick Actions, and the existing recent-studies list (no progress bars).

**Architecture:** A new DB-backed cache table plus a small service function isolate the one piece of genuinely new backend logic (avoiding 4 live external fetches per homepage load) from the route and template, which are otherwise thin. Two tasks: (1) the cache model + service, fully unit-tested in isolation; (2) wiring it into the `/` route and rewriting `index.html`.

**Tech Stack:** SQLAlchemy (new model), FastAPI, Jinja2, pytest with `unittest.mock` for the external-fetch mocking.

## Global Constraints

- **Branch from `beta-tier-1a-restyle`** (or `main` once merged), and this branch must also include the Engines directory piece's work (either branch from `tier-1b-engines-directory`, or verify `/engines` exists on whatever base is used) — the new engine cards link to `/engines`, which must resolve.
- **New table, not a new column.** `Base.metadata.create_all()` in `web/database.py`'s `init_db()` creates brand-new tables automatically on startup. Do NOT add an entry to `COLUMN_MIGRATIONS` in `web/database.py` — that mechanism is only for adding a column to an *existing* table.
- **Graceful partial failure.** If `fetch_rcl()` fails for one reading type, that reading is omitted from "This Week" — the whole homepage must never fail because of one bad external fetch.
- **No thematic summary lines, no `/generate?engine=X` preselect, no progress percentages, no Currents/Signals/Notes widgets** — all explicitly out of scope per the design spec.
- **The existing test suite must stay green** (baseline count depends on which branches are merged in — confirm via `python3 -m pytest tests/ -v` before starting, don't assume a specific number).

---

### Task 1: Lectionary reading cache — model and service

**Files:**
- Modify: `web/models.py` (add `LectionaryReadingCache`)
- Create: `web/services/lectionary_widget_service.py`
- Test: `tests/test_lectionary_widget_service.py`

**Interfaces:**
- Consumes: `lectionary_engines.text_fetcher.TextFetcher` (existing class, `__init__(self, default_translation: str = "NRSVue")`, method `fetch_rcl(reading_type: str) -> Tuple[str, str]` returning `(reference, text)`, raises on failure).
- Produces: `web.models.LectionaryReadingCache` (SQLAlchemy model); `web.services.lectionary_widget_service.get_this_week_readings(db: Session) -> dict` — returns a dict keyed by `"gospel"`, `"epistle"`, `"ot"`, `"psalm"`; each present key's value is `{"reference": str, "text": str}`; a key is absent entirely if that reading type's fetch failed. Task 2 consumes this function and its return shape directly.

- [ ] **Step 1: Add the model**

In `web/models.py`, the import line currently reads:

```python
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Index
```

Change it to add `Date` and `UniqueConstraint`:

```python
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Index, Date, UniqueConstraint
```

Then add this class at the end of the file (after `CollisionVectorState`):

```python
class LectionaryReadingCache(Base):
    """
    Caches one day's RCL readings so the Today homepage doesn't re-fetch
    from Vanderbilt's site on every page load. fetch_rcl() has no caching
    of its own - this table adds a day-granularity cache in front of it.
    """

    __tablename__ = "lectionary_reading_cache"

    id = Column(Integer, primary_key=True)
    reading_date = Column(Date, nullable=False, index=True)
    reading_type = Column(String(20), nullable=False)  # "gospel", "ot", "psalm", "epistle"
    reference = Column(String(500), nullable=False)
    text = Column(Text, nullable=False)
    fetched_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("reading_date", "reading_type", name="uq_reading_date_type"),
    )

    def __repr__(self):
        return f"<LectionaryReadingCache(reading_date='{self.reading_date}', reading_type='{self.reading_type}')>"
```

`datetime` is already imported at the top of `web/models.py` (`from datetime import datetime`) — no new import needed for that.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_lectionary_widget_service.py`:

```python
"""
Tests for the Today homepage's "This Week in the Lectionary" cache layer.

fetch_rcl() makes a live, uncached HTTP call to an external site - every
test here mocks it. No test in this file should make a real network call.
"""

from datetime import date
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from web.models import Base, LectionaryReadingCache
from web.services.lectionary_widget_service import get_this_week_readings


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@patch("web.services.lectionary_widget_service.TextFetcher")
def test_cache_miss_fetches_and_stores(mock_fetcher_class, db):
    mock_fetcher = mock_fetcher_class.return_value
    mock_fetcher.fetch_rcl.side_effect = lambda reading_type: (f"{reading_type}-ref", f"{reading_type}-text")

    result = get_this_week_readings(db)

    assert result["gospel"] == {"reference": "gospel-ref", "text": "gospel-text"}
    assert result["epistle"] == {"reference": "epistle-ref", "text": "epistle-text"}
    assert result["ot"] == {"reference": "ot-ref", "text": "ot-text"}
    assert result["psalm"] == {"reference": "psalm-ref", "text": "psalm-text"}
    assert mock_fetcher.fetch_rcl.call_count == 4

    cached_rows = db.query(LectionaryReadingCache).all()
    assert len(cached_rows) == 4
    assert {row.reading_type for row in cached_rows} == {"gospel", "epistle", "ot", "psalm"}


@patch("web.services.lectionary_widget_service.TextFetcher")
def test_cache_hit_skips_fetch(mock_fetcher_class, db):
    mock_fetcher = mock_fetcher_class.return_value
    mock_fetcher.fetch_rcl.side_effect = lambda reading_type: (f"{reading_type}-ref", f"{reading_type}-text")

    # First call populates the cache.
    get_this_week_readings(db)
    assert mock_fetcher.fetch_rcl.call_count == 4

    # Second call on the same day should hit the cache, not fetch again.
    mock_fetcher.fetch_rcl.reset_mock()
    result = get_this_week_readings(db)

    assert result["gospel"] == {"reference": "gospel-ref", "text": "gospel-text"}
    assert mock_fetcher.fetch_rcl.call_count == 0


@patch("web.services.lectionary_widget_service.TextFetcher")
def test_one_failed_fetch_does_not_block_the_others(mock_fetcher_class, db):
    mock_fetcher = mock_fetcher_class.return_value

    def side_effect(reading_type):
        if reading_type == "psalm":
            raise Exception("Vanderbilt site unreachable")
        return (f"{reading_type}-ref", f"{reading_type}-text")

    mock_fetcher.fetch_rcl.side_effect = side_effect

    result = get_this_week_readings(db)

    assert "psalm" not in result
    assert result["gospel"] == {"reference": "gospel-ref", "text": "gospel-text"}
    assert result["epistle"] == {"reference": "epistle-ref", "text": "epistle-text"}
    assert result["ot"] == {"reference": "ot-ref", "text": "ot-text"}

    cached_rows = db.query(LectionaryReadingCache).all()
    assert len(cached_rows) == 3
    assert "psalm" not in {row.reading_type for row in cached_rows}
```

- [ ] **Step 3: Run the tests to confirm they fail**

```bash
python3 -m pytest tests/test_lectionary_widget_service.py -v
```

Expected: FAIL — `web.services.lectionary_widget_service` does not exist yet (`ModuleNotFoundError` or `ImportError`).

- [ ] **Step 4: Create the service**

Create `web/services/lectionary_widget_service.py`:

```python
"""
Today homepage's "This Week in the Lectionary" widget: fetches and caches
one day's four RCL readings (Gospel, Epistle, Old Testament, Psalm).

fetch_rcl() makes a live, uncached HTTP scrape of Vanderbilt Divinity
Library's site per call - calling it 4x on every homepage load, with no
caching, would make the app's most-visited page depend on an external
site's uptime and latency. This module adds a day-granularity DB cache in
front of it (see web.models.LectionaryReadingCache).

A single reading type's fetch failure does not prevent the other three
from succeeding - the homepage shows a partial widget rather than none at
all, and never fails outright because of a Vanderbilt outage.
"""

import logging
from datetime import date
from typing import Dict

from sqlalchemy.orm import Session

from lectionary_engines.text_fetcher import TextFetcher
from web.models import LectionaryReadingCache

logger = logging.getLogger(__name__)

READING_TYPES = ["gospel", "epistle", "ot", "psalm"]


def get_this_week_readings(db: Session) -> Dict[str, dict]:
    """
    Returns a dict keyed by reading type ("gospel", "epistle", "ot",
    "psalm"). Each present key's value is {"reference": str, "text": str}.
    A key is absent if that reading type's fetch failed today and there
    was no cached row to fall back on.
    """
    today = date.today()
    results: Dict[str, dict] = {}
    fetcher = TextFetcher()

    for reading_type in READING_TYPES:
        cached = (
            db.query(LectionaryReadingCache)
            .filter(
                LectionaryReadingCache.reading_date == today,
                LectionaryReadingCache.reading_type == reading_type,
            )
            .first()
        )
        if cached:
            results[reading_type] = {"reference": cached.reference, "text": cached.text}
            continue

        try:
            reference, text = fetcher.fetch_rcl(reading_type)
        except Exception as e:
            logger.warning(f"Failed to fetch RCL reading '{reading_type}': {e}")
            continue

        row = LectionaryReadingCache(
            reading_date=today,
            reading_type=reading_type,
            reference=reference,
            text=text,
        )
        db.add(row)
        db.commit()

        results[reading_type] = {"reference": reference, "text": text}

    return results
```

- [ ] **Step 5: Run the tests to confirm they pass**

```bash
python3 -m pytest tests/test_lectionary_widget_service.py -v
```

Expected: all 3 PASS.

- [ ] **Step 6: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS, 0 failures.

- [ ] **Step 7: Commit**

```bash
git add web/models.py web/services/lectionary_widget_service.py tests/test_lectionary_widget_service.py
git commit -m "Add lectionary reading cache model and This Week service

New LectionaryReadingCache table plus get_this_week_readings(), a
day-granularity cache in front of fetch_rcl(). Avoids 4 live external
scrapes of Vanderbilt's site per homepage load; a single reading type's
fetch failure doesn't block the other three.

New table only - no COLUMN_MIGRATIONS entry needed, create_all() handles
brand-new tables automatically."
```

---

### Task 2: Wire into the homepage route and template

**Files:**
- Modify: `web/app.py:104-116` (the `/` route)
- Modify: `web/templates/index.html` (full content rewrite)
- Modify: `web/static/css/styles.css` (new rules for the new sections)
- Modify: `tests/test_route_smoke.py`

**Interfaces:**
- Consumes: `get_this_week_readings(db)` from Task 1, exact return shape as documented there (dict keyed by `"gospel"`/`"epistle"`/`"ot"`/`"psalm"`, each value `{"reference": str, "text": str}` or key absent).
- Produces: nothing consumed by later tasks — this is the last task in this plan.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_route_smoke.py`. This test needs the four readings to actually resolve, so it mocks `TextFetcher` the same way Task 1's tests do (patching where it's *used*, i.e. in `web.services.lectionary_widget_service`, not where it's defined):

```python
from unittest.mock import patch


@patch("web.services.lectionary_widget_service.TextFetcher")
def test_today_homepage_shows_this_week_readings(mock_fetcher_class, client):
    mock_fetcher = mock_fetcher_class.return_value
    mock_fetcher.fetch_rcl.side_effect = lambda reading_type: (f"{reading_type}-ref", f"{reading_type}-text")

    response = client.get("/")

    assert response.status_code == 200
    body = response.text
    assert "Gospel" in body
    assert "Epistle" in body
    assert "Hebrew Scripture" in body
    assert "Psalm" in body
```

- [ ] **Step 2: Run it to confirm it fails**

```bash
python3 -m pytest tests/test_route_smoke.py -v -k "test_today_homepage_shows_this_week_readings"
```

Expected: FAIL — "Gospel" (the category label) doesn't appear anywhere in the current `index.html` output.

- [ ] **Step 3: Update the `/` route**

In `web/app.py`, the current route reads:

```python
@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    """
    Home page - shows welcome message and recent studies
    """
    # Get recent studies (last 5)
    recent_studies = db.query(Study).order_by(Study.created_at.desc()).limit(5).all()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "recent_studies": recent_studies,
        "config": config
    })
```

Change it to:

```python
@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
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

The import is placed inside the function (matching the existing local-import style already used elsewhere in this route file, e.g. `/profiles`'s `from .models import UserProfile`) rather than at module level, to avoid growing `web/app.py`'s already-long top-level import block for a dependency only this one route needs.

- [ ] **Step 4: Rewrite the template**

Replace the entire `{% block content %}...{% endblock %}` body of `web/templates/index.html` (currently the hero section, engines-info section, and recent-studies section) with:

```html
{% block content %}
<div class="container">
    <div class="page-header">
        <h1>Today</h1>
        <p>Biblical interpretation through three hermeneutical frameworks</p>
    </div>

    <section class="this-week-section">
        <h2>This Week in the Lectionary</h2>
        <div class="this-week-grid">
            {% if this_week.gospel %}
            <div class="reading-card">
                <span class="reading-label">Gospel</span>
                <p class="reading-reference">{{ this_week.gospel.reference }}</p>
            </div>
            {% endif %}
            {% if this_week.epistle %}
            <div class="reading-card">
                <span class="reading-label">Epistle</span>
                <p class="reading-reference">{{ this_week.epistle.reference }}</p>
            </div>
            {% endif %}
            {% if this_week.ot %}
            <div class="reading-card">
                <span class="reading-label">Hebrew Scripture</span>
                <p class="reading-reference">{{ this_week.ot.reference }}</p>
            </div>
            {% endif %}
            {% if this_week.psalm %}
            <div class="reading-card">
                <span class="reading-label">Psalm</span>
                <p class="reading-reference">{{ this_week.psalm.reference }}</p>
            </div>
            {% endif %}
        </div>
    </section>

    <section class="choose-engine-section">
        <h2>Choose Your Engine</h2>
        <div class="engines-directory-list">
            <a href="/engines" class="engine-card">
                <h3>Threshold</h3>
                <p>Four progressive thresholds of engagement, culminating in a tech touchpoint.</p>
            </a>
            <a href="/engines" class="engine-card">
                <h3>Palimpsest</h3>
                <p>Five hermeneutical layers using the PaRDeS framework.</p>
            </a>
            <a href="/engines" class="engine-card">
                <h3>Collision</h3>
                <p>Five-step collision process forcing unprecedented connections.</p>
            </a>
        </div>
    </section>

    <section class="quick-actions-section">
        <h2>Quick Actions</h2>
        <div class="quick-actions-list">
            <a href="/generate" class="btn btn-secondary">Start a New Study</a>
            <a href="/browse" class="btn btn-secondary">View Library</a>
            <a href="/currents" class="btn btn-secondary">Explore Currents</a>
        </div>
    </section>

    {% if recent_studies %}
    <section class="recent-studies">
        <h2>Continue Your Studies</h2>
        <div class="studies-list">
            {% for study in recent_studies %}
            <div class="study-item">
                <a href="/study/{{ study.id }}" class="study-link">
                    <span class="engine-badge engine-{{ study.engine }}">{{ study.engine }}</span>
                    <span class="study-reference">{{ study.reference }}</span>
                    <span class="study-meta">
                        {{ study.word_count }} words | {{ study.created_at.strftime('%B %d, %Y') }}
                    </span>
                </a>
            </div>
            {% endfor %}
        </div>
        <div class="section-footer">
            <a href="/browse" class="btn btn-link">View all studies →</a>
        </div>
    </section>
    {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 5: Add CSS for the new sections**

Add to `web/static/css/styles.css`, anywhere after the existing `.engines-info`/`.engines-grid`/`.engine-card` rules (search for `.engine-card {` to find that area):

```css
.this-week-section,
.choose-engine-section,
.quick-actions-section {
    margin-bottom: var(--space-2xl);
}

.this-week-section h2,
.choose-engine-section h2,
.quick-actions-section h2 {
    font-family: var(--font-display);
    text-align: center;
    margin-bottom: var(--space-xl);
    font-size: 1.8rem;
    font-weight: 500;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: var(--color-ink-muted);
}

.this-week-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: var(--space-md);
}

.reading-card {
    background: rgba(255, 255, 255, 0.58);
    padding: var(--space-md);
    border-radius: var(--radius-md);
    border: 1px solid var(--border-light);
    box-shadow: var(--shadow-sm);
    text-align: center;
}

.reading-label {
    display: block;
    font-family: var(--font-ui);
    font-size: 0.68rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: var(--color-ink-muted);
    margin-bottom: var(--space-xs);
}

.reading-reference {
    font-family: var(--font-editorial);
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--color-ink);
}

.quick-actions-list {
    display: flex;
    justify-content: center;
    gap: var(--space-md);
    flex-wrap: wrap;
}

/* .engine-card is normally a <div>; Today's cards are <a> so they're
   clickable to /engines. Additive override, doesn't touch the existing
   .engine-card rule used elsewhere (e.g. web/templates/engines.html). */
a.engine-card {
    display: block;
    text-decoration: none;
    color: inherit;
}
```

Every token used here (`--space-*`, `--radius-md`, `--shadow-sm`, `--border-light`, `--font-display`/`--font-ui`/`--font-editorial`, `--color-ink`/`--color-ink-muted`) already exists in `:root` from Tier 1a — do not invent new tokens.

- [ ] **Step 6: Run the test to confirm it passes**

```bash
python3 -m pytest tests/test_route_smoke.py -v -k "test_today_homepage_shows_this_week_readings"
```

Expected: PASS.

- [ ] **Step 7: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS, 0 failures.

- [ ] **Step 8: Verify by eye**

Start the dev server (`uvicorn web.app:app --port 8123`, using the venv at the repo root), sign in, visit `/`. Confirm: This Week section shows 4 readings (or fewer, gracefully, if you don't mock the fetcher and a live fetch fails — that's expected without Task 1's test mocking active in a manual browser session), Choose Your Engine section shows 3 cards linking to `/engines` (click one to confirm), Quick Actions section shows 3 links to the right routes, Continue Your Studies shows the same recent-studies list the old homepage had (empty state if the local DB has no studies, which is expected — note in your report rather than treating as a bug).

- [ ] **Step 9: Commit**

```bash
git add web/app.py web/templates/index.html web/static/css/styles.css tests/test_route_smoke.py
git commit -m "Wire This Week readings into the Today homepage

/ now shows This Week in the Lectionary (from Task 1's cached service),
compact engine cards linking to /engines, Quick Actions, and the existing
recent-studies list relabeled 'Continue Your Studies' (no progress bars -
that data doesn't exist yet).

New CSS reuses existing Beta tokens throughout - no new design tokens
introduced."
```

---
