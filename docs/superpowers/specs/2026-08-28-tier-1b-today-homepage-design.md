# Tier 1b — Today Homepage: Design Spec

Third of Tier 1b's four independently-shippable pieces (Engines directory and
Workbench reflow — both shipped — Today homepage, unified Library — see parent
spec section 6). The largest and most complex of the four: it's the only piece
needing new persistent state (a cache table) and new backend logic beyond a pure
template change.

**Parent spec:** `docs/superpowers/specs/2026-08-27-beta-workspace-redesign-design.md`
— design tokens, aesthetic guardrails, and the mockup reference are inherited
from there. Section 6's Tier 1b bullet: "Today ships incrementally: the shell,
This Week in the Lectionary (built from the existing `fetch_rcl`), the three
engine cards, Quick Actions, and Continue Your Studies *without* progress
percentages. The Currents / Signals / Notes widgets appear as their backing
features land in later tiers."

**Depends on Tier 1a** (sidebar shell, Beta tokens) **and the Engines directory
piece** (this design links to `/engines`, which must exist). Branches from
`beta-tier-1a-restyle` (or `main` once merged) and should include the Engines
directory branch's work — either by branching from it directly, or by verifying
`/engines` exists on whatever base this branches from before implementation
starts.

## Problem

`web/templates/index.html` is the current homepage: a hero section, a static
3-engine info grid, and a "Recent Studies" list. The Beta information
architecture renames it "Today" and adds a genuine dashboard element — "This
Week in the Lectionary" — that the current page doesn't have at all.

## Design

### The caching problem (resolved 2026-08-28)

`fetch_rcl(reading_type: str)` (`lectionary_engines/text_fetcher.py:262`) makes
one live, uncached HTTP scrape of Vanderbilt Divinity Library's site per call,
for one reading type. Displaying all four readings (Gospel, Epistle, Hebrew
Scripture/OT, Psalm) on every homepage load would mean 4 live external fetches
on the app's most-visited page, with no existing caching infrastructure
anywhere in this codebase (confirmed: no Redis, no cache table, nothing).
Resolution: cache per-day results in a new DB table, following the existing
`CollisionVectorState` precedent (a small, purpose-specific state table).

### New model: `LectionaryReadingCache`

Added to `web/models.py`:

```python
class LectionaryReadingCache(Base):
    __tablename__ = "lectionary_reading_cache"

    id = Column(Integer, primary_key=True)
    reading_date = Column(Date, nullable=False, index=True)
    reading_type = Column(String(20), nullable=False)  # "gospel", "ot", "psalm", "epistle"
    reference = Column(String(500), nullable=False)
    text = Column(Text, nullable=False)
    fetched_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("reading_date", "reading_type", name="uq_reading_date_type"),
    )
```

New tables are created automatically by `Base.metadata.create_all()` in
`init_db()` — no manual migration step needed (that's only required for adding
a *column* to an *existing* table, per `COLUMN_MIGRATIONS` in
`web/database.py`; a brand-new table needs nothing extra).

### New service: `web/services/lectionary_widget_service.py`

One function: `get_this_week_readings(db: Session) -> dict`. For each of the
four reading types (`"gospel"`, `"epistle"`, `"ot"`, `"psalm"`), check the cache
table for a row matching today's date. On a hit, use it. On a miss, call
`fetch_rcl(reading_type)`, store a new `LectionaryReadingCache` row, and use the
fresh result. If `fetch_rcl()` raises for a given reading type (network failure,
site down, unparseable page), catch it, log it, and omit that one reading from
the returned dict rather than failing the whole function — partial display over
total failure. Returns a dict keyed by reading type, each value either the
reading data (`{"reference": ..., "text": ...}`) or absent if that fetch failed.
`web/app.py`'s `/` route calls this alongside its existing recent-studies query
and passes the result to the template.

### Content decisions (resolved 2026-08-28)

- **Reference only, no thematic summary.** The mockup shows a short summary
  line under each reading (e.g. "Sabbath, hospitality, humility at the table").
  That text isn't produced by `fetch_rcl` — generating it would need a new
  Claude API call or `theme_extractor.py`, both bigger scope than "built from
  the existing `fetch_rcl`" and squarely Tier 2 (Signals) territory. Omitted
  here; each reading card shows only its reference (e.g. "Luke 14:1-14") under
  a category label ("Gospel" / "Epistle" / "Hebrew Scripture" / "Psalm" —
  `reading_type="ot"` displays as "Hebrew Scripture" per Beta terminology,
  mapped in the template, not the data layer).
- **Engine cards link to `/engines`, not a `/generate` preselect.**
  `/generate?engine=X` doesn't exist — the Workbench reflow piece explicitly
  deferred it. Linking to `/engines` (which exists — shipped) lets someone read
  more about a specific engine before committing, and avoids a dead-end
  preselect param that would silently do nothing.
- **Quick Actions: three items, not four.** The mockup shows "Open Workbench"
  and "Start a New Study" as separate entries, but both would point at the same
  `/generate` route today — redundant. This design uses three: "Start a New
  Study" (`/generate`), "View Library" (`/browse`), "Explore Currents"
  (`/currents`).
- **Continue Your Studies has no progress percentages**, per the spec's
  explicit instruction. Reuses the existing recent-studies query
  (`web/app.py`'s current `/` route already does `db.query(Study).order_by(...).limit(5)`)
  — same data, restyled into the new page.

### Page structure — single-column, stacked sections (not a 2-column grid)

The mockup shows a 2-column layout: main content plus a right sidebar with
three widgets (Choose Your Engine, Recent Notes, Quick Actions). Recent Notes
has no backing feature yet (the notes system doesn't exist). Building a
2-column shell for 2-of-3 sidebar widgets now means either an awkwardly sparse
sidebar or reworking the grid layout again once Notes lands. Per the spec's own
"ships incrementally" framing, this design uses a single-column stack instead:

1. **This Week in the Lectionary** — 4 reading cards (Gospel, Epistle, Hebrew
   Scripture, Psalm), each showing category label + reference. Cards with a
   failed fetch are simply omitted (not shown as an error state).
2. **Choose Your Engine** — 3 cards (Threshold, Palimpsest, Collision), each
   linking to `/engines`. Content (name, one-line description) can reuse the
   existing engine info already in `index.html`'s current grid.
3. **Quick Actions** — 3 links: Start a New Study, View Library, Explore
   Currents.
4. **Continue Your Studies** — existing recent-studies list, no progress bars.

`web/templates/index.html` is edited in place (not replaced by a new route) —
`/` stays `/`, only its template content and the route's Python logic change.

## Testing

- `get_this_week_readings()`: unit tests mocking `fetch_rcl` to verify (a) a
  cache hit skips the network call, (b) a cache miss calls `fetch_rcl`, stores
  the result, and returns it, (c) one reading type's `fetch_rcl` failure
  doesn't prevent the other three from succeeding and being returned.
- Route-smoke coverage: `GET /` continues to return 200 (already covered by the
  existing parametrized test); add an assertion that all four category labels
  ("Gospel", "Epistle", "Hebrew Scripture", "Psalm") appear when readings are
  successfully fetched/cached in a test DB.

## Out of scope (belongs to later Tier 1b pieces or later tiers)

- Currents / Signals / Notes widgets (explicitly deferred by the parent spec)
- Thematic summary lines under each reading (Tier 2 territory)
- `/generate?engine=X` preselect (a different, not-yet-scoped Workbench
  follow-up)
- Progress percentages on Continue Your Studies (explicitly deferred)
- The 2-column sidebar layout (revisit once Notes/Signals exist to fill it)
