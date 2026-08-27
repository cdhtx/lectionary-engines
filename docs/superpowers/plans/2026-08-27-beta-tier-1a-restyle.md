# Beta Tier 1a — Restyle In Place: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the entire existing site adopt the Beta visual identity — navy sidebar shell, Source Serif 4 + Inter typography, remapped engine colors — without adding routes or changing any application behavior.

**Architecture:** Rather than renaming ~2,546 lines of CSS that reference the current `--color-*` tokens, we add the authoritative Beta token set to `:root` and re-point the existing token names at it as a compatibility alias layer. One task recolors the whole site; later tasks refine specific components. `base.html` becomes a sidebar app-shell, and the two standalone templates (`login.html`, `admin_users.html`) are brought along separately since they do not extend it.

**Tech Stack:** Jinja2 templates, hand-written CSS (no framework, no build step), FastAPI serving static files. Fonts via Google Fonts `@import`. Tests: pytest, plus `httpx` for FastAPI's `TestClient`.

## Global Constraints

- **Strictly presentational.** Do not modify `web/routes/`, `web/services/`, `web/models.py`, or any file under `lectionary_engines/`. The only Python written in this plan is *test* code.
- **Design spec is binding:** `docs/superpowers/specs/2026-08-27-beta-workspace-redesign-design.md`. Token values there are authoritative.
- **Engine colors are remapped and must not be "corrected" back:** Threshold `#E95B13` (was plum), Palimpsest `#1565B5` (was forest green), Collision `#007D8A` (was sienna).
- **Aesthetic guardrail:** Do not make this look like a church website. No stained glass, crosses, praying hands, church photography, **parchment textures**, purple gradients, or inspirational stock imagery. Reference: editorial publishing + Linear/Notion product UI + biblical scholarship + antique cartography.
- **Nav may only link to routes that already exist.** Never ship a link that 404s. Engines, Signals, and Settings arrive in Tier 1b/2 — omit them now.
- **The existing 82 tests must stay green.** A failure means the presentational constraint was violated; that is signal, not noise.
- **Work on a branch**, not `main`. `base.html` is shared by every page and is the highest-blast-radius file in the codebase.

---

### Task 1: Test harness — token contract + route smoke tests

Build the safety net before touching anything. Undefined CSS variables fail *silently* in browsers, and `base.html` is shared by every page — both need automated detection.

**Files:**
- Modify: `pyproject.toml` (add `httpx` to the existing dev extra)
- Create: `tests/test_design_tokens.py`
- Create: `tests/test_route_smoke.py`

**Interfaces:**
- Consumes: nothing (first task)
- Produces: `tests/test_design_tokens.py` and `tests/test_route_smoke.py`, run by every later task as the regression gate.

- [ ] **Step 1: Create the working branch**

`base.html` is shared by every page. All of this work happens on a branch and merges as one coherent unit — never a half-restyled `main`.

```bash
cd ~/Documents/ClaudeCode/lectionary-engines
git checkout main && git pull
git checkout -b beta-tier-1a-restyle
```

- [ ] **Step 2: Add the test-only dependency**

In `pyproject.toml`, find the dev extra containing `pytest>=7.4.0` and add one line:

```toml
"httpx>=0.27.0",
```

This is test infrastructure only — it does not go in `requirements.txt` and does not ship to production.

- [ ] **Step 3: Install it**

```bash
cd ~/Documents/ClaudeCode/lectionary-engines && source venv/bin/activate && pip install httpx
```

- [ ] **Step 4: Write the design token contract test**

Create `tests/test_design_tokens.py`:

```python
"""
Contract tests for the CSS design token layer.

Undefined CSS custom properties fail silently in browsers - the property is
simply dropped and the element renders with an inherited or initial value.
These tests turn that silent failure into a loud one.
"""

import re
from pathlib import Path

CSS_PATH = Path(__file__).parent.parent / "web" / "static" / "css" / "styles.css"


def _css() -> str:
    return CSS_PATH.read_text()


def _root_block() -> str:
    """The contents of the first :root { ... } block."""
    match = re.search(r":root\s*\{(.*?)\n\}", _css(), re.DOTALL)
    assert match, ":root block not found in styles.css"
    return match.group(1)


def _defined_tokens() -> set:
    return set(re.findall(r"(--[\w-]+)\s*:", _root_block()))


def _used_tokens() -> set:
    return set(re.findall(r"var\(\s*(--[\w-]+)", _css()))


def test_every_referenced_token_is_defined():
    missing = _used_tokens() - _defined_tokens()
    assert not missing, f"CSS variables used but never defined: {sorted(missing)}"


def test_engine_colors_use_beta_palette():
    root = _root_block()
    assert "#E95B13" in root, "Threshold must be burnt orange #E95B13"
    assert "#1565B5" in root, "Palimpsest must be primary blue #1565B5"
    assert "#007D8A" in root, "Collision must be deep teal #007D8A"


def test_old_engine_colors_are_gone():
    # Guards against a well-meaning revert toward the pre-Beta palette.
    root = _root_block()
    for old_hex, name in [("#6b2d5b", "plum"), ("#1e5631", "forest"), ("#8b2500", "sienna")]:
        assert old_hex not in root.lower(), f"Pre-Beta {name} {old_hex} still present"
```

- [ ] **Step 5: Run it — expect failures**

```bash
cd ~/Documents/ClaudeCode/lectionary-engines && source venv/bin/activate && python3 -m pytest tests/test_design_tokens.py -v
```

Expected: `test_engine_colors_use_beta_palette` and `test_old_engine_colors_are_gone` FAIL (Beta tokens do not exist yet). `test_every_referenced_token_is_defined` should PASS — the current stylesheet is internally consistent, and that is exactly the invariant we must not break.

- [ ] **Step 6: Write the route smoke test**

Create `tests/test_route_smoke.py`:

```python
"""
Smoke tests: every parameter-free page renders.

base.html is shared by every page in the app, so a mistake there breaks
everything at once. These tests make that immediate and obvious.

Auth note: AuthMiddleware only checks that the session cookie decodes -
it does not verify the user exists - so a signed cookie is sufficient.
"""

import pytest
from fastapi.testclient import TestClient

from web.app import app
from web.auth import create_session_cookie, COOKIE_NAME

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
]


@pytest.fixture
def client():
    c = TestClient(app)
    c.cookies.set(COOKIE_NAME, create_session_cookie(1))
    return c


@pytest.mark.parametrize("path", PAGES)
def test_page_renders(client, path):
    response = client.get(path)
    assert response.status_code == 200, f"{path} returned {response.status_code}"
    assert "<html" in response.text.lower(), f"{path} did not return an HTML document"


def test_login_page_renders_without_auth():
    # login is a public path and must render for a signed-out visitor.
    response = TestClient(app).get("/login")
    assert response.status_code == 200


def test_health_endpoint():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
```

- [ ] **Step 7: Run it — expect all green**

```bash
python3 -m pytest tests/test_route_smoke.py -v
```

Expected: all PASS. This captures the pre-change baseline. If anything fails now, stop and investigate before restyling — you would be building on a broken foundation.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml tests/test_design_tokens.py tests/test_route_smoke.py
git commit -m "Add design token contract and route smoke tests

Safety net for the Beta restyle. The token test catches undefined CSS
variables, which fail silently in browsers. The smoke tests catch
breakage in base.html, which every page shares.

Two token tests fail by design until the Beta palette lands."
```

---

### Task 2: Beta design tokens + compatibility alias layer

The single highest-leverage change: recolors the entire site at once.

**Files:**
- Modify: `web/static/css/styles.css:16-69` (the `:root` block), plus removal at `:72-96`

**Interfaces:**
- Consumes: token tests from Task 1
- Produces: Beta tokens (`--navy-*`, `--ivory-*`, `--ink-*`, `--blue-*`, `--orange-*`, `--teal-*`, `--threshold`, `--palimpsest`, `--collision`, `--gold-*`, `--border-*`, `--surface-*`, `--shadow-*`, `--radius-*`, `--sidebar-width`, `--content-max`) plus every legacy `--color-*` name preserved as an alias. Later tasks may use either, but should prefer Beta names in new CSS.

- [ ] **Step 1: Replace the `:root` block**

Replace lines 16-69 of `web/static/css/styles.css` entirely with:

```css
:root {
    /* ========================================================================
       BETA DESIGN TOKENS (authoritative)
       See docs/superpowers/specs/2026-08-27-beta-workspace-redesign-design.md
       ======================================================================== */

    /* Backgrounds */
    --navy-950: #071B33;
    --navy-900: #0A2342;
    --navy-850: #0D2D52;
    --ivory-50: #FAF8F3;
    --ivory-100: #F6F2EA;
    --ivory-200: #EEE8DE;

    /* Text */
    --ink-950: #10233F;
    --ink-800: #24364D;
    --ink-600: #5E6B78;
    --ink-400: #8B949E;

    /* Primary accents */
    --blue-600: #1565C0;
    --blue-500: #1976D2;
    --blue-400: #3B8EDB;
    --orange-600: #E55300;
    --orange-500: #F36C12;
    --orange-400: #FF8A35;
    --teal-700: #006C78;
    --teal-600: #008797;
    --teal-500: #13A6B5;

    /* Engine colors - REMAPPED from the pre-Beta palette. Do not revert. */
    --threshold: #E95B13;
    --palimpsest: #1565B5;
    --collision: #007D8A;

    /* Theological accent */
    --gold-500: #C9962C;
    --gold-300: #E2BC63;

    /* Borders and surfaces */
    --border-light: #DED8CF;
    --border-medium: #CBC3B8;
    --surface-white: #FFFDFC;
    --surface-muted: #F4F0E9;

    /* States */
    --success: #287A57;
    --warning: #D9951E;
    --danger: #A93B2A;

    /* Shadows */
    --shadow-sm: 0 2px 8px rgba(12, 32, 54, 0.06);
    --shadow-md: 0 8px 24px rgba(12, 32, 54, 0.09);
    --shadow-lg: 0 18px 50px rgba(12, 32, 54, 0.13);

    /* Layout */
    --sidebar-width: 188px;
    --content-max: 1440px;

    /* Radii - larger than pre-Beta (was 3/6/12), but still restrained.
       No giant SaaS marshmallows. */
    --radius-sm: 6px;
    --radius-md: 10px;
    --radius-lg: 14px;

    /* Typography - Task 3 repoints these to Source Serif 4 + Inter */
    --font-display: 'Cinzel', serif;
    --font-heading: 'Cormorant Garamond', serif;
    --font-body: 'Crimson Pro', serif;
    --font-mono: 'SF Mono', 'Monaco', 'Consolas', monospace;

    /* Spacing */
    --space-xs: 0.5rem;
    --space-sm: 1rem;
    --space-md: 1.5rem;
    --space-lg: 2rem;
    --space-xl: 3rem;
    --space-2xl: 5rem;

    /* Transitions */
    --transition-fast: 0.15s ease;
    --transition-medium: 0.3s ease;
    --transition-slow: 0.5s ease;

    /* ========================================================================
       LEGACY ALIAS LAYER
       ~2,500 lines of existing CSS reference these names. Rather than
       rewriting every line (large, risky, and easy to half-finish), the old
       names are preserved and re-pointed at the Beta palette. The whole site
       inherits the new look with no other edits.

       New CSS should use the Beta tokens above directly.
       ======================================================================== */
    --color-parchment: var(--ivory-50);
    --color-parchment-light: var(--surface-white);
    --color-parchment-dark: var(--ivory-200);

    --color-ink: var(--ink-950);
    --color-ink-light: var(--ink-800);
    --color-ink-muted: var(--ink-600);

    --color-gold: var(--gold-500);
    --color-gold-light: var(--gold-300);
    --color-gold-muted: rgba(201, 150, 44, 0.15);

    --color-threshold: var(--threshold);
    --color-threshold-light: var(--orange-400);
    --color-palimpsest: var(--palimpsest);
    --color-palimpsest-light: var(--blue-400);
    --color-collision: var(--collision);
    --color-collision-light: var(--teal-500);

    /* Resonance and Currents are surfaces, not engines. The spec assigns no
       colors for them; these are judgment calls kept in the Beta family. */
    --color-resonance: var(--gold-500);
    --color-resonance-light: var(--gold-300);
    --color-currents: var(--navy-900);
    --color-currents-light: var(--navy-850);

    --color-border: var(--border-light);
    --color-border-strong: var(--border-medium);
    --color-shadow: rgba(12, 32, 54, 0.06);
    --color-shadow-strong: rgba(12, 32, 54, 0.13);
}
```

- [ ] **Step 2: Remove the parchment texture**

The guardrails forbid parchment textures. The current `body` rule carries a noise SVG, and `body::before` layers parchment radial gradients over the whole page. Both go.

Replace the `body { ... }` rule and delete the entire `body::before { ... }` rule (currently lines ~72-96) with:

```css
/* Base Body Styles */
body {
    font-family: var(--font-body);
    font-size: 18px;
    line-height: 1.7;
    color: var(--color-ink);
    background-color: var(--color-parchment);
    min-height: 100vh;
}
```

Delete the `/* Subtle page texture overlay */` comment along with the `body::before` block.

- [ ] **Step 3: Run the token tests**

```bash
python3 -m pytest tests/test_design_tokens.py -v
```

Expected: all 4 PASS. If `test_every_referenced_token_is_defined` fails, a legacy `--color-*` name was dropped from the alias layer — the failure message names it.

- [ ] **Step 4: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS (82 existing + 4 token + 11 smoke).

- [ ] **Step 5: Look at it**

```bash
source venv/bin/activate && uvicorn web.app:app --port 8123
```

Open `http://localhost:8123`. The site should be recognizably the same layout in the Beta palette: ivory background, navy-tinted ink, no paper texture. Engine badges should read orange / blue / teal. Stop the server when done.

- [ ] **Step 6: Commit**

```bash
git add web/static/css/styles.css
git commit -m "Adopt Beta design tokens via compatibility alias layer

Adds the authoritative Beta token set and re-points every legacy
--color-* name at it, so ~2,500 lines of existing CSS inherit the new
palette without being rewritten.

Engine colors remap: Threshold plum to burnt orange, Palimpsest forest
to primary blue, Collision sienna to deep teal.

Also removes the noise-SVG body texture and parchment gradient overlay -
the aesthetic guardrails explicitly forbid parchment textures."
```

---

### Task 3: Typography — the serif/grotesk split

The highest-leverage single change per the spec. The current design is *too much serif*, which is why it reads as journal rather than product. UI chrome becomes Inter; theological content stays serif.

**Files:**
- Modify: `web/static/css/styles.css:7` (the `@import`), the `:root` font tokens, and the four content containers

**Interfaces:**
- Consumes: token layer from Task 2
- Produces: `--font-editorial` (Source Serif 4, for scripture and study prose) and `--font-body` repointed to Inter (UI default).

- [ ] **Step 1: Swap the font import**

Replace line 7 of `styles.css`:

```css
@import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;0,8..60,700;1,8..60,400&family=Inter:wght@400;500;600;700&display=swap');
```

- [ ] **Step 2: Repoint the font tokens**

In the `:root` typography block from Task 2, replace the four font lines with:

```css
    /* Typography - two voices. UI says "software", content says "theology". */
    --font-editorial: 'Source Serif 4', Georgia, 'Times New Roman', serif;
    --font-ui: 'Inter', system-ui, -apple-system, sans-serif;

    /* Legacy aliases */
    --font-display: var(--font-editorial);
    --font-heading: var(--font-editorial);
    --font-body: var(--font-ui);
    --font-mono: 'SF Mono', 'Monaco', 'Consolas', monospace;
```

`--font-body` now resolves to Inter, so `body {}` and everything inheriting from it become the UI voice. Headings keep the editorial serif through `--font-display` / `--font-heading`.

- [ ] **Step 3: Set the body size for UI**

Inter at 18px reads oversized for interface text. In the `body {}` rule from Task 2, change:

- `font-size: 18px;` → `font-size: 15px;`
- `line-height: 1.7;` → `line-height: 1.5;`

- [ ] **Step 4: Keep generated content in the editorial voice**

Because `body` is now Inter at 15px, the four generated-content containers would inherit sans-serif at interface size. They must not — this is the reading surface.

Add **one** new rule immediately *before* the existing `.study-content {` rule (~line 936 pre-edit). Do not modify or delete the existing `.study-content` rule; this new rule only restores the editorial voice and reading size, and the existing rule's other declarations still apply.

```css
/* The reading surface keeps the editorial voice and reading size, even
   though the surrounding interface is Inter at 15px. */
.study-content,
.currents-content,
.workshop-content,
.resonance-content {
    font-family: var(--font-editorial);
    font-size: 18px;
    line-height: 1.7;
}
```

- [ ] **Step 5: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS.

- [ ] **Step 6: Verify both voices render**

Start the server and open a generated study (`/browse`, click any study). Confirm: sidebar/nav/buttons/metadata are sans-serif; the study prose and title are serif. That contrast is the deliverable — if everything looks like one font, the fonts are not loading. Check the browser devtools Network tab for the Google Fonts request.

- [ ] **Step 7: Commit**

```bash
git add web/static/css/styles.css
git commit -m "Split typography into editorial serif and UI grotesk

Source Serif 4 for scripture, study titles, and theological prose;
Inter for navigation, labels, metadata, and controls. Body size drops
to 15px for interface text while generated content keeps 18px/1.7 for
reading.

Per the spec this is the single highest-leverage visual change: the UI
now says software while the content says theology."
```

---

### Task 4: Create the missing 404 template

**Pre-existing bug, confirmed:** `404.html` is referenced by `web/app.py`, `web/routes/currents.py`, and `web/routes/workshop.py`, but the file does not exist. Every not-found path currently raises `TemplateNotFound` → HTTP 500 instead of rendering a 404. Fixing it is a template change, squarely inside this tier's scope.

**Files:**
- Create: `web/templates/404.html`
- Modify: `tests/test_route_smoke.py`

**Interfaces:**
- Consumes: `base.html` (extends it)
- Produces: a working 404 page; template context variable `message` (string, optional).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_route_smoke.py`:

```python
def test_missing_study_renders_404_not_500(client):
    response = client.get("/study/99999999")
    assert response.status_code == 404, (
        f"Expected 404, got {response.status_code}. A 500 here means the "
        "404.html template is missing."
    )


def test_missing_currents_renders_404_not_500(client):
    response = client.get("/currents/99999999")
    assert response.status_code == 404


def test_missing_workshop_prep_renders_404_not_500(client):
    response = client.get("/workshop/99999999")
    assert response.status_code == 404
```

- [ ] **Step 2: Run them to confirm they fail**

```bash
python3 -m pytest tests/test_route_smoke.py -k "404" -v
```

Expected: FAIL. The error will be `jinja2.exceptions.TemplateNotFound: 404.html`, surfacing as a 500.

- [ ] **Step 3: Create the template**

Create `web/templates/404.html`:

```html
{% extends "base.html" %}

{% block title %}Not Found | Lectionary Engines{% endblock %}

{% block content %}
<div class="container">
    <div class="empty-state">
        <h1>Not found</h1>
        <p>{{ message or "That page does not exist." }}</p>
        <p>
            <a href="/browse" class="btn btn-secondary">Browse the library</a>
            <a href="/" class="btn btn-primary">Go to start</a>
        </p>
    </div>
</div>
{% endblock %}
```

- [ ] **Step 4: Run the tests**

```bash
python3 -m pytest tests/test_route_smoke.py -k "404" -v
```

Expected: all 3 PASS.

- [ ] **Step 5: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add web/templates/404.html tests/test_route_smoke.py
git commit -m "Add missing 404.html template

Pre-existing bug: three route modules render 404.html on not-found, but
the template was never created - so every not-found path raised
TemplateNotFound and surfaced as a 500 rather than a 404.

Found while surveying templates for the Beta restyle."
```

---

### Task 5: base.html app shell + sidebar

The structural heart of Tier 1a, and the highest-risk change in the plan — every page inherits this file.

**Files:**
- Modify: `web/templates/base.html` (full rewrite of the body)
- Modify: `web/static/css/styles.css` (add app-shell and sidebar rules)

**Interfaces:**
- Consumes: Beta tokens (Task 2), fonts (Task 3)
- Produces: `.app-shell`, `.sidebar`, `.sidebar-nav`, `.sidebar-link`, `.sidebar-link.active`, `.main-content` CSS classes; Jinja blocks `title`, `extra_head`, `content`, `extra_scripts` (unchanged names — child templates must keep working untouched).

- [ ] **Step 1: Rewrite base.html**

Replace the entire contents of `web/templates/base.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Lectionary Engines{% endblock %}</title>
    <link rel="stylesheet" href="/static/css/styles.css">
    {% block extra_head %}{% endblock %}
</head>
<body>
    <div class="app-shell">
        <aside class="sidebar">
            <a href="/" class="brand">
                <span class="brand-mark">LE</span>
                <span class="brand-name">Lectionary<br>Engines</span>
            </a>

            <nav class="sidebar-nav">
                <a href="/" class="sidebar-link {% if request.url.path == '/' %}active{% endif %}">Today</a>
                <a href="/generate" class="sidebar-link {% if request.url.path.startswith('/generate') %}active{% endif %}">Workbench</a>
                <a href="/browse" class="sidebar-link {% if request.url.path.startswith('/browse') or request.url.path.startswith('/study') %}active{% endif %}">Library</a>

                <div class="sidebar-divider"></div>

                <a href="/workshop" class="sidebar-link {% if request.url.path.startswith('/workshop') %}active{% endif %}">Workshop</a>
                <a href="/currents" class="sidebar-link {% if request.url.path.startswith('/currents') %}active{% endif %}">Currents</a>
                <a href="/resonance" class="sidebar-link {% if request.url.path.startswith('/resonance') %}active{% endif %}">Resonance</a>

                <div class="sidebar-divider"></div>

                <a href="/profiles" class="sidebar-link {% if request.url.path.startswith('/profiles') %}active{% endif %}">Profiles</a>
            </nav>

            <form action="/logout" method="POST" class="sidebar-signout">
                <button type="submit" class="sidebar-link sidebar-link--button">Sign out</button>
            </form>
        </aside>

        <main class="main-content">
            {% block content %}{% endblock %}
        </main>
    </div>

    {% block extra_scripts %}{% endblock %}
</body>
</html>
```

Note: Engines, Signals, and Settings are deliberately absent — those routes do not exist yet, and the guardrail is that nav must never link to a page that is not there.

- [ ] **Step 2: Add app-shell and sidebar CSS**

Add to `styles.css`, immediately after the `.container` rule (~line 99 post-edit):

```css
/* ============================================================================
   App Shell
   ============================================================================ */

.app-shell {
    display: grid;
    grid-template-columns: var(--sidebar-width) 1fr;
    min-height: 100vh;
}

.main-content {
    width: 100%;
    max-width: var(--content-max);
    margin: 0 auto;
    padding: 28px 36px 64px;
}

/* ============================================================================
   Sidebar
   ============================================================================ */

.sidebar {
    position: sticky;
    top: 0;
    height: 100vh;
    display: flex;
    flex-direction: column;
    background: linear-gradient(180deg, #06182E 0%, #082445 55%, #061A31 100%);
    color: rgba(255, 255, 255, 0.86);
    padding: 28px 16px;
}

.brand {
    display: block;
    text-decoration: none;
    margin-bottom: 34px;
}

.brand-mark {
    display: block;
    color: var(--orange-400);
    font-family: var(--font-editorial);
    font-size: 2.8rem;
    line-height: 1;
    letter-spacing: 0.02em;
}

.brand-name {
    display: block;
    margin-top: 6px;
    color: rgba(255, 255, 255, 0.62);
    font-family: var(--font-ui);
    font-size: 0.62rem;
    font-weight: 600;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    line-height: 1.5;
}

.sidebar-nav {
    display: flex;
    flex-direction: column;
    gap: 2px;
}

.sidebar-link {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 11px 12px;
    border-radius: var(--radius-sm);
    color: rgba(255, 255, 255, 0.88);
    font-family: var(--font-ui);
    font-size: 0.9rem;
    text-decoration: none;
    transition: background var(--transition-fast), color var(--transition-fast);
}

.sidebar-link:hover {
    background: rgba(255, 255, 255, 0.07);
    color: #fff;
}

/* The inset blue rail is what makes this read as software rather than a
   styled ecclesiastical website. */
.sidebar-link.active {
    background: rgba(35, 105, 185, 0.25);
    box-shadow: inset 3px 0 0 var(--blue-400);
    color: #fff;
}

.sidebar-link--button {
    width: 100%;
    background: none;
    border: none;
    cursor: pointer;
    text-align: left;
    font-size: 0.9rem;
}

.sidebar-divider {
    height: 1px;
    margin: 14px 12px;
    background: rgba(255, 255, 255, 0.10);
}

.sidebar-signout {
    margin-top: auto;
    padding-top: 20px;
}
```

- [ ] **Step 3: Neutralize the old header and footer CSS**

The `header`, `.navbar`, `.nav-brand`, `.nav-menu`, `.nav-link`, and `footer` rules (Header and Navigation section, ~line 106; Footer section, ~line 1263) now style markup that no longer exists. Leaving them is harmless but confusing.

Add a short comment above the Header and Navigation section marking it dead, and above the Footer section likewise:

```css
/* NOTE: superseded by the app shell in Tier 1a. The <header>/<nav>/<footer>
   markup these rules targeted no longer exists in base.html. Kept
   temporarily; safe to delete once Tier 1b settles the layout. */
```

Do not delete the rules in this task — deleting ~150 lines of CSS while also restructuring the shell makes a bisect harder if something breaks.

- [ ] **Step 4: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS. The smoke tests are the real gate here — they exercise every page against the new shell.

- [ ] **Step 5: Verify every page by eye**

Start the server and visit each: `/`, `/generate`, `/browse`, `/workshop`, `/workshop/browse`, `/currents`, `/currents/browse`, `/resonance`, `/profiles`, plus one study, one currents analysis, one workshop prep, and one resonance result from the Library.

For each, confirm: sidebar renders, the correct nav item shows the active rail, content is not overlapped or clipped, and no horizontal scrollbar appears.

- [ ] **Step 6: Commit**

```bash
git add web/templates/base.html web/static/css/styles.css
git commit -m "Convert base.html into a navy sidebar app shell

Replaces the horizontal header/footer with a persistent sidebar using
Beta nomenclature: Today, Workbench, Library, then Workshop/Currents/
Resonance, then Profiles. Active state uses the inset blue rail.

Nav links only to routes that already exist - Engines, Signals, and
Settings are deliberately omitted until Tier 1b/2 create them, so no
link 404s.

Old header/nav/footer rules are marked superseded rather than deleted,
to keep this commit bisectable."
```

---

### Task 6: Standalone templates — login and admin

`login.html` and `admin_users.html` do not extend `base.html`, so they inherited none of the shell work and will look pre-Beta.

**Files:**
- Modify: `web/templates/login.html`
- Modify: `web/templates/admin_users.html`

**Interfaces:**
- Consumes: Beta tokens, fonts
- Produces: nothing consumed by later tasks

- [ ] **Step 1: Read both files**

```bash
cat web/templates/login.html
cat web/templates/admin_users.html
```

Note every inline `style` attribute, `<style>` block, and hardcoded color. These are what will look wrong.

- [ ] **Step 2: Update login.html**

Login is a public, signed-out page — it must NOT get the sidebar (there is nothing to navigate to). Keep it a centered card, restyled.

Replace any hardcoded colors and fonts with Beta tokens. Specifically:
- Any cream/parchment hex → `var(--ivory-50)`
- Any dark text hex → `var(--ink-950)`
- Any serif `font-family` on form controls, buttons, and labels → `var(--font-ui)`
- The product name / heading → `var(--font-editorial)`
- Any `border` color → `var(--border-light)`
- Any `border-radius` → `var(--radius-sm)` or `var(--radius-md)`

If the file has no stylesheet link, ensure it has `<link rel="stylesheet" href="/static/css/styles.css">` in its `<head>` so the tokens resolve.

- [ ] **Step 3: Update admin_users.html**

Same token substitutions. This page is behind Basic Auth and is a utility screen — it needs to be consistent and legible, not beautiful. Do not add the sidebar; it is reached directly, outside the main app flow.

- [ ] **Step 4: Verify both render**

```bash
python3 -m pytest tests/test_route_smoke.py -v
```

Then start the server, sign out, and confirm `/login` looks like it belongs to the Beta site.

- [ ] **Step 5: Commit**

```bash
git add web/templates/login.html web/templates/admin_users.html
git commit -m "Bring standalone templates onto the Beta palette

login.html and admin_users.html do not extend base.html, so they missed
the shell work. Both now use Beta tokens and the UI font. Neither gets
the sidebar: login is signed-out with nothing to navigate to, and admin
is reached directly outside the main app flow."
```

---

### Task 7: Component refinements

The Beta spec is specific about component treatment, and the current components are pre-Beta: heavy black buttons, tighter radii, no defined card elevation.

**Files:**
- Modify: `web/static/css/styles.css` (Buttons section ~line 260; card rules across the Engine Cards, Recent Studies, and Browse Layout sections; Search Bar section ~line 1071)

**Interfaces:**
- Consumes: Beta tokens
- Produces: refined `.btn`, `.btn-primary`, `.btn-secondary`, card, and search styles

- [ ] **Step 1: Restrain the buttons**

Per the spec, Beta does not use the heavy black buttons of the current site. Find the Buttons section and update the base `.btn`, `.btn-primary`, and `.btn-secondary` rules so that:

```css
.btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 9px 14px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-medium);
    background: var(--surface-white);
    color: var(--ink-950);
    font-family: var(--font-ui);
    font-size: 0.9rem;
    font-weight: 550;
    text-decoration: none;
    cursor: pointer;
    transition: all var(--transition-fast);
}

.btn:hover {
    background: var(--ivory-100);
    transform: translateY(-1px);
}

.btn-primary {
    background: var(--navy-900);
    color: #fff;
    border-color: var(--navy-900);
}

.btn-primary:hover {
    background: var(--navy-850);
}

.btn-secondary {
    background: var(--surface-white);
    color: var(--ink-950);
    border-color: var(--border-medium);
}
```

Preserve any existing `.btn-large` / `.btn--sm` size modifiers — only the color, border, font, and radius treatment changes.

- [ ] **Step 2: Soften the cards**

Cards should be barely elevated — no heavy shadows. Find the card-like rules (`.engine-card`, `.study-card`, `.profile-card`, `.current-chip` if present) and ensure each uses:

```css
    background: rgba(255, 255, 255, 0.58);
    border: 1px solid var(--border-light);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-sm);
```

with hover shifting only the border:

```css
    border-color: var(--border-medium);
```

Do not add `transform` on card hover — the spec calls for restraint here.

- [ ] **Step 3: Update the search field**

In the Search Bar section, update `.search-bar input[type="text"]`:

```css
.search-bar input[type="text"] {
    flex: 1;
    height: 42px;
    padding: 0 14px;
    border: 1px solid var(--border-light);
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.8);
    color: var(--ink-950);
    font-family: var(--font-ui);
    font-size: 0.95rem;
    box-shadow: var(--shadow-sm);
}

.search-bar input[type="text"]:focus {
    outline: none;
    border-color: var(--blue-400);
    box-shadow: 0 0 0 3px rgba(25, 118, 210, 0.10), var(--shadow-sm);
}
```

- [ ] **Step 4: Give engine badges the Beta treatment**

Find the Engine Badges section and ensure badges use the UI font, uppercase, tight letter-spacing, white text on the engine color:

```css
.engine-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 5px 10px;
    border-radius: 4px;
    font-family: var(--font-ui);
    font-size: 0.68rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: #fff;
}
```

Keep the existing `.engine-threshold` / `.engine-palimpsest` / `.engine-collision` background rules — they already resolve to the remapped Beta colors through the alias layer.

- [ ] **Step 5: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS.

- [ ] **Step 6: Verify**

Start the server. Check `/browse` (cards + search), `/generate` (buttons, engine cards), and a study page (badges, action bar buttons). Buttons should read as restrained product controls, not heavy blocks.

- [ ] **Step 7: Commit**

```bash
git add web/static/css/styles.css
git commit -m "Refine buttons, cards, search, and badges to Beta spec

Buttons become restrained product controls (light surface, thin border,
navy primary) rather than the heavy black blocks of the pre-Beta site.
Cards are barely elevated with hover shifting only the border. Search
gets the blue focus ring. Badges move to the UI font."
```

---

### Task 8: Full verification sweep

The plan's closing gate. Everything above is verified per-task; this confirms the whole surface together.

**Files:**
- None modified (verification only). Create `docs/superpowers/plans/2026-08-27-tier-1a-verification.md` to record results.

**Interfaces:**
- Consumes: everything
- Produces: a written record of what was checked

- [ ] **Step 1: Full automated suite**

```bash
cd ~/Documents/ClaudeCode/lectionary-engines && source venv/bin/activate && python3 -m pytest tests/ -v
```

Expected: all PASS — 82 pre-existing + 4 token + 14 smoke/404.

- [ ] **Step 2: Confirm no Python was touched**

```bash
git diff main --stat -- web/routes/ web/services/ web/models.py lectionary_engines/
```

Expected: **empty output.** Any result means the presentational constraint was violated — stop and review.

- [ ] **Step 3: Walk every page**

Start the server and visit each, confirming the sidebar renders, the right nav item is active, and nothing is clipped or overlapping:

| Path | Also check |
|---|---|
| `/` | landing content readable |
| `/generate` | engine cards, form controls, sliders |
| `/browse` | search field, cards, filter sidebar |
| `/browse?q=Ephesians` | search results + Clear link |
| `/workshop` | lens cards |
| `/workshop/browse` | list renders |
| `/currents` | headline fetch UI |
| `/currents/browse` | list renders |
| `/resonance` | theme input |
| `/profiles` | profile cards, edit modal opens |
| a study | serif prose, badges, actions bar, PDF/Share/Email |
| a currents analysis | expand/collapse still work |
| a workshop prep | renders |
| a resonance result | renders |
| `/study/99999999` | clean 404, not 500 |
| `/login` (signed out) | Beta styling, no sidebar |

- [ ] **Step 4: Check empty states**

Visit `/browse?q=zzzznotarealword` and confirm the empty state renders correctly in the new palette. Empty states are the most commonly missed case in a restyle.

- [ ] **Step 5: Check narrow viewport**

Resize to ~900px and ~500px wide. The sidebar grid is fixed at `188px 1fr` and will need attention on mobile. Record what breaks — **do not fix it in this task.** If mobile is broken, note it as Tier 1b scope; if it is acceptable, say so.

- [ ] **Step 6: Confirm one PDF still generates**

```bash
curl -s -o /tmp/verify.pdf -w "%{http_code}\n" -H "Cookie: le_session=$(python3 -c "
from dotenv import load_dotenv; load_dotenv()
from web.auth import create_session_cookie; print(create_session_cookie(1))")" \
  http://localhost:8123/study/38/pdf && file /tmp/verify.pdf
```

Expected: `200` and `PDF document`. PDF generation uses its own print stylesheet and should be unaffected — this confirms it.

- [ ] **Step 7: Write the verification record**

Create `docs/superpowers/plans/2026-08-27-tier-1a-verification.md` listing every path from Step 3 with a pass/fail note, the mobile findings from Step 5, and any deferred items.

- [ ] **Step 8: Commit and open the PR**

```bash
git add docs/superpowers/plans/2026-08-27-tier-1a-verification.md
git commit -m "Record Tier 1a verification sweep results"
git push -u origin beta-tier-1a-restyle
gh pr create --title "Beta Tier 1a: restyle in place" --body "$(cat <<'EOF'
Adopts the Beta visual identity across the entire existing site with no
new routes and no application-logic changes.

- Beta design tokens with a compatibility alias layer, so ~2,500 lines
  of existing CSS inherit the new palette without a rewrite
- Engine colors remapped: Threshold orange, Palimpsest blue, Collision teal
- Typography split: Source Serif 4 for content, Inter for interface
- base.html becomes a navy sidebar app shell
- Parchment texture removed (forbidden by the aesthetic guardrails)
- Fixes a pre-existing bug: 404.html was referenced by three route
  modules but never existed, so not-found paths returned 500

Verification record: docs/superpowers/plans/2026-08-27-tier-1a-verification.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Deferred to Tier 1b

Recorded here so they are not silently lost:

- **Mobile/responsive sidebar.** The `188px 1fr` grid needs a collapse behavior below ~768px. The existing Responsive Design section (~line 2350) targets the old header markup and will need rework.
- **Deleting the superseded header/nav/footer CSS.** Marked with comments in Task 5, left in place to keep commits bisectable.
- **Global search (⌘K), notifications, avatar menu.** Present in the mockup, no backing routes yet.
- **Engines, Signals, Settings nav items.** Omitted until their routes exist.
