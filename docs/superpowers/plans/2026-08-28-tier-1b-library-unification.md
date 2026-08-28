# Tier 1b — Library Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify `/browse` into one paginated, searchable list spanning Study, WorkshopPrep, CurrentsAnalysis, and CulturalResonance, replacing its current Study-only query.

**Architecture:** A new service function builds one normalized SQLAlchemy `select()` per content type and combines them with `union_all()`, so pagination is correct across the *combined* chronological result rather than four independently-paginated lists glued together. The route and template are then updated to use it.

**Tech Stack:** SQLAlchemy 2.0 (`select()`/`union_all()`/`func.coalesce()`), FastAPI, Jinja2, pytest.

## Global Constraints

- **`/workshop/browse` and `/currents/browse` are untouched.** Only `/browse`'s route, `web/templates/browse.html`, and the new service file are in scope. No sidebar changes.
- **`content_type` query param values:** `"study"`, `"workshop"`, `"currents"`, `"resonance"`. Absent, empty, or unrecognized → no filter (all four types). This replaces the existing `engine`/`source` query params, which the type filter supersedes.
- **No granular per-type filters** (engine/source/lens) in this piece — only the type selector and one shared search box.
- **The existing test suite must stay green** (108 tests at branch point — confirm via `python3 -m pytest tests/ -v` before starting, don't assume the exact number if it's drifted).

---

### Task 1: `search_library()` unified query service

**Files:**
- Create: `web/services/library_service.py`
- Test: `tests/test_library_service.py`

**Interfaces:**
- Consumes: `web.models.Study`, `web.models.WorkshopPrep`, `web.models.CurrentsAnalysis`, `web.models.CulturalResonance` (existing models, unchanged).
- Produces: `search_library(db: Session, content_type: Optional[str] = None, q: Optional[str] = None, page: int = 1, per_page: int = 12) -> dict`. Returns `{"results": [...], "page": int, "total_pages": int, "total": int, "has_prev": bool, "has_next": bool}`. Each item in `results` is `{"content_type": str, "id": int, "title": str, "badge_label": str, "created_at": datetime, "url": str}`. Task 2 consumes this function and this exact return shape directly.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_library_service.py`:

```python
"""
Tests for the unified Library query.

Seeds an in-memory SQLite DB with rows across all four content models and
verifies: cross-type ordering, type filtering, search filtering per the
type-specific field mapping, and pagination correctness when results span
more than one type on the same page.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from web.models import Base, CulturalResonance, CurrentsAnalysis, Study, WorkshopPrep
from web.services.library_service import search_library


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


def _seed_one_of_each(db, base_time):
    db.add(Study(
        engine="threshold", reference="John 3:16-21", content="For God so loved the world",
        created_at=base_time - timedelta(days=1),
    ))
    db.add(WorkshopPrep(
        lens="apostolic_journalist", lens_name="The Apostolic Journalist",
        reference="Luke 14:1-14", content="Sabbath hospitality reading",
        created_at=base_time - timedelta(days=2),
    ))
    db.add(CurrentsAnalysis(
        analysis_date="August 20, 2026", headline_summary="A Test Headline",
        content="Some news analysis content", created_at=base_time - timedelta(days=3),
    ))
    db.add(CulturalResonance(
        themes='["hospitality", "empire"]', reference=None,
        content="Resonance content about hospitality", created_at=base_time - timedelta(days=4),
    ))
    db.commit()


def test_no_filter_returns_all_four_types_ordered_by_recency(db):
    base_time = datetime(2026, 8, 28, 12, 0, 0)
    _seed_one_of_each(db, base_time)

    result = search_library(db)

    assert result["total"] == 4
    content_types = [r["content_type"] for r in result["results"]]
    assert content_types == ["study", "workshop", "currents", "resonance"]


def test_content_type_filter_returns_only_that_type(db):
    base_time = datetime(2026, 8, 28, 12, 0, 0)
    _seed_one_of_each(db, base_time)

    result = search_library(db, content_type="workshop")

    assert result["total"] == 1
    assert result["results"][0]["content_type"] == "workshop"
    assert result["results"][0]["title"] == "Luke 14:1-14"


def test_unrecognized_content_type_is_treated_as_no_filter(db):
    base_time = datetime(2026, 8, 28, 12, 0, 0)
    _seed_one_of_each(db, base_time)

    result = search_library(db, content_type="not-a-real-type")

    assert result["total"] == 4


def test_search_matches_study_reference_and_content(db):
    base_time = datetime(2026, 8, 28, 12, 0, 0)
    _seed_one_of_each(db, base_time)

    result = search_library(db, q="John 3")

    assert result["total"] == 1
    assert result["results"][0]["content_type"] == "study"


def test_search_matches_currents_headline_since_it_has_no_reference_field(db):
    base_time = datetime(2026, 8, 28, 12, 0, 0)
    _seed_one_of_each(db, base_time)

    result = search_library(db, q="Test Headline")

    assert result["total"] == 1
    assert result["results"][0]["content_type"] == "currents"


def test_resonance_title_falls_back_to_joined_themes_when_reference_is_null(db):
    base_time = datetime(2026, 8, 28, 12, 0, 0)
    _seed_one_of_each(db, base_time)

    result = search_library(db, content_type="resonance")

    assert result["results"][0]["title"] == "Hospitality, Empire"


def test_urls_are_correct_per_type(db):
    base_time = datetime(2026, 8, 28, 12, 0, 0)
    _seed_one_of_each(db, base_time)

    result = search_library(db)
    by_type = {r["content_type"]: r for r in result["results"]}

    assert by_type["study"]["url"].startswith("/study/")
    assert by_type["workshop"]["url"].startswith("/workshop/")
    assert by_type["currents"]["url"].startswith("/currents/")
    assert by_type["resonance"]["url"].startswith("/resonance/")


def test_pagination_is_correct_across_types_on_the_same_page(db):
    base_time = datetime(2026, 8, 28, 12, 0, 0)
    _seed_one_of_each(db, base_time)

    result = search_library(db, page=1, per_page=2)

    assert result["total"] == 4
    assert result["total_pages"] == 2
    assert len(result["results"]) == 2
    # Most recent 2 overall: study (day -1), workshop (day -2)
    assert [r["content_type"] for r in result["results"]] == ["study", "workshop"]
    assert result["has_next"] is True
    assert result["has_prev"] is False

    page2 = search_library(db, page=2, per_page=2)
    assert [r["content_type"] for r in page2["results"]] == ["currents", "resonance"]
    assert page2["has_next"] is False
    assert page2["has_prev"] is True
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
python3 -m pytest tests/test_library_service.py -v
```

Expected: FAIL — `web.services.library_service` does not exist yet (`ModuleNotFoundError`).

- [ ] **Step 3: Create the service**

Create `web/services/library_service.py`:

```python
"""
Unified Library query: spans Study, WorkshopPrep, CurrentsAnalysis, and
CulturalResonance in one paginated, chronologically-ordered result set.

Each content type is projected into a common shape (id, content_type,
title, badge_label, created_at) via a SQLAlchemy select(), then combined
with union_all() and paginated over the *combined* result - not fetched
and paginated separately per type and then merged, which would produce
incorrect page boundaries whenever results span more than one type.
"""

import json
from typing import Optional

from sqlalchemy import String, cast, func, literal, or_, select, union_all
from sqlalchemy.orm import Session

from web.models import CulturalResonance, CurrentsAnalysis, Study, WorkshopPrep

DETAIL_URL_PREFIXES = {
    "study": "/study/",
    "workshop": "/workshop/",
    "currents": "/currents/",
    "resonance": "/resonance/",
}


def _study_select(q: Optional[str]):
    stmt = select(
        Study.id.label("id"),
        literal("study").label("content_type"),
        cast(Study.reference, String).label("title"),
        cast(Study.engine, String).label("badge_label"),
        Study.created_at.label("created_at"),
    )
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Study.reference.ilike(like), Study.content.ilike(like)))
    return stmt


def _workshop_select(q: Optional[str]):
    stmt = select(
        WorkshopPrep.id.label("id"),
        literal("workshop").label("content_type"),
        cast(WorkshopPrep.reference, String).label("title"),
        cast(literal("Workshop"), String).label("badge_label"),
        WorkshopPrep.created_at.label("created_at"),
    )
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(WorkshopPrep.reference.ilike(like), WorkshopPrep.content.ilike(like)))
    return stmt


def _currents_select(q: Optional[str]):
    title_expr = func.coalesce(CurrentsAnalysis.headline_summary, literal("Theological News Analysis"))
    stmt = select(
        CurrentsAnalysis.id.label("id"),
        literal("currents").label("content_type"),
        cast(title_expr, String).label("title"),
        cast(literal("Currents"), String).label("badge_label"),
        CurrentsAnalysis.created_at.label("created_at"),
    )
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(
            CurrentsAnalysis.headline_summary.ilike(like),
            CurrentsAnalysis.story_context.ilike(like),
            CurrentsAnalysis.content.ilike(like),
        ))
    return stmt


def _resonance_select(q: Optional[str]):
    # title falls back to the raw `themes` JSON string when reference is
    # null; _format_title() below parses and joins it into a readable
    # string ("Hospitality, Empire") after the query runs - that
    # formatting can't be done portably in SQL.
    title_expr = func.coalesce(CulturalResonance.reference, CulturalResonance.themes)
    stmt = select(
        CulturalResonance.id.label("id"),
        literal("resonance").label("content_type"),
        cast(title_expr, String).label("title"),
        cast(literal("Resonance"), String).label("badge_label"),
        CulturalResonance.created_at.label("created_at"),
    )
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(
            CulturalResonance.reference.ilike(like),
            CulturalResonance.themes.ilike(like),
            CulturalResonance.content.ilike(like),
        ))
    return stmt


_SELECT_BUILDERS = {
    "study": _study_select,
    "workshop": _workshop_select,
    "currents": _currents_select,
    "resonance": _resonance_select,
}


def _format_title(content_type: str, raw_title: str) -> str:
    """
    Resonance rows with no `reference` fall back to their raw `themes`
    JSON string (e.g. '["hospitality", "empire"]') at the SQL level -
    parse and join it into a readable string here. Any other type, or a
    resonance row that already has a real reference, passes through
    unchanged.
    """
    if content_type != "resonance" or not raw_title.startswith("["):
        return raw_title
    try:
        themes = json.loads(raw_title)
        return ", ".join(t.title() for t in themes) if themes else raw_title
    except (json.JSONDecodeError, TypeError):
        return raw_title


def search_library(
    db: Session,
    content_type: Optional[str] = None,
    q: Optional[str] = None,
    page: int = 1,
    per_page: int = 12,
) -> dict:
    """
    Returns {"results": [...], "page": int, "total_pages": int,
    "total": int, "has_prev": bool, "has_next": bool}.

    Each result dict: {"content_type": str, "id": int, "title": str,
    "badge_label": str, "created_at": datetime, "url": str}.

    `content_type`: one of "study"/"workshop"/"currents"/"resonance", or
    any other value (including None/"") treated as "no filter" - all four
    types are included.
    """
    types_to_query = [content_type] if content_type in _SELECT_BUILDERS else list(_SELECT_BUILDERS.keys())

    selects = [_SELECT_BUILDERS[t](q) for t in types_to_query]
    combined = selects[0] if len(selects) == 1 else union_all(*selects)
    subquery = combined.subquery()

    total = db.execute(select(func.count()).select_from(subquery)).scalar()

    ordered = (
        select(subquery)
        .order_by(subquery.c.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = db.execute(ordered).all()

    results = []
    for row in rows:
        results.append({
            "content_type": row.content_type,
            "id": row.id,
            "title": _format_title(row.content_type, row.title),
            "badge_label": row.badge_label,
            "created_at": row.created_at,
            "url": f"{DETAIL_URL_PREFIXES[row.content_type]}{row.id}",
        })

    total_pages = (total + per_page - 1) // per_page if total else 0

    return {
        "results": results,
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "has_prev": page > 1,
        "has_next": page < total_pages,
    }
```

**This SQL construction is the single riskiest piece of code in this entire plan** — SQLAlchemy 2.0's `union_all()`/`subquery()` API has real sharp edges (e.g. column type mismatches across union branches on strict backends, subtleties in selecting from a subquery). Treat the code above as a strong starting point, not verbatim gospel: if running the tests in Step 4 below produces a SQLAlchemy error (not a test assertion failure — an actual exception), debug and fix the query construction. The parts that ARE fixed requirements, not up for reinterpretation: the function signature, the return shape, the per-type searchable-field mapping (Step 1's tests encode this), and the title/badge_label logic per the design spec's table. How exactly the union/subquery/count is constructed in SQLAlchemy is not sacred if it doesn't run correctly.

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
python3 -m pytest tests/test_library_service.py -v
```

Expected: all 8 PASS. If you hit a SQLAlchemy exception (not an assertion failure), see the note above — debug the query construction, re-run, and note what you changed and why in your report.

- [ ] **Step 5: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS, 0 failures.

- [ ] **Step 6: Commit**

```bash
git add web/services/library_service.py tests/test_library_service.py
git commit -m "Add unified Library query spanning all four content types

search_library() combines Study, WorkshopPrep, CurrentsAnalysis, and
CulturalResonance into one SQLAlchemy union_all() query, so pagination
is correct across the combined chronological result rather than four
separately-paginated lists glued together.

Resonance's title falls back to its themes list (joined into a readable
string) when reference is null - the only content type without a
guaranteed reference field."
```

---

### Task 2: Wire into `/browse` and rewrite the template

**Files:**
- Modify: `web/app.py:245-303` (the `/browse` route)
- Modify: `web/templates/browse.html` (full content rewrite)
- Modify: `web/static/css/styles.css` (one new badge rule)
- Modify: `tests/test_route_smoke.py`

**Interfaces:**
- Consumes: `search_library(db, content_type, q, page, per_page)` from Task 1, exact return shape as documented there.
- Produces: nothing consumed by later tasks — this is the last task in this plan and in Tier 1b.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_route_smoke.py`:

```python
def test_library_page_shows_all_content_types(client):
    response = client.get("/browse")
    assert response.status_code == 200


def test_library_page_type_filter(client):
    response = client.get("/browse?type=workshop")
    assert response.status_code == 200
```

- [ ] **Step 2: Run them to confirm they pass or fail as expected**

```bash
python3 -m pytest tests/test_route_smoke.py -v -k "test_library_page"
```

Expected: both currently PASS as written (the old `/browse` route already returns 200 regardless of query params it doesn't recognize — FastAPI ignores unrecognized query params rather than erroring). This step is a baseline check, not a red/green TDD gate — the real verification for this task is Step 5 below, confirming the *content* actually reflects the unified query, not just that the route still returns 200.

- [ ] **Step 3: Update the `/browse` route**

In `web/app.py`, the current route reads:

```python
@app.get("/browse", response_class=HTMLResponse)
async def browse_studies(
    request: Request,
    page: int = 1,
    engine: str = None,
    source: str = None,
    q: str = None,
    db: Session = Depends(get_db)
):
    """
    Browse studies page - lists all studies with filtering and search
    """
    # Calculate pagination
    per_page = config.studies_per_page
    skip = (page - 1) * per_page

    # Build query
    query = db.query(Study)

    # Apply filters
    if engine:
        query = query.filter(Study.engine == engine)
    if source:
        query = query.filter(Study.source == source)
    if q and q.strip():
        # .ilike() is case-insensitive on both SQLite and Postgres via
        # SQLAlchemy's dialect handling. Searches the raw reference column
        # (not reference_normalized) since older rows predating that
        # column's migration may have it NULL.
        search_term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Study.reference.ilike(search_term),
                Study.content.ilike(search_term),
            )
        )

    # Order by most recent first
    query = query.order_by(Study.created_at.desc())

    # Get total count before pagination
    total = query.count()

    # Get studies for this page
    studies_list = query.offset(skip).limit(per_page).all()

    # Calculate pagination info
    total_pages = (total + per_page - 1) // per_page
    has_prev = page > 1
    has_next = page < total_pages

    return templates.TemplateResponse("browse.html", {
        "request": request,
        "studies": studies_list,
        "page": page,
        "total_pages": total_pages,
        "has_prev": has_prev,
        "has_next": has_next,
        "total": total,
        "engine_filter": engine,
        "source_filter": source,
        "search_query": q or ""
    })
```

Replace it with:

```python
@app.get("/browse", response_class=HTMLResponse)
async def browse_studies(
    request: Request,
    page: int = 1,
    type: str = None,
    q: str = None,
    db: Session = Depends(get_db)
):
    """
    Library page - unified browse across studies, workshop preps,
    currents analyses, and resonance results
    """
    from .services.library_service import search_library

    search_term = q.strip() if q and q.strip() else None
    result = search_library(db, content_type=type, q=search_term, page=page, per_page=config.studies_per_page)

    return templates.TemplateResponse("browse.html", {
        "request": request,
        "results": result["results"],
        "page": result["page"],
        "total_pages": result["total_pages"],
        "has_prev": result["has_prev"],
        "has_next": result["has_next"],
        "total": result["total"],
        "type_filter": type,
        "search_query": search_term or ""
    })
```

Note: `type` as a parameter name shadows the Python builtin `type()` within this function's scope. This matches the plan's own query-param naming decision (the URL param is literally `?type=...`) and the existing codebase already does the same thing elsewhere with other builtin-shadowing param names (e.g. this same file's `id` parameters) — don't rename it to avoid the shadow; nothing in this function needs the builtin.

- [ ] **Step 4: Add the `.workshop-badge` CSS rule**

`.currents-badge` and `.resonance-badge` already exist and are reused as-is for their result types. Workshop preps need one new badge class, since the existing `.lens-badge` is for per-lens styling on a different page, not a generic "Workshop" identity. Add to `web/static/css/styles.css`, directly after the existing `.currents-badge` rule (search for `.currents-badge {` to find it):

```css
.workshop-badge {
    display: inline-flex;
    align-items: center;
    gap: var(--space-xs);
    padding: 0.3rem 0.9rem;
    font-family: var(--font-display);
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    border-radius: var(--radius-sm);
    background: var(--color-ink);
    color: var(--color-parchment);
}
```

This matches `.currents-badge`/`.resonance-badge`'s exact shape but with a solid `--color-ink` background instead of a gradient (no dedicated "Workshop" color exists in the token set, and a solid neutral ink badge stays visually distinct from Study's three engine colors and from Currents' navy/Resonance's gold gradients, without inventing a new design token).

- [ ] **Step 5: Rewrite the template**

Replace the entire `{% block content %}...{% endblock %}` body of `web/templates/browse.html`:

```html
{% block content %}
<div class="container">
    <div class="page-header">
        <h1>Library</h1>
        <p>{{ total }} result{% if total != 1 %}s{% endif %} total{% if search_query %} matching "{{ search_query }}"{% endif %}</p>
    </div>

    <form class="search-bar" action="/browse" method="get">
        {% if type_filter %}<input type="hidden" name="type" value="{{ type_filter }}">{% endif %}
        <input type="text" name="q" value="{{ search_query }}" placeholder="Search reference or content...">
        <button type="submit" class="btn btn-secondary">Search</button>
        {% if search_query %}
        <a href="/browse{% if type_filter %}?type={{ type_filter }}{% endif %}" class="search-clear">Clear</a>
        {% endif %}
    </form>

    <div class="browse-layout">
        <aside class="browse-sidebar">
            <h3>Filter</h3>

            <div class="filter-group">
                <h4>Type</h4>
                <div class="filter-options">
                    <a href="/browse{% if search_query %}?q={{ search_query }}{% endif %}" class="filter-link {% if not type_filter %}active{% endif %}">
                        All
                    </a>
                    <a href="/browse?type=study{% if search_query %}&q={{ search_query }}{% endif %}" class="filter-link {% if type_filter == 'study' %}active{% endif %}">
                        Studies
                    </a>
                    <a href="/browse?type=workshop{% if search_query %}&q={{ search_query }}{% endif %}" class="filter-link {% if type_filter == 'workshop' %}active{% endif %}">
                        Workshop
                    </a>
                    <a href="/browse?type=currents{% if search_query %}&q={{ search_query }}{% endif %}" class="filter-link {% if type_filter == 'currents' %}active{% endif %}">
                        Currents
                    </a>
                    <a href="/browse?type=resonance{% if search_query %}&q={{ search_query }}{% endif %}" class="filter-link {% if type_filter == 'resonance' %}active{% endif %}">
                        Resonance
                    </a>
                </div>
            </div>
        </aside>

        <div class="browse-main">
            {% if results %}
            <div class="studies-grid">
                {% for item in results %}
                <div class="study-card">
                    <a href="{{ item.url }}" class="study-card-link">
                        <div class="study-card-header">
                            {% if item.content_type == 'study' %}
                            <span class="engine-badge engine-{{ item.badge_label }}">{{ item.badge_label }}</span>
                            {% elif item.content_type == 'workshop' %}
                            <span class="workshop-badge">{{ item.badge_label }}</span>
                            {% elif item.content_type == 'currents' %}
                            <span class="currents-badge">{{ item.badge_label }}</span>
                            {% else %}
                            <span class="resonance-badge">{{ item.badge_label }}</span>
                            {% endif %}
                            <span class="study-card-date">{{ item.created_at.strftime('%b %d, %Y') }}</span>
                        </div>
                        <h3 class="study-card-reference">{{ item.title }}</h3>
                    </a>
                </div>
                {% endfor %}
            </div>

            {% if total_pages > 1 %}
            <div class="pagination">
                {% if has_prev %}
                <a href="/browse?page={{ page - 1 }}{% if type_filter %}&type={{ type_filter }}{% endif %}{% if search_query %}&q={{ search_query }}{% endif %}"
                   class="btn btn-secondary">← Previous</a>
                {% endif %}

                <span class="pagination-info">Page {{ page }} of {{ total_pages }}</span>

                {% if has_next %}
                <a href="/browse?page={{ page + 1 }}{% if type_filter %}&type={{ type_filter }}{% endif %}{% if search_query %}&q={{ search_query }}{% endif %}"
                   class="btn btn-secondary">Next →</a>
                {% endif %}
            </div>
            {% endif %}

            {% else %}
            <div class="empty-state">
                <h2>No results found</h2>
                {% if search_query %}
                <p>Nothing matches "{{ search_query }}". Try a different term, or <a href="/browse{% if type_filter %}?type={{ type_filter }}{% endif %}">clear the search</a>.</p>
                {% else %}
                <p>Try adjusting your filters or <a href="/generate">generate a new study</a>.</p>
                {% endif %}
            </div>
            {% endif %}
        </div>
    </div>
</div>
{% endblock %}
```

Also update the title block near the top of the file:

```html
{% block title %}Library | Lectionary Engines{% endblock %}
```

Note: the `.study-card`/`.studies-grid`/`.study-card-link`/`.study-card-header`/`.study-card-date`/`.study-card-reference` CSS classes keep their existing "study-" prefixed names even though this template now renders all four content types through them — they were already generic in shape (a card with a badge, date, and title), just narrowly named, and this template is the only place they're used. Renaming them is out of scope for this task; do not rename them or add parallel new classes.

The old `.study-card-meta` (word count / translation / source line) is dropped from the markup, since that data doesn't exist uniformly across all four types — do not leave a partially-populated meta line in its place.

- [ ] **Step 6: Run the tests**

```bash
python3 -m pytest tests/test_route_smoke.py -v -k "test_library_page"
python3 -m pytest tests/ -v
```

Expected: both new tests PASS, full suite PASS with 0 failures.

- [ ] **Step 7: Verify by eye**

Start the dev server (`uvicorn web.app:app --port 8123`, using the venv at the repo root), sign in, visit `/browse`. Confirm: page title reads "Library", the Type filter shows All/Studies/Workshop/Currents/Resonance, search works, and (if the local DB has any seed data across these tables) each result card shows the correct badge color/label for its type and links to the right detail page. If the local DB is empty (expected in a fresh checkout — this has been the case throughout this project's other pieces), confirm the empty state renders cleanly instead ("No results found... generate a new study").

- [ ] **Step 8: Commit**

```bash
git add web/app.py web/templates/browse.html web/static/css/styles.css tests/test_route_smoke.py
git commit -m "Unify /browse into the Library page across all four content types

Repurposes the existing /browse route and template to use Task 1's
search_library() instead of a Study-only query. Replaces the old
engine/source filters with one type selector (Study/Workshop/Currents/
Resonance) and keeps one shared search box. /workshop/browse and
/currents/browse are untouched.

One new CSS rule (.workshop-badge) - .currents-badge and .resonance-badge
already existed and are reused as-is."
```

---
