# Tier 1c — Today Page Chrome & Visual Polish: Design Spec

Not a tier from the parent spec's original numbering (`docs/superpowers/specs/2026-08-27-beta-workspace-redesign-design.md`
only defines Tiers 1-5, where Tier 5 is Constellation — a deferred, unrelated
node-graph feature). This piece closes the visual gap between the live site
and the project's original reference mockup
(`docs/superpowers/specs/assets/beta-workspace-mockup-2026-08-27.png`), which
the parent spec's own Tier 1a/1b work intentionally implemented only
partially — token/palette/shell in 1a, core Today-page widgets in 1b, with
header chrome, sidebar consolidation, reading progress, and the
illustration/quote banner explicitly left for later. It's named 1c because
it's presentational work in the same vein as 1a (no new backend logic beyond
one small, focused progress-tracking feature), not a new numbered tier.

## Investigation findings (2026-08-29)

Confirmed directly against the code (not assumed from the spec text):

- `web/templates/base.html` has no header row at all today — the sidebar and
  `{% block content %}` are the only two elements in `.app-shell`. Each page
  supplies its own `<h1>` inside its content block (e.g. `index.html`'s
  `<h1>Today</h1>`).
- `AuthMiddleware` (`web/app.py`) only validates that the session cookie
  decodes; it never queries the `User` table or attaches user data to the
  request. Every route that needs the current user calls
  `get_current_user(request, db)` (`web/auth.py`) individually as a FastAPI
  dependency. Since a header greeting/avatar needs to appear on every page
  via `base.html`, and touching every route handler to pass a user into its
  template context would be a much bigger footprint than this piece
  warrants, `AuthMiddleware` gets extended to resolve the user once and
  attach it to `request.state.user` — every route already passes `request`
  into its template context today, so `base.html` can read
  `request.state.user` with no changes to any individual route.
- `User` (`web/models.py`) has no avatar/photo field — only `email`, `name`,
  `password_hash`. Avatars are rendered as initials, not photos.
- No concept of "progress" exists anywhere in the data model. `Study`,
  `WorkshopPrep`, `CurrentsAnalysis`, and `CulturalResonance` have no
  per-user, per-item state at all — content is a shared pool, not
  user-owned.
- `.search-bar` (`web/static/css/styles.css:1390-1429`) already exists and is
  used only by `browse.html`'s in-page search. It submits a `q` param that
  `search_library()` (Tier 4) already handles.
- The sidebar's `Workshop`/`Currents`/`Resonance` link group
  (`base.html:26-28`) is already visually separated from the primary group by
  a `.sidebar-divider`, but rendered with identical link styling — no
  de-emphasis today.

## Scope decisions (resolved 2026-08-29, via brainstorming with visual companion)

**In scope:**
1. Header chrome: date, "Welcome back, {first name}," a search bar wired to
   the existing `/browse?q=` search, and an initials-based avatar with a
   dropdown (Profiles, Sign out). **No notification bell, no notification
   system** — dropped entirely, not even as inert UI.
2. Reading progress: scroll-based, tracked per (user, content item), shared
   across all four content types via one new table. Feeds both "Continue
   Your Studies" (already exists, currently has no progress display) and a
   new pinned sidebar widget showing the user's current in-progress read.
3. Sidebar visual regrouping: the existing `Workshop`/`Currents`/`Resonance`
   group gets de-emphasized styling (smaller, muted) to read as secondary —
   no route changes, no page redesigns. This is **not** the parent spec's
   full "folded into Workbench/Library/Signals" end-state (which would mean
   redesigning three generation flows) — that remains explicitly deferred, a
   third time now.
4. Quote banner with the engraved-illustration background, using a real
   asset the user has already generated (see below) rather than a
   placeholder.

**Out of scope, explicitly:**
- A real notes system ("Recent Notes" in the mockup) — a genuinely separate,
  not-yet-scoped piece (backend storage, a notes UI, likely its own detail
  view). Not touched here.
- Full sidebar consolidation (removing the standalone `/workshop`,
  `/currents`, `/resonance` routes and folding their generation forms into
  Workbench/Library) — visual regrouping only, per above.
- "Emerging Currents" (the theme-trend-bar panel) — already ruled out during
  Tier 2 brainstorming; appears in the mockup but nowhere in the parent
  spec's written text for any tier. Not revisited here.
- Any notification system, in any form.

## Design

### 1. Header chrome

`web/templates/base.html` gets a new `<header class="topbar">` between the
opening `.app-shell` markup and `{% block content %}` (rendered once, so it
appears identically on every page — matching how the sidebar already works):

- **Date**: server-rendered via Python (`datetime.now().strftime('%A, %B %d, %Y')`),
  not JS — avoids a flash-of-unstyled-date and matches how `study.html`
  already formats dates server-side.
- **Greeting**: `Welcome back, {{ request.state.user.name.split(' ')[0] }}.`
  — first name only, matching the mockup's "Welcome back, Chris." No
  time-of-day variants (morning/afternoon) — unnecessary complexity for a
  static greeting.
- **Search**: reuses the existing `.search-bar` pattern
  (`styles.css:1390-1429`) — a `<form action="/browse" method="get">` with a
  `name="q"` text input, submitting to the already-built `/browse?q=...`
  search. A `⌘K` hint span sits inside the input (visual only, matching the
  mockup); a small new JS listener in a new `web/static/js/header-search.js`
  focuses the input on `Cmd+K`/`Ctrl+K` — this is the one small new JS
  behavior in an otherwise server-rendered header, added because it's a
  cheap, self-contained enhancement, not because search itself needs JS (the
  form works via plain HTML submission with JS entirely absent).
- **Avatar**: a circular `<button>` showing the user's initials (first
  letter of first and last name-parts, e.g. "Chris Harrison" → "CH"),
  background color deterministically derived from the user's name (a small
  hash-to-hue function, so the same user always gets the same color, and
  different users get visually distinct ones) — no new `User` column, purely
  computed at render time. Clicking opens a small dropdown (`/profiles`,
  sign-out form) — reuses the existing sign-out form already in the sidebar,
  just relocated/duplicated into the header dropdown's markup.

**No notification bell.** Explicitly dropped per the scope decision — the
header has exactly these three elements (date+greeting, search, avatar), not
four.

`request.state.user` is populated by extending `AuthMiddleware`
(`web/app.py`): after decoding the session cookie into a `user_id`, the
middleware opens a plain `SessionLocal()` (not a FastAPI `Depends`-injected
session, since middleware runs outside route dependency injection), queries
the `User` row, attaches it to `request.state.user`, and closes the session
before calling `call_next(request)`. This adds one indexed primary-key
lookup per authenticated request — cheap, and it's the only place this logic
needs to live, since `request` is already threaded into every route's
template context today.

### 2. Reading progress

New model, `ReadingProgress` (`web/models.py`):

```python
class ReadingProgress(Base):
    __tablename__ = "reading_progress"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    content_type = Column(String(20), nullable=False)  # 'study'/'workshop'/'currents'/'resonance'
    content_id = Column(Integer, nullable=False)
    percent = Column(Integer, nullable=False, default=0)  # 0-100, monotonically increasing
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('idx_reading_progress_user', 'user_id'),
        UniqueConstraint('user_id', 'content_type', 'content_id', name='uq_reading_progress_item'),
    )
```

Reuses the exact `content_type` vocabulary Tier 4's `ContentTheme` already
established, for the same reason: one normalized table beats four parallel
per-model columns when the same concept spans four structurally-unrelated
models. New table — `Base.metadata.create_all()` creates it automatically,
no `COLUMN_MIGRATIONS` entry needed (same precedent as `ContentTheme` and
`LectionaryThemeCache`).

**Tracking**: a new `web/static/js/reading-progress.js`, included on the four
content-detail templates (`study.html`, `workshop_result.html`,
`currents_result.html`, `resonance_result.html`), computes
`scrollTop / (scrollHeight - clientHeight) * 100` on scroll, debounced to
save roughly 2 seconds after scrolling stops, via `POST /api/progress` with
`{content_type, content_id, percent}` in the body. A `visibilitychange`/
`pagehide` listener also fires a `navigator.sendBeacon` save as a fallback,
so a save isn't lost if the user navigates away mid-debounce.

**Endpoint**: `POST /api/progress` (`web/app.py`) — authenticated (uses
`require_login`), looks up any existing `ReadingProgress` row for
`(current_user.id, content_type, content_id)`; if the posted `percent` is
higher than what's stored (or no row exists yet), upserts it; if lower
(e.g. the user scrolled back up), the row is left unchanged — progress only
ever increases. Returns `204 No Content` on success; no response body is
needed since this is a fire-and-forget background save, not something the
page's JS branches on.

**Display**:
- "Continue Your Studies" (`index.html`) — each card gets a progress bar and
  percentage, reading `ReadingProgress` for that study (joined in the
  existing recent-studies query, or a small follow-up query — whichever
  keeps `web/app.py`'s `/` route simplest; the implementer's call).
- New sidebar widget (`base.html`, pinned above the sign-out form) — shows
  the single `ReadingProgress` row with the most recent `updated_at` where
  `percent < 100` for the current user, across all four content types (not
  just studies), with its engine/type badge, title, and progress bar,
  linking to that item's detail page. If no in-progress item exists (percent
  is 0 or 100 for everything, or the user has no `ReadingProgress` rows at
  all), the widget doesn't render — no empty-state card needed for a purely
  presentational sidebar accent.

### 3. Sidebar visual regrouping

In `web/templates/base.html`, the existing `Workshop`/`Currents`/`Resonance`
links (already inside their own `.sidebar-divider`-separated group) get a
new modifier class, `.sidebar-link--secondary`, applied only to those three
`<a>` tags — no structural change, no route change. New CSS in
`styles.css`: smaller font-size and muted color (reusing existing muted-text
tokens, not inventing a new one), matching how `Profiles` already reads as
lower-priority in the current sidebar without literally copying its markup
(profiles keeps its own styling; this is a new, separate modifier for this
specific group).

### 4. Quote banner + illustration

New section at the bottom of `index.html` (Today page only — this is a
Today-page accent, not a global footer): a `<blockquote>` with a small
hardcoded Python list of 5-10 quotes (theological/hermeneutical, matching
the mockup's N.T. Wright example) in `web/app.py`'s `/` route, one selected
deterministically by day-of-year modulo list length (`date.today().timetuple().tm_yday % len(QUOTES)`)
so it's stable within a day and rotates daily without needing a database row
or scheduler.

The banner sits over a background illustration: the user has already
generated a real asset (`Codex Image Aug 29, 2026, 10_02_59 AM.png`,
1920×819px, engraved/etched mountain-and-tree line art matching the
aesthetic guardrail's "engraved theological cartography" direction). This
gets copied into the repo at `web/static/images/today-illustration.png` as
part of implementation (not left as an empty slot to fill later, since the
asset already exists). CSS: `background-image`, `background-size: cover`,
`background-position: center`, opacity ~0.13, `mix-blend-mode: multiply` —
exactly the values the aesthetic guardrail section of the parent spec
specifies. `background-size: cover` means the exact source dimensions
aren't load-bearing — if this asset is ever swapped for a different one
later, any reasonably wide/landscape image drops in without CSS changes.

## Testing

- `AuthMiddleware` change: a route-smoke test confirming `request.state.user`
  is populated (e.g. the header's rendered "Welcome back, {name}" text
  appears in an authenticated page's response) and that public paths
  (`/login`, `/health`) still work unauthenticated without error (they skip
  the user-lookup entirely, matching the middleware's existing early-return
  for `PUBLIC_PATHS`).
- Header: search form present with the correct `action`/`name` attributes;
  avatar renders correct initials for a given user name; no notification
  markup anywhere in the rendered header (a regression guard matching this
  spec's explicit "no notifications" decision).
- `POST /api/progress`: unit/route tests — creates a row on first save;
  updates `percent` when the new value is higher; leaves `percent` unchanged
  when the new value is lower (monotonic-increase guarantee); requires
  authentication (401/redirect for an unauthenticated request, matching
  existing auth-dependency behavior elsewhere in the app).
- "Continue Your Studies" and the sidebar widget: each reflects a seeded
  `ReadingProgress` row correctly; the sidebar widget picks the single most
  recently updated in-progress item across mixed content types (not just
  studies), and doesn't render when no in-progress item exists.
- Sidebar regrouping: a route-smoke test confirming the
  `.sidebar-link--secondary` class is present on the Workshop/Currents/
  Resonance links and absent from the primary group.
- Quote banner: renders on `/` with the illustration background present;
  the selected quote is deterministic for a given date (not asserting on
  the mocked date changing this test's outcome, per the existing codebase's
  general avoidance of real-clock-dependent test fragility — freeze
  `date.today()` if needed to assert a specific quote index).

## Out of scope (belongs to a later piece)

- A real notes system
- Full sidebar consolidation (folding Workshop/Currents/Resonance's
  generation forms into Workbench/Library, removing the standalone routes)
- Any notification system
- "Emerging Currents" (already ruled out in Tier 2's brainstorming)
- Theme canonicalization, tradition faceting, and everything else already
  out of scope per Tier 4's design spec (unaffected by this piece)
