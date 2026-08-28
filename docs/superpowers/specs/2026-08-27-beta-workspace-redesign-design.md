# Beta Workspace Redesign — Design Spec

**Date:** 2026-08-27
**Status:** Approved for tiered implementation
**Scope:** Full visual restyle + new information architecture + new functionality

---

## 1. The problem

The current UI is not bad. It is pointed at the wrong future.

Today Lectionary Engines reads as *a beautifully typeset theological journal with some app
controls inside it*. The target is *a serious theological product with editorial depth*.

The mismatch shows up structurally, not cosmetically. The navigation is a list of website
sections (Home, Generate, Workshop, Currents, Resonance, Browse, Profiles). The homepage
explains what the product is rather than showing what it is doing. The Generate page reads
as form submission rather than as entering a method.

**The core shift: from pages to workspace.** A user should not feel like they are clicking
around a website. They should feel like they have entered Lectionary Engines.

## 2. What carries forward

Not a burn-it-down redesign. These are assets and stay:

- **The engine names** — Threshold, Palimpsest, Collision. Distinctive, proprietary, keep.
- **The long-form study reading experience.** The large title, linked scripture references,
  and editorial typography say "this is worth reading" rather than "here is an AI output
  blob." Preserve the center; add intelligence around it.
- **Serif for content.** The theological weight is real and earned.
- **The existing worldview** — interpretation frameworks, sources, profiles, currents,
  resonance. Most software has no worldview. This is a genuine asset.

What gets replaced is the **website-shaped mental model** underneath them.

## 3. Aesthetic guardrails

Verbatim, and binding on every screen:

> **Do not make this look like a church website.**
>
> The interface should feel like a premium research product used by theologians, scholars,
> preachers, and serious students of Scripture.
>
> Use religious history and manuscript traditions as intellectual texture, not decoration.
>
> Avoid stained glass, generic crosses, praying hands, church photography, parchment
> textures, purple AI gradients, and inspirational stock imagery.
>
> Visual reference: editorial publishing + Linear/Notion-style product UI + biblical
> scholarship + antique cartography.

Illustration style, where used: **engraved theological cartography** — antique biblical
atlas, etching, line illustration, topographical imagery, manuscript diagrams. Very low
opacity (~0.13), `mix-blend-mode: multiply`. Never a photograph of Jerusalem.

## 4. Design tokens (authoritative)

**Resolved contradiction — read this before changing any engine color.**

Three earlier artifacts (the current live site, the Beta mockup image, and the written
rationale doc) all specified engine colors as plum / forest green / rust. The CSS token
spec supersedes all three and **remaps every engine color**. This is intentional and
approved. Do not "correct" these back toward the old palette.

Reference: `assets/beta-workspace-mockup-2026-08-27.png` (saved 2026-08-27) is the
dashboard-style mockup referenced above — Today dashboard, Workbench, Library, Engines,
Signals, Currents, Resonance, Browse, Profiles, Settings in the sidebar, plus global
search, notifications, a notes system, and per-study progress tracking. Tier 1a
(the restyle-in-place work) deliberately implements only the visual palette/shell from
this mockup against *existing* routes; the Engines directory, Signals, search, notes,
notifications, and per-study progress are new functionality deferred to Tier 1b/2 — see
the plan's own "Deferred to Tier 1b" section.

| Engine | Old (current live site) | **New (authoritative)** |
|---|---|---|
| Threshold | plum `#6b2d5b` | **burnt orange `#E95B13`** |
| Palimpsest | forest `#1e5631` | **primary blue `#1565B5`** |
| Collision | sienna `#8b2500` | **deep teal `#007D8A`** |

Engine color is load-bearing: badges, progress bars, study headers, the Engines directory.
The long-term goal is that a user recognizes the engine without reading its name.

Also settled: **"Beta" is the design being built. "Alpha" was a separate direction and is
not under consideration.** The orange is deliberately muted from the raw mockup, which
drifted toward Fanta orange in places.

### Core palette

```
Midnight Navy    #071B33      Primary Ink      #10233F
Deep Navy        #0A2342      Secondary Ink    #5E6B78
Warm Ivory       #FAF8F3      Border           #DED8CF
Soft Cream       #F6F2EA
                              Old Gold         #C9962C
Primary Blue     #1565B5
Signal Blue      #3B8EDB      Threshold        #E95B13
Burnt Orange     #E95B13      Palimpsest       #1565B5
Soft Ember       #F47A2A      Collision        #007D8A
Deep Teal        #007D8A
Signal Teal      #13A6B5
```

### Full token set

Transcribe wholesale into `:root`, replacing the current Sacred Manuscript tokens.

```css
:root {
  /* BACKGROUNDS */
  --navy-950: #071B33;   --navy-900: #0A2342;   --navy-850: #0D2D52;
  --ivory-50: #FAF8F3;   --ivory-100: #F6F2EA;  --ivory-200: #EEE8DE;

  /* TEXT */
  --ink-950: #10233F;    --ink-800: #24364D;
  --ink-600: #5E6B78;    --ink-400: #8B949E;

  /* PRIMARY ACCENTS */
  --blue-600: #1565C0;   --blue-500: #1976D2;   --blue-400: #3B8EDB;
  --orange-600: #E55300; --orange-500: #F36C12; --orange-400: #FF8A35;
  --teal-700: #006C78;   --teal-600: #008797;   --teal-500: #13A6B5;

  /* ENGINE COLORS — see remap table above */
  --threshold: #E95B13;  --palimpsest: #1565B5; --collision: #007D8A;

  /* THEOLOGICAL ACCENT */
  --gold-500: #C9962C;   --gold-300: #E2BC63;

  /* BORDERS / SURFACES */
  --border-light: #DED8CF;  --border-medium: #CBC3B8;
  --surface-white: #FFFDFC; --surface-muted: #F4F0E9;

  /* STATES */
  --success: #287A57;    --warning: #D9951E;    --danger: #A93B2A;

  /* SHADOWS */
  --shadow-sm: 0 2px 8px rgba(12, 32, 54, 0.06);
  --shadow-md: 0 8px 24px rgba(12, 32, 54, 0.09);
  --shadow-lg: 0 18px 50px rgba(12, 32, 54, 0.13);

  /* RADII — note: smaller than current site. No giant SaaS marshmallows. */
  --radius-sm: 6px;      --radius-md: 10px;     --radius-lg: 14px;

  /* LAYOUT */
  --sidebar-width: 188px;
  --content-max: 1440px;
}
```

**Component notes carried from the spec:**

- **Sidebar** — vertical gradient `#06182E → #082445 → #061A31`, sticky full-height.
  Active link: `rgba(35,105,185,0.25)` background + `inset 3px 0 0 var(--blue-400)` rail.
  Brand mark in `--orange-400`, Source Serif.
- **Cards** — barely elevated: `rgba(255,255,255,0.58)` on `--border-light`, `--shadow-sm`.
  Hover shifts border to `--border-medium` only.
- **Buttons** — restrained, not the current heavy black. Default is `--surface-white` with
  a `--border-medium` outline; `.button-primary` is `--navy-900`; `.button-accent` is
  `--orange-500`. Hover lifts `translateY(-1px)`.
- **Dashboard grid** — `minmax(0, 1fr) 340px`, gap 22px.
- **Lectionary tiles** — 4-column, divided by `border-right`, serif reference at 1.45rem.
- **Search** — `min(420px, 40vw)`, 42px tall; focus ring
  `0 0 0 3px rgba(25,118,210,0.10)` + `--blue-400` border.

### Typography — the single highest-leverage change

The current design is **too much serif**. That is why it reads as journal rather than
product. Introduce tension between two voices:

- **Editorial serif — Source Serif 4.** Scripture, study titles, theological writing,
  lectionary references.
- **UI grotesk — Inter.** Navigation, labels, metadata, buttons, search, controls, eyebrows.

The UI says *software* while the content says *theology*. That marriage is the point.

Fonts load via the existing `@import` at the top of `styles.css` (line 7) — the current
Cinzel / Cormorant Garamond / Crimson Pro import is replaced, not added to. Note: `@import`
is render-blocking; migrating to a `<link rel="preconnect">` in `base.html` is a reasonable
opportunistic improvement but is not required.

## 5. Information architecture

| Current | Beta |
|---|---|
| Home | **Today** |
| Generate | **Workbench** |
| Browse | **Library** |
| (engine info scattered) | **Engines** |
| (new) | **Signals** |
| Workshop, Currents, Resonance | folded into Workbench / Library / Signals |
| Profiles | secondary (Profile / Settings) |

Sidebar is persistent, navy, near-black rather than royal blue, with a blue inset active
rail. That active-state detail is what makes it read as software rather than a styled
ecclesiastical site.

### "Generate" is retired

The word has acquired baggage: *generate* = AI makes something for me. The product is
richer than that. Workbench reframes the flow:

1. **What are you exploring?** — passage, lectionary date, theme, question, existing study
2. **Choose an engine** — Threshold, Palimpsest, Collision

The engine becomes the *methodology*, not the first form field. The psychology shifts from
"pick a machine and generate content" to "bring a question into a theological method."

## 6. Tiers

Ordered by risk and dependency. Each tier is its own spec → plan → build cycle.

### Tier 1 — Foundation shell *(start here)*

Split into two independently shippable halves. They mix different risk profiles: 1a is a
pure cutover with no new backend surface, 1b introduces new routes. Separating them means
the single riskiest change in the project ships alone, with one obvious cause if anything
breaks.

**Hard constraint on both halves: Tier 1 is strictly presentational.** No changes to
`routes/` logic, `services/`, or `models.py` beyond adding new read-only routes in 1b.
Every existing capability — Claude generation, PDF export, share, email, scripture linking,
cultural grounding — lives in Python and is untouched by definition, not merely by care.
This is what makes "clean new site without broken pipes" structurally achievable rather
than aspirational.

#### Tier 1a — Restyle in place *(no new routes)*

The whole site adopts the Beta look: token replacement in `:root`, font `@import` swap,
navy sidebar app-shell in `base.html`, every existing template restyled in place. Sidebar
uses Beta nomenclature pointing at existing routes (Workbench → `/generate`, Library →
`/browse`).

Touches `styles.css`, `base.html`, and ~11 templates. Touches no Python at all. If any of
the existing 82 tests fail during 1a, the presentational constraint has been violated —
that failure is the signal, not noise.

#### Tier 1b — New pages

Today homepage (replacing the current index), Library unifying the three separate browse
pages (`browse.html`, `currents_browse.html`, `workshop_browse.html`), and the Engines
directory.

Today ships incrementally: the shell, This Week in the Lectionary (built from the existing
`fetch_rcl`), the three engine cards, Quick Actions, and Continue Your Studies *without*
progress percentages. The Currents / Signals / Notes widgets appear as their backing
features land in later tiers.

Workbench 1b delivers the existing paths (passage / lectionary / paste) reflowed into the
new two-step framing. "Theme" and "question" as entry points are new capability, later.

The Library unification query — multi-type filtering and pagination across four content
models — is real logic with clear expected outputs, and is written test-first.

### Tier 2 — Signals

The first tier with real backend logic. Detects genuine thematic overlap across this week's
readings and recent studies — "3 unexpected connections detected."

Cheaper than it looks: `theme_extractor.py` already exists and does exactly the hard part
(passage → theme keywords). Signals extends it to comparison rather than inventing new
infrastructure. New model, new route; feeds both the Today widget and a dedicated page.

### Tier 3 — Palimpsest as spatial experience

Currently the five PaRDeS layers exist only as markdown headers inside one flat content
blob. Making the framework spatial — a left rail where the active layer tracks scroll, or
click-a-layer-reveals-beside-anchored-text — requires those layers to become *addressable
sections*. That is a real parsing and data-shape decision, not CSS.

The distinction that makes this worth doing: today the product gives you *the result of*
Palimpsest. This lets a user *think with* Palimpsest.

### Tier 4 — Library as knowledge graph

Faceting by liturgical season, tradition, source, theme. Blocked on taxonomy fields that do
not exist in the data model today. Currents and Resonance stop being separate tabs and
become *ways the archive reorganizes itself*.

### Tier 5 — Constellation *(deferred, not scheduled)*

A node graph centered on a passage, radiating themes → related texts → traditions →
contemporary currents. Genuinely compelling, and genuinely R&D: graph layout, a new
interaction model, and relationship data that does not yet exist.

**Gate:** revisit only after Signals proves the underlying relationship data is rich enough
to be worth exploring visually. Building it first risks an impressive-looking view over
coincidence.

### Dependency order

```
1a ──> 1b ──> 2 ──> 3
                └──> 4 ──> 5
```

1a → 1b is the only hard sequence. Tier 3 (Palimpsest) has no dependency on Tier 2 and can
run first if the reading experience matters more than Signals.

## 7. Component hierarchy

**Today** — date header + welcome · This Week in the Lectionary (4-up: Gospel / Epistle /
Hebrew Scripture / Psalm) · Emerging Currents (theme chips with meters, T2) · Signals
(T2) · Continue Your Studies (progress T2+) · Choose Your Engine · Recent Notes (T3+) ·
Quick Actions.

**Workbench** — exploration-mode selector · context input · engine selector · preferences
(existing profile + override controls) · submit with existing loading overlay.

**Library** — unified archive across all four content types · type filter · existing search
· card grid · facets (T4).

**Study** — quiet editorial center, intelligence in the rails. Left: layers/structure
(Palimpsest T3). Center: long-form content, preserved. Right: signals, themes, sources,
notes. Existing actions bar (PDF / Share / Email) folds into the new shell.

Meter and progress colors derive from the engine, not a single global accent. Explicitly
avoid "orange soup" — everything defaulting to one accent color.

## 8. Testing strategy

TDD applies unevenly, and pretending otherwise would be theater.

**Test-first (genuine TDD):** Signals detection logic, Palimpsest layer parsing, progress
calculation, any data transformation. Clear inputs, clear expected outputs, no visual
judgment. Same rigor as the existing `scripture_linker.py` / `theme_extractor.py` suites,
written test-first.

**Not TDD — systematic verification instead:** templates and CSS. There is no meaningful
failing assertion for "does this look right." The substitute is route-by-route
verification: every route hit and confirmed rendering, in both empty and populated states,
rather than a sampled spot-check. This is the discipline that caught a stale-server
false positive earlier in this project.

**Regression floor:** the existing 82 tests stay green throughout.

## 9. Risks

| Risk | Mitigation |
|---|---|
| `base.html` is shared by every page — highest blast radius in the codebase | Systematic route-by-route verification, not sampling. Feature branch, not direct-to-main. |
| Sidebar links to pages that do not exist yet → beautiful shell, dead links behind half the nav | Only surface nav items that are built, or honest "coming soon" stubs. Never a link that lies. |
| Partial migration reads as broken even when nothing is failing | Treat Tier 1a as a clean cutover: build the full visual layer on a branch, verify every page, merge as one coherent unit. Never merge a half-restyled site. |
| Engine color remap touches many files; risk of half-migrated color | Tokens are the single source of truth. No hardcoded engine hex anywhere. |
| Design drift across later, deeper screens | This document is the reference. Tokens and guardrails are binding, not suggestions. |

## 10. Out of scope

- **Multi-user accounts, paywall, billing.** Build against today's single shared login.
  When real multi-tenancy arrives it is its own project — half-building it alongside a UI
  redesign would do both badly.
- **OAuth social connections.** Settled: sharing uses the native Web Share API, so each
  user shares through whatever they are already signed into on their own device. No
  per-platform API integration, and this already works correctly under a shared login.
- **Alpha design direction.** Not under consideration.
