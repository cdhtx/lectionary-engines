# Tier 3 — Palimpsest as Spatial Experience: Design Spec

Fifth piece of the beta workspace redesign (per the parent spec's dependency graph —
`docs/superpowers/specs/2026-08-27-beta-workspace-redesign-design.md` section 6: Tier 3
has no dependency on Tier 2, which is now fully complete and merged).

**Parent spec's Tier 3 description (verbatim, section 6):**
> Currently the five PaRDeS layers exist only as markdown headers inside one flat content
> blob. Making the framework spatial — a left rail where the active layer tracks scroll, or
> click-a-layer-reveals-beside-anchored-text — requires those layers to become *addressable
> sections*. That is a real parsing and data-shape decision, not CSS.
>
> The distinction that makes this worth doing: today the product gives you *the result of*
> Palimpsest. This lets a user *think with* Palimpsest.

This paragraph is intent, not a spec — the sections below resolve everything it left open.

## Scope decisions (resolved 2026-08-28)

**Palimpsest only, not a generic layered-study mechanism.** Threshold (4 sections) and
Collision (5 steps + extras) share the same underlying shape — progressive `##`-delimited
sections in one markdown blob — and the parsing mechanism this tier needs would work
unchanged for either. But the parent spec's own text scopes this tier to Palimpsest by name,
and Palimpsest's five layers are fixed and named (Peshat/Remez/Derash/Sod/Incarnation),
which is a simpler, better-bounded parsing target than three engines with different section
counts and vocabularies. Threshold and Collision keep rendering as flat scroll. Extending the
same mechanism to them is a reasonable follow-up piece once this one ships, not part of it.

**Interaction model: scroll-tracking left rail, not click-to-reveal-beside-text.** The parent
spec names two options. The rail model keeps the existing single continuous scroll (which the
protocol's own prose is written for — each layer explicitly ends with "now we explore...",
assuming the reader continues downward) and adds a sticky nav that highlights the active
layer and lets the reader jump to any layer. The reveal-beside-anchored-text model is a
materially bigger interaction-design problem (what stays "anchored," how layers stack on
mobile, whether it breaks the linear read the protocol assumes) with no corresponding gain
named in the parent spec's own reasoning ("think with Palimpsest" doesn't require abandoning
linear reading — the current product already asks for a 25-35 minute continuous read, per
`palimpsest_protocol.py`'s `OUTPUT_CONSTRAINTS`).

**Data shape: render-time parsing, no database migration.** `Study.content` stays exactly as
it is today — one markdown `Text` column, unchanged across all three engines. At view time,
`/study/{id}` parses a Palimpsest study's content into five named sections and renders them
with anchors; nothing is persisted differently. This was weighed against adding structured
storage (a `StudyLayer` table or JSON column, populated at generation time) — rejected for
this tier because it requires a migration and a decision about already-generated studies
(backfill-parse vs. leave flat), in exchange for query power (e.g. cross-study layer
analytics) nothing in this tier or Tier 4 currently asks for. The parser's output shape (a
list of `{key, label, markdown}` objects) is exactly what a future migration would backfill
from, so this choice doesn't foreclose structured storage later — it just doesn't build it
before something needs it.

## Problem

Palimpsest studies render today exactly like Threshold and Collision studies: one flat
markdown blob converted to one HTML blob, dropped into a single scrolling `.study-content`
div (`web/app.py:161-208`, `web/templates/study.html:138-140`). The five PaRDeS layers exist
only as `## Layer Two: Remez (Hint/Allegory)`-style headers — visually and structurally
indistinguishable from any other subheading in the piece. There is no way to see all five
layers at a glance, jump between them, or know which one you're currently reading without
scrolling back up to find the last heading. For a 3000-4000 word, 25-35 minute read
(`palimpsest_protocol.py` `OUTPUT_CONSTRAINTS`), that's a real navigation gap.

## Design

### New module: `web/services/palimpsest_layers.py`

One function: `parse_palimpsest_layers(content: str) -> Optional[dict]`.

Scans `content` for `##`-level markdown headings containing one of the five layer keywords —
matched on the Hebrew/technical term itself (`Peshat`, `Remez`, `Derash`, `Sod`,
`Incarnation`), case-insensitively, not on literal "Layer One/Two/Three/Four/Five" text,
since the protocol only constrains the model to produce these headings in this relative
order (`palimpsest_protocol.py`'s `OUTPUT_CONSTRAINTS["required_layers"]`); exact phrasing
around them ("Layer One:" vs "Layer 1:" vs no numeral at all) is not guaranteed. If all five
keywords are found as distinct `##` headings, in that order, the function returns:

```python
{
    "intro_markdown": str,   # everything before the first ("Peshat") heading
    "layers": [
        {"key": "peshat", "markdown": str},       # heading line through end of this layer
        {"key": "remez", "markdown": str},
        {"key": "derash", "markdown": str},
        {"key": "sod", "markdown": str},
        {"key": "incarnation", "markdown": str},   # includes the six "### For X" subheadings verbatim
    ],
}
```

If fewer than five keywords are found, or they appear out of order, or any two collide at the
same position, the function returns `None` — the caller's signal to fall back to today's
undivided rendering. `None` is the expected, non-error outcome for any non-Palimpsest content
and for the rare malformed Palimpsest generation; it is not logged as a failure.

Layer Five's six `### For Individuals in Transition` / `### For Post-Institutional Seekers` /
etc. subheadings (`palimpsest_protocol.py` lines 216-232) need no special handling — they are
`###`, one level below the `##` split point, so they simply remain inside the Incarnation
layer's `markdown` chunk and render as ordinary subheadings within that section. They are not
separately tracked in the rail.

### Route: `/study/{id}` (`web/app.py`, `view_study`)

Only when `study.engine == "palimpsest"`: after the existing `link_scripture_references()`
call (unchanged — scripture linking happens on the full content before any splitting, so its
behavior is identical to today), call `parse_palimpsest_layers()` on the linked content.

**On success:** render `intro_markdown` and each layer's `markdown` through the same
`markdown.Markdown(extensions=['extra', 'nl2br', 'sane_lists'])` pipeline already in use,
calling `.reset()` between conversions (required by python-markdown to clear
footnote/reference state between independent `.convert()` calls on the same instance). Wrap
each layer's rendered HTML in `<section id="layer-{key}" class="palimpsest-layer">...
</section>` and concatenate: `intro_html + layer_html_1 + ... + layer_html_5`. This
concatenated string becomes `study_html` — the exact same template variable
`study.html:139` already renders via `{{ study_html | safe }}`. The template's existing
rendering path does not change shape at all; it just now contains five `<section id="...">`
wrapper tags it didn't have before.

The only new template variable is `palimpsest_rail`: a fixed list of five
`{"key": ..., "label": ...}` dicts, present only when parsing succeeded:

```python
PALIMPSEST_RAIL_LABELS = [
    {"key": "peshat", "label": "Peshat · Simple/Literal"},
    {"key": "remez", "label": "Remez · Hint/Allegory"},
    {"key": "derash", "label": "Derash · Search/Interpretation"},
    {"key": "sod", "label": "Sod · Secret/Mystery"},
    {"key": "incarnation", "label": "Incarnation · Contemporary Body"},
]
```

Labels are hardcoded here, not extracted from the AI-generated heading text, so rail display
never depends on the model's exact phrasing matching a specific format.

**On failure (`None` returned), or for any non-Palimpsest `study.engine`:** behavior is
byte-for-byte identical to today — one `md.convert(linked_content)` call, no `palimpsest_rail`
in the template context, no sections, no rail.

`/study/{id}/pdf` (`download_study_pdf`) is **not modified**. It keeps calling
`md.convert(linked_content)` directly on the full flat content, exactly as today. The rail is
a page-navigation aid for on-screen reading; a downloaded PDF has no scroll position to track
and no benefit from mid-document anchors that don't exist as PDF bookmarks.

### Template: `web/templates/study.html`

One new conditional block, rendered only `{% if palimpsest_rail %}`: a `<nav
class="palimpsest-rail">` containing one `<a href="#layer-{{ item.key }}">{{ item.label }}
</a>` per entry. No changes to the existing `.study-content` block — it keeps rendering
`study_html` exactly as it does today; the `<section id="layer-*">` anchors are now simply
part of that HTML.

Desktop: the rail is sticky-positioned in a left column beside `.study-content`, using the
same `position: sticky` pattern already established elsewhere in `web/static/css/styles.css`
for sticky UI. Mobile (no room for a persistent sidebar): the same rail markup collapses via
media query into a horizontal, scrollable strip pinned below the study header — same anchors,
same active-state JS, `flex-direction: row` instead of `column`. This follows the existing
mobile-breakpoint pattern already used for `.study-content` at `styles.css:2861` (`@media`
block covering `.study-content, .workshop-content, .resonance-content, .currents-content`).

### New file: `web/static/js/palimpsest-rail.js`

Loaded via `{% block extra_scripts %}` in `study.html`, alongside the existing
`content-actions.js`, only when the rail is present (guard on `document.querySelector('.palimpsest-rail')` at the top of the script, so the file can be
unconditionally included without erroring on non-Palimpsest pages — matching the existing
`content-actions.js` pattern of checking for its target elements before wiring up listeners).

Two behaviors, same vanilla-JS, no-framework style as `content-actions.js`:
1. An `IntersectionObserver` watches all five `<section id="layer-*">` elements. Whichever
   section is most visible in the viewport gets its matching rail link marked `.active`
   (and all others cleared).
2. Clicking a rail link calls `scrollIntoView({behavior: 'smooth', block: 'start'})` on the
   corresponding section — no custom scroll math, standard browser API.

### Non-goals (explicitly out of scope for this tier)

- Threshold and Collision spatial navigation (same mechanism, different engine — a reasonable
  follow-up, not part of this piece; see Scope decisions above)
- Click-to-reveal-beside-anchored-text interaction model (see Scope decisions above)
- Any database schema change or migration (see Scope decisions above)
- PDF export changes — `/study/{id}/pdf` is untouched
- Backfilling or re-validating existing Palimpsest studies — the parser runs at view time
  against whatever `content` already exists; no batch job, no data migration

## Testing

- `parse_palimpsest_layers()`: unit tests with a known-good, full-length Palimpsest markdown
  fixture (all five headings present, in order, including Layer Five's six `### For X`
  subheadings) asserting all five layers are extracted with correct boundaries and the intro
  text is captured separately; a fixture missing one layer heading asserting `None` is
  returned; a fixture with headings out of order asserting `None` is returned; a fixture with
  heading text variance ("## Layer 1: Peshat" instead of "## Layer One: Peshat (Simple/Literal)")
  asserting the keyword-based match still succeeds.
- Route-smoke coverage: a Palimpsest study's `GET /study/{id}` response includes
  `palimpsest-rail` markup and all five `layer-*` anchor ids; a Threshold study's `GET
  /study/{id}` response includes neither (regression guard that non-Palimpsest rendering is
  unaffected); a Palimpsest study whose content doesn't parse (missing/malformed layers)
  still returns 200 with the existing flat rendering and no rail markup.
- Scroll-tracking and click-to-jump behavior (the `IntersectionObserver` active-state
  highlighting, smooth-scroll on click) are not verifiable by the automated test suite —
  these are manual browser checks during implementation, the same category of verification
  Tier 2's UI work required.
