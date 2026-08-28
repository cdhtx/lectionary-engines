# Tier 1b — Library Unification: Design Spec

Fourth and final piece of Tier 1b (Engines directory, Workbench reflow, and Today
homepage all shipped — see parent spec section 6). The most complex of the four:
the only piece with genuine multi-model query logic, not a template reorder or a
small static route.

**Parent spec:** `docs/superpowers/specs/2026-08-27-beta-workspace-redesign-design.md`
— design tokens, aesthetic guardrails, and the IA table are inherited from there.

**Depends on Tier 1a** (sidebar shell, Beta tokens, `.engine-badge`/`.currents-badge`/
`.resonance-badge` CSS already exist) **and the three already-shipped Tier 1b pieces**
(specifically reuses patterns established by Today's homepage query work). Branches
from `main`, which now has all of Tier 1a and the first three Tier 1b pieces merged.

## Problem

Three separate pages today (`/browse`, `/workshop/browse`, `/currents/browse`) each
independently query and paginate one content type (`Study`, `WorkshopPrep`,
`CurrentsAnalysis`). A fourth content type, `CulturalResonance`, has no browse page
at all — only a search form (`/resonance`) and per-result view pages. The spec calls
for one unified Library view spanning all four.

## Scope decisions (resolved 2026-08-28)

- **Include `CulturalResonance` now**, not deferred. The spec's own text says the
  query spans "four content models," and the four SQLAlchemy models in
  `web/models.py` are exactly `Study`, `WorkshopPrep`, `CurrentsAnalysis`,
  `CulturalResonance`. Resonance results link to their existing `/resonance/{id}`
  view page — no new detail page needed, just inclusion in the list query.
- **Filtering: a content-type selector plus one shared search box.** The three
  existing pages have inconsistent, type-specific filters today (Study has
  engine/source; WorkshopPrep has lens; Currents has none). This piece does not
  preserve those granular filters — it adds one `type` filter (All / Studies /
  Workshop / Currents / Resonance) and one text search applied per-type against
  each model's own searchable fields (see "Per-type field mapping" below).
  Re-adding engine/source/lens-level filtering on top of the unified view is a
  reasonable future piece, not part of this one.
- **`/browse` is repurposed, not replaced with a new route.** Its existing route
  and template (`browse.html`) get rewritten to serve the unified query. The
  sidebar's "Library" link already points at `/browse`, so no nav change is
  needed. `/workshop/browse` and `/currents/browse` are left completely
  untouched — still fully functional, just no longer the primary way to reach
  their content. This satisfies Tier 1's "no route removal" posture with zero
  404 risk.
- **The sidebar keeps its Workshop/Currents/Resonance links as-is.** The parent
  spec's IA table describes an eventual "folded into Workbench / Library /
  Signals" state for those three, but Tier 1b's own scope paragraph only names
  Today, Workbench, Library, and Engines as deliverables — it does not ask to
  remove existing nav. A supplied reference mockup shows a sidebar with both
  "Library" and "Browse" as separate items, and Currents/Resonance still
  present alongside Library, which is internally inconsistent with the spec's
  own "folded into" language for those two. Per precedent already set in the
  spec itself (section 4: "the CSS token spec supersedes" the mockup and
  rationale doc where they conflicted), the written spec's text governs, not
  the mockup's rendering of it — and doing a fuller sidebar consolidation now
  would be scope creep beyond what this tier's own text asks for, on top of
  what's already shipped unchanged through three prior Tier 1b pieces.

## Design

### New service: `web/services/library_service.py`

One function: `search_library(db: Session, content_type: Optional[str] = None, q: Optional[str] = None, page: int = 1, per_page: int = 12) -> dict`.

Builds one normalized SQLAlchemy `select()` per content type, each projecting into
a common column shape: `id`, `content_type` (a literal string constant per query —
`"study"` / `"workshop"` / `"currents"` / `"resonance"`), `title`, `badge_label`,
`created_at`. If `content_type` is given, only that one type's `select()` is built
(the other three are skipped entirely, not filtered out after the fact). If `q` is
given, each type's `select()` gets an `ilike` filter against its own searchable
fields. The (possibly single, possibly four) `select()` statements are combined
with SQLAlchemy's `union_all()`, wrapped, ordered by `created_at desc`, and
paginated with a single `LIMIT`/`OFFSET` over the *combined* result — this is what
makes pagination correct across four differently-sized, differently-shaped tables;
independently paginating each type and merging the pages would produce wrong page
boundaries.

Returns: `{"results": [...], "page": int, "total_pages": int, "total": int,
"has_prev": bool, "has_next": bool}`. Each result dict has `content_type`, `id`,
`title`, `badge_label`, `created_at`, and `url` (computed from `content_type` +
`id`, e.g. `/study/{id}`, `/workshop/{id}`, `/currents/{id}`, `/resonance/{id}`).

### Per-type field mapping

| Type | Searchable fields (`q` matches against) | `title` | `badge_label` |
|---|---|---|---|
| Study | `reference`, `content` | `reference` | `engine` (Threshold/Palimpsest/Collision) |
| WorkshopPrep | `reference`, `content` | `reference` | `"Workshop"` (fixed string, not per-lens) |
| CurrentsAnalysis | `headline_summary`, `story_context`, `content` | `headline_summary`, falling back to `"Theological News Analysis"` if null (matches the existing fallback pattern already used in `currents_result.html`) | `"Currents"` (fixed string) |
| CulturalResonance | `reference`, `themes`, `content` | `reference` if present, else its `themes` (JSON array) joined with `", "` (e.g. `"Hospitality, Empire"`) | `"Resonance"` (fixed string) |

### Badge CSS

`.engine-badge` (with `.engine-threshold`/`.engine-palimpsest`/`.engine-collision`)
and `.currents-badge`/`.resonance-badge` already exist and are reused as-is — no
changes to their styling. One new class, `.workshop-badge`, is added to
`web/static/css/styles.css` matching the same visual pattern as `.currents-badge`/
`.resonance-badge` (a colored pill, not per-lens variation — the existing
`.lens-badge` used on `workshop_result.html` stays untouched and unrelated).

### Route: `/browse` (repurposed)

`web/app.py`'s existing `browse_studies` handler is rewritten to accept `type`,
`q`, `page` query params (replacing `engine`/`source`, which the type filter
supersedes) and calls `search_library()` instead of its current `Study`-only
query. Response passed to the (rewritten) `browse.html` template.

**Exact `type` param values** (both the route param and `search_library()`'s
`content_type` param use the same strings): `"study"`, `"workshop"`,
`"currents"`, `"resonance"`. Absent, empty, or any unrecognized value is treated
identically to "no filter" (all four types included) — this is a UI-driven
dropdown, not a user-typed field, so failing open rather than erroring on a
stray/invalid value is the right default.

### Template: `browse.html` (rewritten)

One type-filter control (All / Studies / Workshop / Currents / Resonance) plus one
search input, a card list where each card shows its `badge_label`, `title`,
formatted `created_at`, and links to its `url`, and the existing pagination
controls (kept, just driven by the new response shape).

## Testing

`search_library()` is unit-testable in isolation (test-first, per the parent
spec's explicit call-out): seed a temp DB with rows across all four models,
assert (a) no filter returns all four types merged and correctly ordered by
`created_at desc` regardless of source table, (b) a `content_type` filter returns
only that type, (c) a `q` filter matches across the right fields per type and
excludes non-matching rows, (d) pagination boundaries are correct when results
span multiple types on the same page (e.g. page 1 has 12 results drawn from more
than one type, not "12 studies then a hard cutoff before workshop preps").
Route-smoke coverage: `GET /browse` still returns 200 (already covered by the
existing parametrized `test_page_renders`).

## Out of scope (belongs to a later piece or later tier)

- Re-adding granular per-type filters (engine/source/lens) on top of the unified
  view
- Removing or consolidating the sidebar's Workshop/Currents/Resonance links
- A dedicated Resonance browse/detail page beyond linking to the existing
  `/resonance/{id}` view
- Faceting by liturgical season, tradition, or theme (explicitly Tier 4 —
  "Library as knowledge graph" — per the parent spec, blocked on taxonomy fields
  that don't exist in the data model yet)
