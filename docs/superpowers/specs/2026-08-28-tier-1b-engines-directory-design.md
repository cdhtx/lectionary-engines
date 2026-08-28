# Tier 1b — Engines Directory: Design Spec

First of Tier 1b's four independently-shippable pieces (Today homepage, unified
Library, Engines directory, Workbench reflow — see parent spec section 6). Picked
first as the lowest-risk, lowest-complexity new route: no new query logic, no new
data model, fully static content.

**Parent spec:** `docs/superpowers/specs/2026-08-27-beta-workspace-redesign-design.md`
— design tokens, aesthetic guardrails, and information architecture are all
inherited from there and not repeated here.

**Depends on Tier 1a.** The navy sidebar `base.html` shell only exists on branch
`beta-tier-1a-restyle` (PR open, not yet merged to `main`). This work branches from
`beta-tier-1a-restyle`, not `main`, and should retarget once 1a merges.

## Problem

Engine information (Threshold, Palimpsest, Collision — name, description,
methodology steps, word count/read time) currently lives only as three cards
crammed into the homepage (`web/templates/index.html:17-51`). The Beta information
architecture calls for a dedicated "Engines" nav item (parent spec section 5), and
Tier 1b's own scope explicitly includes "the Engines directory."

## Design

**Route:** `GET /engines`, in a new `web/routes/engines.py` `APIRouter`, registered
in `web/app.py` alongside the other five feature routers (`auth`, `studies`,
`profiles`, `workshop`, `resonance`, `currents`) — following that established
convention rather than the older pattern of routes living directly in `app.py`.

**Template:** `web/templates/engines.html`, extends `base.html`. Full-width single
page listing all three engines (not an index + three detail pages — the existing
content doesn't warrant that much depth per engine, and one page keeps side-by-side
comparison easy).

**Content — relocated, not invented.** The exact existing copy from
`index.html:17-51` (per-engine description paragraph, methodology step list,
word-count/read-time meta line) moves here, expanded into more breathing room than
the homepage grid cards allow. No new marketing copy. Each engine section gets one
new element: a "Start a [Engine] study" button linking to `/generate` (no
query-param preselect — passing the chosen engine through to `/generate` is new
`/generate` behavior and belongs to the Workbench reflow piece, out of scope here).

**One known exception to "exactly":** the Threshold step list's fourth bullet reads
"Embodied Practice + Tech" in `index.html`. There's a standing, already-approved
request (noted in project memory 2026-08-27) to change this to just "Embodied
Practice" wherever it appears next. Since this page is a fresh transcription of that
content, not an edit to the existing line, apply the correction here directly rather
than relocating the not-yet-fixed wording and needing a second pass. `index.html`
itself is untouched either way (see "do not touch index.html" below).

**Nav integration:** `base.html`'s sidebar gets a new `Engines` link immediately
after Library, *before* the existing `sidebar-divider` (i.e. inside the primary
group with Today/Workbench/Library, matching the parent spec's IA table grouping
— not in the Workshop/Currents/Resonance group below the divider). `active` when
`request.url.path.startswith('/engines')`.

**Data flow:** None — fully static. No DB query, no template context beyond the
standard `request` object passed by every route.

## Testing

One test added to `tests/test_route_smoke.py` (or a new dedicated file if that one
is getting crowded): `GET /engines` returns 200 and the response body contains all
three engine names ("Threshold", "Palimpsest", "Collision"). Mirrors the pattern
Tier 1a's smoke tests already established.

## Out of scope (belongs to other Tier 1b pieces or later tiers)

- `/generate?engine=X` query-param preselect (Workbench reflow)
- Example studies, "when to use this" guidance, or any other new copy beyond the
  relocated homepage content (not requested; can be a fast follow if wanted later)
- Removing the engine cards from `index.html` — that page gets replaced wholesale
  when the Today homepage piece ships; touching it now would be premature
  duplicate work
