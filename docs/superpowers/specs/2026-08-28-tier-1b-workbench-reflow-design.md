# Tier 1b — Workbench Reflow: Design Spec

Second of Tier 1b's four independently-shippable pieces (Engines directory —
already shipped — Today homepage, unified Library, Workbench reflow — see
parent spec section 6).

**Parent spec:** `docs/superpowers/specs/2026-08-27-beta-workspace-redesign-design.md`
— design tokens, aesthetic guardrails, and the "Generate is retired" rationale
(section 5) are inherited from there and not repeated here.

**Depends on Tier 1a.** Same as the Engines directory piece: branches from
`beta-tier-1a-restyle` (or, once that PR has merged, from `main`) for the sidebar
shell and Beta CSS tokens `generate.html` already relies on.

## Problem

The current `/generate` page (`web/templates/generate.html`) leads with engine
selection: "1. Choose an Engine" comes before "3. Choose Text Source." The parent
spec's information architecture (section 5, "Generate is retired") reframes this:
the engine is a *methodology* chosen after deciding what you're exploring, not the
first decision. Per section 6: "Workbench 1b delivers the existing paths (passage /
lectionary / paste) reflowed into the new two-step framing. 'Theme' and 'question'
as entry points are new capability, later."

## Design

**Pure reorder + relabel, no new capability, no Python changes.** Confirmed scope
(2026-08-28): all four existing source tabs (Paste Text, Bible Gateway, Moravian
Daily Text, RCL) stay — the spec's "passage / lectionary / paste" wording is
descriptive shorthand, not an instruction to remove Moravian. Profile selection and
News Integration stay as later steps, content unchanged.

**File touched:** `web/templates/generate.html` only.

**What moves:** The `<div class="form-section">` currently titled "3. Choose Text
Source" (containing the four source tabs and all their per-source fields) moves to
the first position in the form, heading changed to `<h2>1. What are you
exploring?</h2>`. The block currently titled "1. Choose an Engine" moves to the
second position, heading changed to `<h2>2. Choose an Engine</h2>`.

**What stays put, renumbered only:** "Select Your Profile" becomes
`<h2>3. Select Your Profile</h2>`; "News Integration" becomes `<h2>4. News
Integration</h2>` (its existing "(optional)" suffix span is unchanged).

**What doesn't change:** every `name=` and `id=` attribute; the `<script>` block's
JS (profile loading via `/api/profiles`, tone/cultural-artifacts sliders, news
toggle + past-Currents fetch, engine-based time-estimate text, source-tab
show/hide switching, moravian-context character counters) — all of it is wired by
element ID or `name`, not DOM position, so none of it needs to change. The POST
handler in `web/routes/studies.py` reads submitted fields by name; form layout is
irrelevant to it.

**Page title/intro text:** `web/templates/generate.html`'s `<div class="page-header">`
(`<h1>Generate Study</h1>` + intro paragraph) is left as-is. Renaming the page
itself (title, `/generate` route path, sidebar "Workbench" label — already done in
Tier 1a) is out of scope; this piece only reorders the form sections inside the
existing page.

## Testing

Extend the existing `tests/test_route_smoke.py` (already covers `GET /generate`
returning 200 via the parametrized `test_page_renders`). Add one new assertion-based
test confirming the reorder actually happened — not just that the page still
loads — by checking that "What are you exploring?" appears before "Choose an
Engine" in the response body (string index comparison), and that both still appear
before "Select Your Profile" and "News Integration" in that order.

## Out of scope (belongs to later Tier 1b pieces or later tiers)

- New "theme" or "question" entry points as first-class source options (parent
  spec explicitly defers this)
- Removing Moravian Daily Text (confirmed 2026-08-28: stays)
- Renaming the route (`/generate` stays `/generate`; only the sidebar label
  "Workbench" changed, already done in Tier 1a)
- Any visual/CSS changes beyond what Tier 1a's existing `.form-section`,
  `.radio-card`, `.source-tabs` etc. rules already provide — no new styling
