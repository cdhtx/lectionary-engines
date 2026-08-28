# Tier 3 — Palimpsest Spatial Experience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn a Palimpsest study's five PaRDeS layers (Peshat, Remez, Derash, Sod, Incarnation) from indistinguishable markdown headers into addressable, spatially-navigable sections — a sticky left rail that tracks scroll position and lets a reader jump between layers.

**Architecture:** A new parser splits a Palimpsest study's existing flat markdown content into five named sections at view time (no database changes). The route wraps each section in an anchor, the template renders a rail nav beside the content, and a small vanilla-JS file highlights the active layer as the reader scrolls and smooth-scrolls on click. Threshold and Collision studies, and any Palimpsest study whose content doesn't cleanly parse, keep rendering exactly as they do today.

**Tech Stack:** Python (regex-based parsing, no new dependencies), Jinja2, existing `markdown` package (python-markdown), vanilla JS (`IntersectionObserver`), existing CSS custom-property design tokens.

## Global Constraints

- **Palimpsest only.** `study.engine == "palimpsest"` is the only branch that gets this treatment. Threshold and Collision studies must render identically to their current behavior — no shared code path changes their output.
- **Scroll-tracking left rail, not click-to-reveal-beside-text.** Content stays one continuous scroll; the rail is a navigation aid layered on top, not a restructuring of the reading flow.
- **No database migration.** `Study.content` (`web/models.py`) is not modified in shape or column. Nothing new is persisted. The parser runs against `study.content` at view time, every time.
- **`/study/{id}/pdf` is untouched.** PDF export keeps calling `markdown.Markdown(...).convert()` on the full flat content directly, exactly as it does today — no rail, no per-layer sections, no import from the new parser module.
- **Graceful fallback, not an error path.** Any Palimpsest study whose content doesn't parse into exactly five layers in order renders with today's exact behavior (one flat `study_html` blob, no rail) — this is the expected outcome for malformed content, not a bug to surface to the user.
- **Rail labels are hardcoded, not extracted from AI-generated text** — display labels never depend on the model's exact heading phrasing matching a specific format.
- **JS style:** match `web/static/js/content-actions.js`'s existing conventions exactly — an IIFE wrapper (`(function () { ... })();`), `var` declarations, `function` expressions, no arrow functions, no `const`/`let`. This is the established vanilla-JS style for this codebase's static assets.
- **The existing test suite must stay green** (133 tests at branch point — confirm the exact count via `python3 -m pytest tests/ -v` before starting, don't assume it hasn't drifted).

---

### Task 1: Palimpsest layer parser

**Files:**
- Create: `web/services/palimpsest_layers.py`
- Test: `tests/test_palimpsest_layers.py`

**Interfaces:**
- Produces: `parse_palimpsest_layers(content: str) -> Optional[dict]` — returns `None` if the content doesn't contain all five layer keywords as distinct `##`-level headings in the canonical order (Peshat, Remez, Derash, Sod, Incarnation), with no duplicates. On success, returns `{"intro_markdown": str, "layers": [{"key": str, "markdown": str}, ...]}` — exactly 5 entries in `layers`, in that order, each `key` one of `"peshat"`, `"remez"`, `"derash"`, `"sod"`, `"incarnation"`. Also produces the module-level constant `RAIL_LABELS: List[dict]` — `[{"key": "peshat", "label": "Peshat · Simple/Literal"}, ...]`, same 5 keys in the same order as `parse_palimpsest_layers`'s output, for Task 2's route to pass to the template unchanged. Task 2 imports both `parse_palimpsest_layers` and `RAIL_LABELS` from this module.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_palimpsest_layers.py`:

```python
"""
Tests for the Palimpsest layer parser: splits a Palimpsest study's flat
markdown content into its five named PaRDeS layers, so the study view
can render each as an addressable section for spatial navigation. See
docs/superpowers/specs/2026-08-28-tier-3-palimpsest-design.md.
"""

from web.services.palimpsest_layers import RAIL_LABELS, parse_palimpsest_layers


VALID_PALIMPSEST_MARKDOWN = """# Palimpsest Study: John 3:16-21

This text rewards layered reading because it moves from cosmic love to concrete judgment in a single breath.

## Layer One: Peshat (Simple/Literal)

John uses agape throughout. The Greek kosmos here means the whole created order, not merely humanity.

This is what the text says. Now we explore what it means.

## Layer Two: Remez (Hint/Allegory)

The lifting up of the Son of Man echoes the bronze serpent in Numbers 21 - healing through looking at the very thing that wounds.

The text hints at realities beyond itself. Now we see how communities have read these hints.

## Layer Three: Derash (Search/Interpretation)

Augustine reads this as pure grace; Wesley reads it as prevenient grace inviting response. Both readings persist because the text itself is generative, not because either resolves it.

Traditions differ, and rightly so. Now we enter the mystery that transcends all readings.

## Layer Four: Sod (Secret/Mystery)

Light entering darkness.

Not explained. Witnessed.

Sit for a moment in that light before turning the page.

## Layer Five: Incarnation (Contemporary Body)

### For Individuals in Transition

Ask: what have I been avoiding stepping into the light on?

### For Post-Institutional Seekers

You do not need an institution's permission to be loved by this text.

### For Leaders and Coaches

Ask your directee: where in your leadership are you hiding in the dark rather than risking exposure?

### For Worship Communities

Use this as a call to confession that ends in assurance, not shame.

### For Content Creators

A short-form piece: "The verse everyone quotes and no one finishes reading."

### For Professional Contexts

Judgment in this text is diagnostic, not punitive - a useful reframe for performance conversations.

---

**The Palimpsest Through-Line**: From literal meaning through allegorical connections through interpretive traditions through mystical silence into contemporary embodiment.
"""


def test_valid_content_splits_into_five_layers_in_order():
    result = parse_palimpsest_layers(VALID_PALIMPSEST_MARKDOWN)

    assert result is not None
    assert [layer["key"] for layer in result["layers"]] == [
        "peshat", "remez", "derash", "sod", "incarnation",
    ]


def test_intro_text_before_first_layer_is_captured_separately():
    result = parse_palimpsest_layers(VALID_PALIMPSEST_MARKDOWN)

    assert result is not None
    assert "This text rewards layered reading" in result["intro_markdown"]
    assert "Layer One" not in result["intro_markdown"]


def test_each_layer_contains_only_its_own_content():
    result = parse_palimpsest_layers(VALID_PALIMPSEST_MARKDOWN)

    assert result is not None
    layers_by_key = {layer["key"]: layer["markdown"] for layer in result["layers"]}

    assert "agape" in layers_by_key["peshat"]
    assert "bronze serpent" not in layers_by_key["peshat"]

    assert "bronze serpent" in layers_by_key["remez"]
    assert "Augustine" not in layers_by_key["remez"]

    assert "Augustine" in layers_by_key["derash"]
    assert "Sit for a moment" not in layers_by_key["derash"]

    assert "Sit for a moment" in layers_by_key["sod"]
    assert "Individuals in Transition" not in layers_by_key["sod"]


def test_incarnation_layer_keeps_its_six_subheadings_intact():
    result = parse_palimpsest_layers(VALID_PALIMPSEST_MARKDOWN)

    assert result is not None
    incarnation = next(layer for layer in result["layers"] if layer["key"] == "incarnation")

    for subheading in [
        "For Individuals in Transition",
        "For Post-Institutional Seekers",
        "For Leaders and Coaches",
        "For Worship Communities",
        "For Content Creators",
        "For Professional Contexts",
    ]:
        assert subheading in incarnation["markdown"]


def test_missing_layer_returns_none():
    missing_sod = VALID_PALIMPSEST_MARKDOWN.replace(
        "## Layer Four: Sod (Secret/Mystery)", "## Layer Four: Something Else Entirely"
    )

    assert parse_palimpsest_layers(missing_sod) is None


def test_layers_out_of_order_returns_none():
    # Swap Remez's and Derash's heading lines, producing the order
    # Peshat, Derash, Remez, Sod, Incarnation.
    out_of_order = VALID_PALIMPSEST_MARKDOWN.replace(
        "## Layer Two: Remez (Hint/Allegory)", "## Layer Two: TEMP_REMEZ_MARKER"
    ).replace(
        "## Layer Three: Derash (Search/Interpretation)", "## Layer Two: Remez (Hint/Allegory)"
    ).replace(
        "## Layer Two: TEMP_REMEZ_MARKER", "## Layer Three: Derash (Search/Interpretation)"
    )

    assert parse_palimpsest_layers(out_of_order) is None


def test_non_palimpsest_content_returns_none():
    threshold_style_content = """# Threshold Study: Mark 5:1-5

## Threshold One: Archaeological Dive

Some content here.

## Threshold Two: Theological Combustion

More content here.
"""

    assert parse_palimpsest_layers(threshold_style_content) is None


def test_heading_text_variance_still_matches_on_keyword():
    varied_heading = VALID_PALIMPSEST_MARKDOWN.replace(
        "## Layer One: Peshat (Simple/Literal)", "## Layer 1: Peshat"
    )

    result = parse_palimpsest_layers(varied_heading)

    assert result is not None
    assert result["layers"][0]["key"] == "peshat"


def test_empty_content_returns_none():
    assert parse_palimpsest_layers("") is None


def test_rail_labels_keys_match_parser_keys_in_same_order():
    result = parse_palimpsest_layers(VALID_PALIMPSEST_MARKDOWN)

    assert result is not None
    assert [item["key"] for item in RAIL_LABELS] == [layer["key"] for layer in result["layers"]]
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
python3 -m pytest tests/test_palimpsest_layers.py -v
```

Expected: FAIL — `web.services.palimpsest_layers` does not exist yet.

- [ ] **Step 3: Create the parser**

Create `web/services/palimpsest_layers.py`:

```python
"""
Parses a Palimpsest study's flat markdown content into its five named
PaRDeS layers (Peshat, Remez, Derash, Sod, Incarnation), so the study
view can render each as an addressable section for spatial navigation
(a scroll-tracking rail). See
docs/superpowers/specs/2026-08-28-tier-3-palimpsest-design.md.

Palimpsest studies are the only engine's content this parses; Threshold
and Collision keep rendering as flat scroll (see the design spec's
"Scope decisions" section for why).
"""

import re
from typing import List, Optional, TypedDict


class ParsedLayer(TypedDict):
    key: str
    markdown: str


class ParsedPalimpsest(TypedDict):
    intro_markdown: str
    layers: List[ParsedLayer]


LAYER_KEYWORDS = ["Peshat", "Remez", "Derash", "Sod", "Incarnation"]

RAIL_LABELS = [
    {"key": "peshat", "label": "Peshat · Simple/Literal"},
    {"key": "remez", "label": "Remez · Hint/Allegory"},
    {"key": "derash", "label": "Derash · Search/Interpretation"},
    {"key": "sod", "label": "Sod · Secret/Mystery"},
    {"key": "incarnation", "label": "Incarnation · Contemporary Body"},
]

_HEADING_PATTERN = re.compile(
    r"^##\s+.*\b(" + "|".join(LAYER_KEYWORDS) + r")\b.*$",
    re.MULTILINE | re.IGNORECASE,
)


def parse_palimpsest_layers(content: str) -> Optional[ParsedPalimpsest]:
    """
    Splits a Palimpsest study's markdown into its five PaRDeS layers.

    Returns None (not an error - callers should fall back to rendering
    `content` unsplit, exactly as today) unless all five keywords are
    found as distinct `##` headings, in the canonical order, with no
    duplicates and no extras.
    """
    matches = list(_HEADING_PATTERN.finditer(content))

    found_keywords = [m.group(1).lower() for m in matches]
    if found_keywords != [kw.lower() for kw in LAYER_KEYWORDS]:
        return None

    intro_markdown = content[: matches[0].start()].strip()

    layers: List[ParsedLayer] = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        layers.append({
            "key": LAYER_KEYWORDS[i].lower(),
            "markdown": content[start:end].strip(),
        })

    return {"intro_markdown": intro_markdown, "layers": layers}
```

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
python3 -m pytest tests/test_palimpsest_layers.py -v
```

Expected: all 10 PASS.

- [ ] **Step 5: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS, 0 failures.

- [ ] **Step 6: Commit**

```bash
git add web/services/palimpsest_layers.py tests/test_palimpsest_layers.py
git commit -m "Add Palimpsest layer parser

Splits a Palimpsest study's flat markdown content into its five named
PaRDeS layers (Peshat/Remez/Derash/Sod/Incarnation), matched on the
Hebrew/technical term itself inside a ## heading rather than literal
'Layer One/Two/...' text, since only the term order is protocol-
guaranteed. Returns None on any structural mismatch - missing layer,
wrong order, duplicates - so callers can fall back to today's flat
rendering. No database changes; this is pure render-time parsing.

See docs/superpowers/specs/2026-08-28-tier-3-palimpsest-design.md."
```

---

### Task 2: Route, template, and CSS for the rail

**Files:**
- Modify: `web/app.py` (the `view_study` route, `~line 161-208`)
- Modify: `web/templates/study.html`
- Modify: `web/static/css/styles.css`
- Modify: `tests/test_route_smoke.py`

**Interfaces:**
- Consumes: `parse_palimpsest_layers(content: str) -> Optional[dict]` and `RAIL_LABELS` from Task 1, exact shapes as documented there.
- Produces: the route passes `palimpsest_rail` (either `None` or Task 1's `RAIL_LABELS` list) into `study.html`'s template context. Task 3 reads `palimpsest_rail` from the template (already wired by this task) to conditionally load its JS file — Task 3 does not touch the route or the CSS added here, only `study.html`'s `extra_scripts` block and the new JS file itself.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_route_smoke.py`. First add this fixture near the top of the file, alongside the existing `client`/`isolated_client` fixtures (it needs its own fixture because, unlike `isolated_client`, these tests must seed a `Study` row into the same in-memory DB the client will query — `isolated_client` doesn't expose its session factory for seeding):

```python
@pytest.fixture
def study_client():
    """
    Like isolated_client, but also yields the session factory so tests
    can seed a Study row into the same in-memory DB before hitting the
    route under test.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    c = TestClient(app)
    c.cookies.set(COOKIE_NAME, create_session_cookie(1))
    yield c, SessionLocal

    app.dependency_overrides.pop(get_db, None)
```

Then add these tests (this file already has `from web.models import Base` at the top — add `Study` to that same import line, i.e. change `from web.models import Base` to `from web.models import Base, Study`):

```python
_PALIMPSEST_FIXTURE_CONTENT = """# Palimpsest Study: John 3:16-21

Intro paragraph here.

## Layer One: Peshat (Simple/Literal)

Peshat content.

## Layer Two: Remez (Hint/Allegory)

Remez content.

## Layer Three: Derash (Search/Interpretation)

Derash content.

## Layer Four: Sod (Secret/Mystery)

Sod content.

## Layer Five: Incarnation (Contemporary Body)

### For Individuals in Transition

Incarnation content.
"""


def test_palimpsest_study_page_shows_rail(study_client):
    client, SessionLocal = study_client
    session = SessionLocal()
    study = Study(
        engine="palimpsest", reference="John 3:16-21",
        content=_PALIMPSEST_FIXTURE_CONTENT, word_count=50,
    )
    session.add(study)
    session.commit()
    study_id = study.id
    session.close()

    response = client.get(f"/study/{study_id}")

    assert response.status_code == 200
    body = response.text
    assert 'class="palimpsest-rail"' in body
    for key in ["peshat", "remez", "derash", "sod", "incarnation"]:
        assert f'id="layer-{key}"' in body


def test_threshold_study_page_has_no_rail(study_client):
    client, SessionLocal = study_client
    session = SessionLocal()
    study = Study(
        engine="threshold", reference="Mark 5:1-5",
        content="## Threshold One: Archaeological Dive\n\nSome content.",
        word_count=10,
    )
    session.add(study)
    session.commit()
    study_id = study.id
    session.close()

    response = client.get(f"/study/{study_id}")

    assert response.status_code == 200
    assert 'class="palimpsest-rail"' not in response.text


def test_malformed_palimpsest_study_falls_back_to_flat_rendering(study_client):
    client, SessionLocal = study_client
    session = SessionLocal()
    malformed_content = (
        "## Layer One: Peshat (Simple/Literal)\n\n"
        "Only one layer here, missing the other four."
    )
    study = Study(
        engine="palimpsest", reference="Mark 5:1-5",
        content=malformed_content, word_count=10,
    )
    session.add(study)
    session.commit()
    study_id = study.id
    session.close()

    response = client.get(f"/study/{study_id}")

    assert response.status_code == 200
    assert 'class="palimpsest-rail"' not in response.text
    assert "Only one layer here" in response.text
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
python3 -m pytest tests/test_route_smoke.py -v -k "rail or malformed_palimpsest"
```

Expected: all 3 FAIL — the route doesn't produce rail markup yet (`test_threshold_study_page_has_no_rail` may pass trivially since there's no rail markup anywhere yet; the important ones, `test_palimpsest_study_page_shows_rail` and the malformed-content test, must fail).

- [ ] **Step 3: Update the route**

In `web/app.py`, add this import near the other `.services` imports (alongside `from .services.pdf_service import render_pdf, slugify`):

```python
from .services.palimpsest_layers import parse_palimpsest_layers, RAIL_LABELS
```

Find the current `view_study` route:

```python
@app.get("/study/{study_id}", response_class=HTMLResponse)
async def view_study(request: Request, study_id: int, db: Session = Depends(get_db)):
    """
    Study view page - displays a single study with beautiful formatting
    """
    study = db.query(Study).filter(Study.id == study_id).first()

    if not study:
        return templates.TemplateResponse("404.html", {
            "request": request,
            "message": "Study not found"
        }, status_code=404)

    # Convert markdown to HTML, linking scripture references to Bible Gateway
    # first so they render as normal markdown links.
    linked_content = link_scripture_references(study.content, study.translation)
    md = markdown.Markdown(extensions=[
        'extra',          # Tables, footnotes, etc.
        'nl2br',          # Newline to <br>
        'sane_lists',     # Better list handling
    ])
    study_html = md.convert(linked_content)
```

Replace the markdown-conversion portion (everything from the `linked_content = ...` line through `study_html = md.convert(linked_content)`) with:

```python
    # Convert markdown to HTML, linking scripture references to Bible Gateway
    # first so they render as normal markdown links.
    linked_content = link_scripture_references(study.content, study.translation)

    parsed_layers = None
    if study.engine == "palimpsest":
        parsed_layers = parse_palimpsest_layers(linked_content)

    palimpsest_rail = None
    if parsed_layers:
        md = markdown.Markdown(extensions=['extra', 'nl2br', 'sane_lists'])
        html_parts = [md.convert(parsed_layers["intro_markdown"])]
        for layer in parsed_layers["layers"]:
            md.reset()
            layer_html = md.convert(layer["markdown"])
            html_parts.append(
                f'<section id="layer-{layer["key"]}" class="palimpsest-layer">{layer_html}</section>'
            )
        study_html = "".join(html_parts)
        palimpsest_rail = RAIL_LABELS
    else:
        md = markdown.Markdown(extensions=[
            'extra',          # Tables, footnotes, etc.
            'nl2br',          # Newline to <br>
            'sane_lists',     # Better list handling
        ])
        study_html = md.convert(linked_content)
```

Leave the rest of the function (the validation-parsing block and the final `return templates.TemplateResponse(...)` call) exactly as-is, except add `"palimpsest_rail": palimpsest_rail,` to the context dict passed to `TemplateResponse`:

```python
    return templates.TemplateResponse("study.html", {
        "request": request,
        "study": study,
        "study_html": study_html,
        "palimpsest_rail": palimpsest_rail,
        "validation": validation
    })
```

Do **not** modify `download_study_pdf` (the `/study/{study_id}/pdf` route below it) — it keeps its own independent `md.convert(linked_content)` call, untouched.

- [ ] **Step 4: Update the template**

In `web/templates/study.html`, find the opening container div:

```html
<div class="container study-container" data-share-title="{{ study.reference }} — {{ study.engine | title }}">
```

Replace with:

```html
<div class="container study-container{% if palimpsest_rail %} study-container--with-rail{% endif %}" data-share-title="{{ study.reference }} — {{ study.engine | title }}">
```

Find the content block:

```html
    <div class="study-content" data-highlight-share>
        {{ study_html | safe }}
    </div>
```

Replace with:

```html
    {% if palimpsest_rail %}
    <div class="study-body-with-rail">
        <nav class="palimpsest-rail">
            {% for item in palimpsest_rail %}
            <a href="#layer-{{ item.key }}" class="palimpsest-rail-link" data-layer-key="{{ item.key }}">{{ item.label }}</a>
            {% endfor %}
        </nav>
        <div class="study-content" data-highlight-share>
            {{ study_html | safe }}
        </div>
    </div>
    {% else %}
    <div class="study-content" data-highlight-share>
        {{ study_html | safe }}
    </div>
    {% endif %}
```

Do not touch the `extra_scripts` block yet — Task 3 adds the JS file and its `<script>` tag together. Leave it as:

```html
{% block extra_scripts %}
<script src="/static/js/content-actions.js" defer></script>
{% endblock %}
```

This means after this task, clicking a rail link already works via the browser's native anchor-jump behavior (`<a href="#layer-peshat">` scrolling to `id="layer-peshat"` is a plain HTML/CSS feature, no JS required) — Task 3 only adds the *smooth* scroll and the active-highlight-while-scrolling enhancement on top of already-functional navigation.

- [ ] **Step 5: Add CSS**

In `web/static/css/styles.css`, find:

```css
.study-content em {
    font-style: italic;
}
```

Add immediately after it (before the `/* Scripture references auto-linked... */` comment that follows):

```css

/* Palimpsest spatial rail - see
   docs/superpowers/specs/2026-08-28-tier-3-palimpsest-design.md */
.study-container--with-rail {
    max-width: calc(750px + 220px + var(--space-xl));
}

.study-container--with-rail .study-header,
.study-container--with-rail .currents-actions-bar,
.study-container--with-rail .validation-panel,
.study-container--with-rail .study-footer {
    max-width: 750px;
    margin-left: auto;
    margin-right: auto;
}

.study-body-with-rail {
    display: grid;
    grid-template-columns: 220px 1fr;
    gap: var(--space-xl);
    align-items: start;
}

.palimpsest-rail {
    position: sticky;
    top: 100px;
    height: fit-content;
    display: flex;
    flex-direction: column;
    gap: var(--space-xs);
}

.palimpsest-rail-link {
    display: block;
    padding: var(--space-xs) var(--space-sm);
    border-left: 2px solid var(--color-border);
    color: var(--color-ink-muted);
    text-decoration: none;
    font-family: var(--font-body);
    font-size: 0.9rem;
    transition: border-left-color 0.15s ease, color 0.15s ease;
}

.palimpsest-rail-link:hover {
    color: var(--color-ink);
}

.palimpsest-rail-link.active {
    border-left-color: var(--color-gold);
    color: var(--color-ink);
    font-weight: 600;
}
```

Then find the existing `@media (max-width: 900px) { ... }` block:

```css
@media (max-width: 900px) {
    .engines-grid {
        grid-template-columns: 1fr;
    }

    .this-week-grid {
        grid-template-columns: 1fr;
    }

    .browse-layout {
        grid-template-columns: 1fr;
    }

    .browse-sidebar {
        position: static;
        order: 2;
    }

    .browse-main {
        order: 1;
    }
}
```

Add these rules inside it, after `.browse-main { order: 1; }` and before the block's closing `}`:

```css

    .study-container--with-rail {
        max-width: 100%;
    }

    .study-body-with-rail {
        grid-template-columns: 1fr;
    }

    .palimpsest-rail {
        position: sticky;
        top: 0;
        z-index: 50;
        flex-direction: row;
        overflow-x: auto;
        background: var(--color-parchment);
        padding: var(--space-sm) 0;
        gap: var(--space-sm);
    }

    .palimpsest-rail-link {
        border-left: none;
        border-bottom: 2px solid var(--color-border);
        white-space: nowrap;
    }

    .palimpsest-rail-link.active {
        border-left-color: transparent;
        border-bottom-color: var(--color-gold);
    }
```

This mobile treatment keeps the rail sticky at the top of the viewport as a horizontal scrollable strip, rather than the `.browse-sidebar` pattern's "drop to a static block below content" — the rail needs to stay usable throughout a long scroll, unlike a one-time filter control, so `position: static` would defeat its purpose here.

Every token used above (`--space-xs/sm/xl`, `--color-border`, `--color-ink-muted`, `--color-ink`, `--color-gold`, `--color-parchment`, `--font-body`) already exists in `:root` — do not invent new tokens, do not modify any existing rule.

- [ ] **Step 6: Run the tests to confirm they pass**

```bash
python3 -m pytest tests/test_route_smoke.py -v -k "rail or malformed_palimpsest"
```

Expected: all 3 PASS.

- [ ] **Step 7: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS, 0 failures.

- [ ] **Step 8: Verify by eye**

Start the dev server (`uvicorn web.app:app --port 8123`, using the venv at the repo root), sign in, and view an existing Palimpsest study (or generate one via `/generate` if none exist locally — `db.query(Study).filter(Study.engine == 'palimpsest').first()` from a Python shell against `lectionary.db` will tell you if one exists). Confirm: the rail appears to the left of the content on a desktop-width window, the reading column is roughly the same width as before (not visibly cramped), clicking a rail link jumps to that layer (native anchor behavior, no smoothness required yet), and narrowing the browser window below ~900px collapses the rail into a horizontal strip at the top. View a Threshold or Collision study and confirm no rail appears and the page is visually unchanged from before this task.

- [ ] **Step 9: Commit**

```bash
git add web/app.py web/templates/study.html web/static/css/styles.css tests/test_route_smoke.py
git commit -m "Add spatial rail markup for Palimpsest studies

/study/{id} now parses Palimpsest content into five anchored sections
(via Task 1's parser) and renders a left rail linking to each. Content
that doesn't parse, and all Threshold/Collision studies, render
exactly as before. Rail navigation works via native anchor links at
this point; Task 3 adds scroll-tracking active-highlight and smooth
scroll on top of this already-functional markup.

See docs/superpowers/specs/2026-08-28-tier-3-palimpsest-design.md."
```

---

### Task 3: Scroll-tracking and smooth-scroll JS

**Files:**
- Create: `web/static/js/palimpsest-rail.js`
- Modify: `web/templates/study.html` (`extra_scripts` block only)

**Interfaces:**
- Consumes: the `.palimpsest-rail` / `.palimpsest-rail-link[data-layer-key]` / `<section id="layer-{key}">` markup Task 2 already renders. No Python interfaces — this task is pure client-side.
- Produces: nothing consumed by later tasks — this is the last task in this plan.

- [ ] **Step 1: Create the JS file**

Create `web/static/js/palimpsest-rail.js`:

```javascript
/**
 * Palimpsest spatial rail: highlights the currently-visible layer in
 * the left rail as the reader scrolls, and smooth-scrolls to a layer
 * when its rail link is clicked. See
 * docs/superpowers/specs/2026-08-28-tier-3-palimpsest-design.md.
 *
 * No-ops entirely if the rail isn't on the page (every non-Palimpsest
 * study, and any Palimpsest study whose content didn't parse into five
 * layers) - this file is safe to include unconditionally, though
 * study.html only includes it when palimpsest_rail is present.
 */
(function () {
    var rail = document.querySelector('.palimpsest-rail');
    if (!rail) {
        return;
    }

    var links = Array.prototype.slice.call(rail.querySelectorAll('.palimpsest-rail-link'));

    function setActive(key) {
        links.forEach(function (link) {
            if (link.dataset.layerKey === key) {
                link.classList.add('active');
            } else {
                link.classList.remove('active');
            }
        });
    }

    var sections = [];
    links.forEach(function (link) {
        var section = document.getElementById('layer-' + link.dataset.layerKey);
        if (section) {
            sections.push(section);
        }
    });

    if (sections.length > 0 && 'IntersectionObserver' in window) {
        var observer = new IntersectionObserver(function (entries) {
            var visible = entries.filter(function (entry) {
                return entry.isIntersecting;
            });
            visible.sort(function (a, b) {
                return b.intersectionRatio - a.intersectionRatio;
            });
            if (visible.length > 0) {
                setActive(visible[0].target.id.replace('layer-', ''));
            }
        }, {
            rootMargin: '-20% 0px -70% 0px',
            threshold: [0, 0.25, 0.5, 0.75, 1]
        });

        sections.forEach(function (section) {
            observer.observe(section);
        });
    }

    links.forEach(function (link) {
        link.addEventListener('click', function (event) {
            var section = document.getElementById('layer-' + link.dataset.layerKey);
            if (section) {
                event.preventDefault();
                section.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
    });
})();
```

- [ ] **Step 2: Wire it into the template**

In `web/templates/study.html`, find:

```html
{% block extra_scripts %}
<script src="/static/js/content-actions.js" defer></script>
{% endblock %}
```

Replace with:

```html
{% block extra_scripts %}
<script src="/static/js/content-actions.js" defer></script>
{% if palimpsest_rail %}
<script src="/static/js/palimpsest-rail.js" defer></script>
{% endif %}
{% endblock %}
```

- [ ] **Step 3: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS, 0 failures. This task adds no new automated tests — `IntersectionObserver` scroll behavior and smooth-scroll are not meaningfully testable at this level (no real browser layout/scroll in the test client); Task 2's route-smoke tests already confirm the markup this script depends on (`.palimpsest-rail`, `.palimpsest-rail-link[data-layer-key]`, `<section id="layer-*">`) is present, which is what matters for this script to have something to attach to.

- [ ] **Step 4: Verify by eye**

Start the dev server, sign in, view a Palimpsest study with a tall enough window that not all five layers fit on screen at once. Confirm: scrolling through the study updates which rail link is bold/highlighted as you pass through each layer's section, and clicking a rail link now smooth-scrolls (not an instant jump) to that layer. Open the browser console and confirm no JS errors on a Threshold or Collision study page (the script should no-op silently there, confirmed by the `if (!rail) { return; }` guard at the top).

- [ ] **Step 5: Commit**

```bash
git add web/static/js/palimpsest-rail.js web/templates/study.html
git commit -m "Add scroll-tracking and smooth-scroll to the Palimpsest rail

IntersectionObserver highlights the active layer's rail link as the
reader scrolls; clicking a rail link smooth-scrolls to that layer
instead of an instant jump. No-ops safely when the rail isn't present
on the page. This completes Tier 3 - the rail markup from Task 2 was
already functional via native anchor links; this is the spatial-
navigation polish the design spec calls for.

See docs/superpowers/specs/2026-08-28-tier-3-palimpsest-design.md."
```

---
