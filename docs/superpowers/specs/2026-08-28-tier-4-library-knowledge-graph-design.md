# Tier 4 — Library as Knowledge Graph: Design Spec

Per the parent spec's dependency graph, Tier 4 depends on Tier 2 (Signals) for
`theme_extractor.py`, but not on Tier 3 (Palimpsest) — see
`docs/superpowers/specs/2026-08-27-beta-workspace-redesign-design.md` section 6's
dependency order: `1a → 1b → 2 → 3` with `2 → 4 → 5` branching off separately.
Tiers 1–3 are complete.

**Parent spec's Tier 4 description (verbatim, section 6):**
> Faceting by liturgical season, tradition, source, theme. Blocked on taxonomy
> fields that do not exist in the data model today. Currents and Resonance stop
> being separate tabs and become *ways the archive reorganizes itself*.

This paragraph is intent, not a spec — the sections below resolve everything it
left open.

## Investigation findings (2026-08-28)

The unified Library (`/browse`, `web/services/library_service.py`) unions four
independent SQLAlchemy models — `Study`, `WorkshopPrep`, `CurrentsAnalysis`,
`CulturalResonance` — with **no shared base model**; the common shape
(`content_type`, `title`, `badge_label`, `created_at`) is a query-time
projection, not a schema-level abstraction. No taxonomy field exists anywhere
in the data model, structured or informal:

- **Season**: not stored anywhere, and can't be reliably backfilled — `Study`/
  `WorkshopPrep` have no reading-date field, only `created_at` (generation
  time) and `reference` (the passage text).
- **Tradition**: appears only as prose inside LLM prompts (e.g.
  `currents_protocol.py`), never as structured, queryable data.
- **Theme**: the only real seed. `CulturalResonance.themes` (`web/models.py:304`)
  is a free-text JSON array, generated per-row by Claude, never normalized.
  `lectionary_engines/theme_extractor.py::extract_themes()` is the shared
  extraction primitive already used by Resonance and Signals (Tier 2) —
  5-8 short, concrete, lowercase-normalizable keywords — but its output is
  never persisted onto `Study`/`WorkshopPrep`/`CurrentsAnalysis`.
- **Source**: `Study.source`/`WorkshopPrep.source` (`paste`/`run`/`moravian`/
  `rcl`) already exists as a real controlled field, but `CurrentsAnalysis` and
  `CulturalResonance` have differently-shaped "source" concepts
  (`news_source`, `sources_used`) that don't unify with it.

Currents and Resonance are two of the four unioned Library content types, plus
their own standalone routes (`web/routes/currents.py`, `web/routes/resonance.py`).
The sidebar (`web/templates/base.html:27-29`) already links `/currents` and
`/resonance` as the **generation forms**, not browse pages — `/currents/browse`
(`web/routes/currents.py:128`, `currents_browse.html`) is a separate,
unlinked-from-nav browse page reachable only via a "Browse Past" button on
`currents_result.html:36`. Resonance has no standalone browse page at all
today.

## Scope decisions (resolved 2026-08-28)

**Tradition is out of scope.** No data source exists for it anywhere in the
app, and inventing one (LLM classification or manual tagging) is a new
capability, not a faceting problem. Revisit only if a real signal emerges.

**Theme facet ships as free text now, canonicalized later.**
`extract_themes()`'s output is persisted as-is (no fixed vocabulary, no
synonym table). "Outsider" and "outsiders" will show as separate facet values
at launch. Canonicalization is a real follow-up once actual theme-value
distribution is visible — designing a closed vocabulary before seeing real
data risks getting it wrong twice.

**Season ships for RCL-sourced content going forward only.** A new
`reading_date` column is added to `Study`/`WorkshopPrep`, populated only when
`source == "rcl"` (the only case where a reading is actually tied to a
lectionary Sunday — a pasted or Bible-Gateway-fetched passage has no inherent
season). Existing rows and non-RCL rows have no season, correctly, since
there's no reliable way to recover a historical reading date for them.

**Source facet is scoped to Study/WorkshopPrep only.** It surfaces
`paste`/`run`/`moravian`/`rcl` and only applies (is shown/filterable) when
`content_type` is `study` or `workshop`. `CurrentsAnalysis.news_source` and
`CulturalResonance.sources_used` are not folded into this facet — they
describe a different kind of thing (an external artifact cited, not how the
content itself was obtained) and forcing them into one facet would be
misleading.

**Currents/Resonance browse pages are removed; generation forms stay.**
`/currents/browse` and its template are deleted (the sidebar never linked to
it; its one internal link, `currents_result.html:36`, is repointed to
`/browse?content_type=currents`). Resonance has no browse page to remove.
`content_type` becomes one facet among several on the unified `/browse` page.
The `/currents` and `/resonance` generation-form routes, and their sidebar
links, are unchanged — this is exactly what "stop being separate tabs and
become ways the archive reorganizes itself" means concretely: browsing past
Currents/Resonance output happens only through the faceted Library now, while
*creating* new Currents/Resonance content stays where it is.

## Design

### New table: `content_theme`

A normalized association table, not per-model JSON columns. The four content
models are structurally unrelated (no shared base), so a purpose-built table
keyed by `(content_type, content_id)` is the only way to facet theme uniformly
across them with plain indexed SQL — matching the existing precedent of
`LectionaryThemeCache` being a separate table rather than a column bolted onto
`Study`. JSON-column filtering (the alternative) would mean fragile `LIKE`
matching on serialized JSON that behaves differently on SQLite (dev) vs.
Postgres (prod, per `web/database.py:14-17`), and can't cheaply produce
"how many items are tagged X" facet counts.

```python
class ContentTheme(Base):
    """
    One row per (content item, theme keyword) pair, spanning all four
    Library content types. Powers theme faceting/filtering uniformly
    across Study/WorkshopPrep/CurrentsAnalysis/CulturalResonance without
    requiring a shared base model between them.
    """

    __tablename__ = "content_theme"

    id = Column(Integer, primary_key=True, autoincrement=True)
    content_type = Column(String(20), nullable=False)  # 'study'/'workshop'/'currents'/'resonance'
    content_id = Column(Integer, nullable=False)
    theme = Column(String(100), nullable=False)  # lowercase, trimmed
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('idx_content_theme_theme', 'theme'),
        Index('idx_content_theme_item', 'content_type', 'content_id'),
        UniqueConstraint('content_type', 'content_id', 'theme', name='uq_content_theme_item_theme'),
    )
```

New table — created automatically by `Base.metadata.create_all()`, no
migration entry needed (same as `LectionaryThemeCache`'s precedent, per
`docs/superpowers/specs/2026-08-28-tier-2-signals-design.md:95-96`).

### New columns: `Study.reading_date`, `Study.season`, `WorkshopPrep.reading_date`, `WorkshopPrep.season`

```python
reading_date = Column(Date, nullable=True, index=True)
season = Column(String(30), nullable=True, index=True)  # 'advent', 'christmas', 'epiphany', 'lent', 'holy_week', 'easter', 'pentecost', 'ordinary_time'
```

Both nullable, both populated together, only when `source == "rcl"`. `season`
is stored precomputed rather than derived at query time — Lent/Easter/Pentecost
are moveable feasts tied to a given year's Easter date, which isn't expressible
as a plain SQL `WHERE`. Storing the computed value keeps facet filtering a
plain equality check and keeps pagination correct (matching
`library_service.py`'s existing warning against post-hoc Python filtering
breaking page boundaries, `web/services/library_service.py:7-9`).

Added via `web/migrations/003_add_theme_and_season.py`, following the existing
migration pattern (`001_add_user_profiles.py`, `002_add_news_to_studies.py`) —
unlike the new table, existing tables' new columns need an explicit migration
since `create_all()` doesn't alter existing tables.

### New utility: `lectionary_engines/liturgical_calendar.py`

One function: `season_for_date(d: date) -> str`. Computes the given year's
Easter date via the standard Gregorian Easter algorithm (Meeus/Jones/Butcher),
then buckets `d` by offset from Easter and from December 25 into the eight
season values listed above (Advent starts the fourth Sunday before Christmas;
Christmastide runs to Epiphany, Jan 6; Epiphany to Ash Wednesday; Lent to Holy
Week, i.e. Palm Sunday to Holy Saturday; Easter to Pentecost, i.e. Easter
Sunday + 49 days; Ordinary Time fills the rest). Pure function, no DB/network
access, easy to unit test exhaustively against known reference dates (e.g.
Easter 2026 = April 5).

### Populating `reading_date`/`season` and `content_theme` at generation time

`web/routes/studies.py` and `web/routes/workshop.py`, at the point each saves
its new row:

- If `source == "rcl"`: set `reading_date = _upcoming_sunday(date.today())`
  (promote `lectionary_widget_service.py:37`'s `_upcoming_sunday()` to a
  public, shared helper rather than duplicating the one-liner) and
  `season = season_for_date(reading_date)`.
- Always (all sources): ensure theme keywords exist for the new row and
  persist them into `content_theme`. `studies.py` already conditionally
  computes `passage_themes = extract_themes(...)` when auto-news-integration
  or cultural grounding is needed (`web/routes/studies.py:189-196`) — reuse
  that result when present; call `extract_themes()` fresh otherwise (it must
  run unconditionally now, since Tier 4 needs themes on every row, not just
  rows that happened to need them for another feature). `workshop.py` has no
  existing `extract_themes()` call — add one. Each theme string is
  lowercased and trimmed before insertion (matching Signals' existing
  case-insensitive convention, `signals_service.py`) and inserted as one
  `ContentTheme` row per keyword.

`web/routes/currents.py::analyze_story` and `web/routes/resonance.py::find_resonances`
get the same treatment: `CurrentsAnalysis` has no existing theme source, so
call `extract_themes()` on `story_context` after saving. `CulturalResonance`
already has its theme list in hand at save time (the `theme_list` the user
submitted or Claude derived, `resonance.py:100`/`269`) — no new Claude call
needed, just insert those into `content_theme` alongside the existing
`themes` JSON column (which stays, unchanged, for its current display use in
`resonance_result.html`).

### Facet query changes: `web/services/library_service.py`

Each `_*_select()` builder gains two more projected columns, `NULL`-filled
where not applicable, so the combined `union_all()` subquery has a uniform
shape to filter on:

- `source` (populated for study/workshop, `NULL` for currents/resonance)
- `season` (populated for RCL-sourced study/workshop rows, `NULL` otherwise)

`search_library()` gains three new optional parameters: `theme: Optional[str]`,
`season: Optional[str]`, `source: Optional[str]`.

- `season`/`source` filters are plain `WHERE subquery.c.season == season` /
  `WHERE subquery.c.source == source` on the combined subquery — cheap, index-backed
  via the new columns' indexes.
- `theme` filter joins the subquery against `content_theme`: `WHERE EXISTS
  (SELECT 1 FROM content_theme ct WHERE ct.content_type = subquery.c.content_type
  AND ct.content_id = subquery.c.id AND ct.theme = :theme)`. All active
  filters combine with AND (existing `content_type`/`q` filters included) —
  matching the existing single-condition-per-clause style already in
  `library_service.py`.

A second function, `get_library_facets(db: Session) -> dict`, returns the
values to populate filter controls: distinct `season` values present (fixed
order matching the liturgical calendar, not alphabetical), distinct `source`
values present, and `SELECT theme, COUNT(*) FROM content_theme GROUP BY theme
ORDER BY COUNT(*) DESC` for theme (no cap — data volume here is small enough
that a full list is fine; revisit if that stops being true). Facet counts are
**not** re-scoped to the currently-active filter selection (i.e. not a fully
faceted-search "counts update as you filter" experience) — that's a real
enhancement but adds real query complexity for a v1 whose main job is making
filtering possible at all.

### `/browse` route and template

The `/browse` route (`web/app.py:272`) passes `theme`,
`season`, `source` query params through to `search_library()`, and calls
`get_library_facets()` to render filter controls. All active filters are
reflected in the URL as query params (`?content_type=study&season=lent&theme=hospitality`),
making filtered views shareable/bookmarkable and giving prev/next pagination
links a stable basis, consistent with how `content_type`/`q`/`page` already
work in the existing template.

`currents_result.html:36`'s "Browse Past" link changes from `/currents/browse`
to `/browse?content_type=currents`. `web/routes/currents.py`'s `browse_currents`
route and `web/templates/currents_browse.html` are deleted.

### Backfill: `web/scripts/backfill_content_themes.py`

One-time management script, run manually post-deploy (matching how this
project has handled prior one-time data needs — no scheduled/automatic
trigger):

1. **`CulturalResonance`**: for every row, parse its existing `themes` JSON
   column and insert corresponding `content_theme` rows. No new Claude calls
   — this data already exists, just ungoverned.
2. **`Study`, `WorkshopPrep`, `CurrentsAnalysis`**: for every row lacking
   `content_theme` entries, call `extract_themes()` against its content
   (`Study.content`/`WorkshopPrep.content` truncated the same way generation
   does; `CurrentsAnalysis.story_context`) and insert the results. This is
   the one-time LLM cost — proportional to existing row count, using the
   same cheap Haiku model `theme_extractor.py` already specifies.
3. Idempotent: skips any `(content_type, content_id)` that already has
   `content_theme` rows, so it's safe to re-run (e.g. after an interrupted
   run, or after new backfill-eligible rows accumulate from a bug fix).
4. No `reading_date`/`season` backfill — per the scope decision above, old
   RCL-sourced rows have no reliable historical reading date to recover, so
   they stay unclassified by season permanently. This only affects
   *filtering*; the rows remain fully visible and theme-facetable.

## Testing

- `season_for_date()`: unit tests against known reference dates spanning
  several years (Easter's date moves ±5 weeks year to year) — at minimum one
  date inside each of the 8 seasons, plus boundary dates (Ash Wednesday,
  Palm Sunday, Pentecost Sunday itself) to confirm bucket edges are correct.
- `search_library()`: unit tests for each new filter in isolation and
  combined with existing `content_type`/`q` filters (AND semantics); a theme
  filter matching zero items; a season/source filter on a content type where
  that facet is always `NULL` (e.g. `season=lent&content_type=currents`
  correctly returns nothing rather than erroring).
- `get_library_facets()`: returns expected distinct values and counts against
  a small fixture dataset.
- Generation-time persistence: `studies.py`/`workshop.py` tests confirming an
  RCL-sourced save gets `reading_date`/`season` populated and a non-RCL save
  doesn't; all four save paths (`studies`, `workshop`, `currents`, `resonance`)
  confirmed to produce the expected `content_theme` rows.
- Backfill script: idempotency (running twice produces no duplicate rows,
  respects the `UniqueConstraint`), and that `CulturalResonance` backfill
  makes zero Claude calls while the other three types make exactly one per
  row lacking themes.
- Route-smoke coverage: `GET /currents/browse` no longer resolves (404);
  `GET /browse` with each new filter param individually returns 200;
  `currents_result.html`'s browse-past link points at the new URL.

## Out of scope (belongs to a later piece or later tier)

- Tradition faceting (no data source exists; a real follow-up if one emerges)
- Theme canonicalization/synonym mapping (ship free-text first, see real
  distribution, revisit)
- Season for historical/pre-Tier-4 RCL content (no reliable recovery path)
- Fully faceted search (counts that re-scope live as filters are applied)
- Folding Currents/Resonance *generation* into the Library page itself (only
  their browse/list experience folds in; creation stays where it is)
- Tier 5 (Constellation) — explicitly deferred and not scheduled per the
  parent spec
