# Tier 1b — Engines Directory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new `/engines` page consolidating the three interpretation engines' existing descriptions into one dedicated, reachable-from-the-sidebar page.

**Architecture:** A new read-only FastAPI router (`web/routes/engines.py`) serving a single static Jinja template. Content is relocated verbatim from the existing homepage cards, not rewritten. The sidebar in `base.html` gets one new nav link.

**Tech Stack:** FastAPI (`APIRouter`), Jinja2, pytest + `httpx`'s `TestClient` (already available from Tier 1a).

## Global Constraints

- **Branch from `beta-tier-1a-restyle`, not `main`.** The navy sidebar `base.html` shell this plan modifies only exists on that branch (Tier 1a's PR is open, not yet merged). When setting up the worktree for this plan, create it from `beta-tier-1a-restyle` explicitly.
- **Content is relocated, not invented.** Every word of the three engine descriptions, methodology-step lists, and word-count/read-time meta lines must match `web/templates/index.html:17-51` exactly, with one documented exception: the Threshold step list's fourth bullet is "Embodied Practice" here (not "Embodied Practice + Tech" as it currently reads in `index.html`), per the already-approved copy-fix request noted in project memory and carried into Task 1 Step 6. No other new marketing copy.
- **`/generate?engine=X` preselect is out of scope.** The "Start a [Engine] study" button links to plain `/generate`. Query-param preselect belongs to a different Tier 1b piece (Workbench reflow).
- **Do not touch `index.html`.** It gets replaced wholesale when the Today homepage piece ships; duplicate/premature edits here create merge conflicts with that later work.
- **The existing test suite must stay green** (99 tests as of Tier 1a, plus this plan's additions).

---

### Task 1: `/engines` route, template, and tests

**Files:**
- Create: `web/routes/engines.py`
- Create: `web/templates/engines.html`
- Modify: `web/app.py:20` (import), `web/app.py:93` (router registration)
- Modify: `web/static/css/styles.css` (one new layout rule)
- Modify: `tests/test_route_smoke.py`

**Interfaces:**
- Consumes: `base.html`'s `title`/`content` blocks (unchanged, from Tier 1a); existing CSS classes `.container`, `.page-header` (see `web/templates/generate.html` for the pattern), `.engine-card`, `.btn`, `.btn-primary`, `.meta`, and the `--space-lg` token — all already defined in `styles.css` from Tier 1a, verify they still exist before using them, do not redefine.
- Produces: `GET /engines` route, `web/templates/engines.html`. Task 2 (nav integration) depends on this route existing so the new sidebar link has somewhere to point.

- [ ] **Step 1: Write the failing tests**

Add `"/engines"` to the `PAGES` list in `tests/test_route_smoke.py` (it already has a `client` fixture and a parametrized `test_page_renders` — this one line makes that test cover the new route too):

```python
PAGES = [
    "/",
    "/generate",
    "/browse",
    "/workshop",
    "/workshop/browse",
    "/currents",
    "/currents/browse",
    "/resonance",
    "/profiles",
    "/engines",
]
```

Then add a dedicated content test at the end of the file:

```python
def test_engines_page_lists_all_three_engines(client):
    response = client.get("/engines")
    assert response.status_code == 200
    body = response.text
    assert "Threshold" in body
    assert "Palimpsest" in body
    assert "Collision" in body
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
python3 -m pytest tests/test_route_smoke.py -v -k "engines"
```

Expected: both FAIL. `test_page_renders[/engines]` fails with a 404 (no route registered yet). `test_engines_page_lists_all_three_engines` fails the same way.

- [ ] **Step 3: Create the router**

Create `web/routes/engines.py`. This follows the same pattern as `web/routes/resonance.py` and `web/app.py`'s `/generate` route: no `response_class` needed, just return the `TemplateResponse` directly.

```python
"""
Engines routes - the static "about the three engines" directory page
"""

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from pathlib import Path

router = APIRouter()

WEB_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))


@router.get("/engines")
async def engines_directory(request: Request):
    """
    Engines directory - consolidated reference for all three interpretation
    engines. Fully static: no DB query, no template context beyond `request`.
    """
    return templates.TemplateResponse("engines.html", {"request": request})
```

- [ ] **Step 4: Register the router in `web/app.py`**

In `web/app.py`, change the routes import line (currently line 20):

```python
from .routes import studies, profiles, workshop, resonance, currents
```

to:

```python
from .routes import studies, profiles, workshop, resonance, currents, engines
```

Then, immediately after the existing `app.include_router(currents.router, tags=["currents"])` line (currently line 96), add:

```python
app.include_router(engines.router, tags=["engines"])
```

- [ ] **Step 5: Add the layout CSS rule**

The homepage's `.engines-grid` (in `web/static/css/styles.css`) is a 3-column grid meant for a compact card layout — this page wants each engine to have more room. Add this rule to `styles.css`, near the existing `.engines-grid` rule (search for `.engines-grid` to find it — add the new rule directly after it):

```css
.engines-directory-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-lg);
}
```

- [ ] **Step 6: Create the template**

Create `web/templates/engines.html`. This relocates the three engine blocks from `web/templates/index.html:17-51` verbatim (same heading text, same description paragraphs, same step lists, same meta lines) into a full-width stacked layout using the new `.engines-directory-list` class, and adds one new element per engine: a "Start a [Name] study" button.

```html
{% extends "base.html" %}

{% block title %}Engines | Lectionary Engines{% endblock %}

{% block content %}
<div class="container">
    <div class="page-header">
        <h1>Engines</h1>
        <p>Three hermeneutical frameworks, each a different way of reading the same text.</p>
    </div>

    <section class="engines-directory-list">
        <div class="engine-card">
            <h3>Threshold</h3>
            <p>Four progressive thresholds of engagement, culminating in a tech touchpoint. One core insight develops across all movements.</p>
            <ul>
                <li>Archaeological Dive</li>
                <li>Theological Combustion</li>
                <li>Present Friction</li>
                <li>Embodied Practice</li>
            </ul>
            <p class="meta">2,500-3,500 words | 20-30 min read</p>
            <a href="/generate" class="btn btn-primary">Start a Threshold study</a>
        </div>

        <div class="engine-card">
            <h3>Palimpsest</h3>
            <p>Five hermeneutical layers using the PaRDeS framework. Each layer visible through the others like a manuscript palimpsest.</p>
            <ul>
                <li>Peshat (Literal)</li>
                <li>Remez (Allegory)</li>
                <li>Derash (Tradition)</li>
                <li>Sod (Mystery)</li>
                <li>Incarnation (Contemporary)</li>
            </ul>
            <p class="meta">3,000-4,000 words | 25-35 min read</p>
            <a href="/generate" class="btn btn-primary">Start a Palimpsest study</a>
        </div>

        <div class="engine-card">
            <h3>Collision</h3>
            <p>Five-step collision process forcing unprecedented connections through randomized vectors from science, culture, philosophy, technology, and personal life.</p>
            <ul>
                <li>Anchor in Antiquity</li>
                <li>Collide with Now</li>
                <li>Navigate Rupture</li>
                <li>Crystallize Insight</li>
                <li>Release into Future</li>
            </ul>
            <p class="meta">3,000-5,000 words | Maximum intensity</p>
            <a href="/generate" class="btn btn-primary">Start a Collision study</a>
        </div>
    </section>
</div>
{% endblock %}
```

Note: the Threshold step list here reads "Embodied Practice" (not "Embodied Practice + Tech" as `index.html` currently has it) — this matches a pending copy-fix request already noted in project memory for `index.html`. Since this is a fresh relocation, not a copy of the unfixed line, use the corrected wording directly.

- [ ] **Step 7: Run the tests to confirm they pass**

```bash
python3 -m pytest tests/test_route_smoke.py -v -k "engines"
```

Expected: both PASS.

- [ ] **Step 8: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS, 0 failures. Do not hardcode an exact test count in your report — confirm 0 failures against whatever the baseline count is at execution time.

- [ ] **Step 9: Commit**

```bash
git add web/routes/engines.py web/templates/engines.html web/app.py web/static/css/styles.css tests/test_route_smoke.py
git commit -m "Add /engines directory page

Consolidates the three interpretation engines' descriptions, methodology
steps, and word-count/read-time metadata onto one dedicated page,
relocated verbatim from the homepage cards. Fully static: no DB query,
no new data model.

Corrects the Threshold step list's fourth bullet from 'Embodied Practice
+ Tech' to 'Embodied Practice' per prior copy-fix request."
```

---

### Task 2: Sidebar nav integration

**Files:**
- Modify: `web/templates/base.html:20` (sidebar nav)
- Modify: `tests/test_route_smoke.py`

**Interfaces:**
- Consumes: `GET /engines` from Task 1 (the link must point at a route that exists — Task 1 must be complete and merged before this task starts).
- Produces: nothing consumed by later tasks — this is the last task in this plan.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_route_smoke.py`:

```python
def test_sidebar_links_to_engines(client):
    response = client.get("/")
    assert response.status_code == 200
    assert 'href="/engines"' in response.text
```

- [ ] **Step 2: Run it to confirm it fails**

```bash
python3 -m pytest tests/test_route_smoke.py -v -k "test_sidebar_links_to_engines"
```

Expected: FAIL — `href="/engines"` is not yet in the rendered homepage.

- [ ] **Step 3: Add the nav link**

In `web/templates/base.html`, the sidebar nav currently reads (inside `<nav class="sidebar-nav">`):

```html
                <a href="/" class="sidebar-link {% if request.url.path == '/' %}active{% endif %}">Today</a>
                <a href="/generate" class="sidebar-link {% if request.url.path.startswith('/generate') %}active{% endif %}">Workbench</a>
                <a href="/browse" class="sidebar-link {% if request.url.path.startswith('/browse') or request.url.path.startswith('/study') %}active{% endif %}">Library</a>

                <div class="sidebar-divider"></div>
```

Change it to (one new line added, immediately after the Library link, still before the divider):

```html
                <a href="/" class="sidebar-link {% if request.url.path == '/' %}active{% endif %}">Today</a>
                <a href="/generate" class="sidebar-link {% if request.url.path.startswith('/generate') %}active{% endif %}">Workbench</a>
                <a href="/browse" class="sidebar-link {% if request.url.path.startswith('/browse') or request.url.path.startswith('/study') %}active{% endif %}">Library</a>
                <a href="/engines" class="sidebar-link {% if request.url.path.startswith('/engines') %}active{% endif %}">Engines</a>

                <div class="sidebar-divider"></div>
```

- [ ] **Step 4: Run the test to confirm it passes**

```bash
python3 -m pytest tests/test_route_smoke.py -v -k "test_sidebar_links_to_engines"
```

Expected: PASS.

- [ ] **Step 5: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS, 0 failures. `base.html` is shared by every page, so this is the real regression gate — a mistake here would show up as failures across many of the parametrized `test_page_renders` cases, not just the new test.

- [ ] **Step 6: Verify by eye**

Start the dev server (`uvicorn web.app:app --port 8123`, using the venv at the repo root), visit `/`, confirm "Engines" appears in the sidebar between Library and the first divider, then click it and confirm it highlights with the active-state blue rail and lands on the new page from Task 1.

- [ ] **Step 7: Commit**

```bash
git add web/templates/base.html tests/test_route_smoke.py
git commit -m "Add Engines link to sidebar nav

Placed in the primary group with Today/Workbench/Library, before the
first divider, per the Beta information architecture's grouping."
```

---
