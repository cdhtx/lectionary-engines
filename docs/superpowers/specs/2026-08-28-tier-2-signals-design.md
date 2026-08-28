# Tier 2 — Signals: Design Spec

First piece of Tier 2 of the Beta redesign. Per the parent spec's dependency graph,
Tier 2 has no hard dependency beyond Tier 1 (which is now fully complete — see
`docs/superpowers/specs/2026-08-27-beta-workspace-redesign-design.md` section 6's
dependency order: `1a → 1b → 2 → 3`).

**Parent spec's Tier 2 description (verbatim, section 6):**
> The first tier with real backend logic. Detects genuine thematic overlap across
> this week's readings and recent studies — "3 unexpected connections detected."
> Cheaper than it looks: `theme_extractor.py` already exists and does exactly the
> hard part (passage → theme keywords). Signals extends it to comparison rather
> than inventing new infrastructure. New model, new route; feeds both the Today
> widget and a dedicated page.

This paragraph is intent, not a spec — the sections below resolve everything it
left open.

## Scope decisions (resolved 2026-08-28)

**Readings vs. readings, not readings vs. studies.** The parent spec's text says
"this week's readings and recent studies," but investigation found two problems
with that literal reading: (1) `Study` has no persisted theme data — `extract_themes()`
is called during generation only as an ephemeral input to Currents/Resonance
lookups, never saved — so "recent studies" would need a new column plus a "day
one is empty" launch problem (no connections until enough *new* studies
accumulate with themes attached); (2) the reference mockup's own example
connections ("Jeremiah 2 ↔ Luke 14," "Hebrews 13 ↔ Psalm 81") are mostly pairs
*within* the same week's four readings, not readings-vs-studies pairs. Given
that, and per the same "written spec governs over the mockup" precedent
established earlier in this project, this piece finds overlap **among this
week's own four lectionary readings** (Gospel/Epistle/Hebrew Scripture/Psalm) —
it works from day one with zero historical data dependency, and needs no new
column on `Study`. Readings-vs-studies is a reasonable follow-up once there's a
real study history to mine, not part of this piece.

**Overlap = exact/case-insensitive keyword match**, not semantic/fuzzy
similarity. Both sides of every comparison come from the same `extract_themes()`
prompt (already normalizes to short, concrete keywords like "hospitality,"
"betrayal"), so literal matching is sufficient and matches the spec's own
"doesn't invent new infrastructure" framing — semantic matching would mean
embeddings, which is new infrastructure.

**"Emerging Currents" (the mockup's other Today-dashboard panel, with
Hospitality/Status/Covenant/Reciprocity trend bars) is explicitly out of
scope.** It appears in the mockup image but nowhere in the parent spec's written
text for any tier — it is not part of this piece.

## Problem

Today's homepage deliberately left a widget slot empty for this ("The Currents /
Signals / Notes widgets appear as their backing features land in later tiers" —
parent spec, Tier 1b section). There's also no dedicated page for exploring
connections, and no backend capability to detect them at all.

## Design

### Full text availability

`LectionaryReadingCache` (built for Today's homepage) only stores each reading's
`reference` (e.g. "Luke 14:1-14"), not full text — a later fix round in that
piece dropped the `text` column as unused. `extract_themes(claude, reference,
text)` needs the actual passage text. Resolution: fetch it on-demand via the
existing `TextFetcher().fetch(reference)` (the same Bible Gateway-backed method
already used by `/generate`'s "Bible Gateway" source option) — only when a
reading's themes aren't already cached for the week.

### New model: `LectionaryThemeCache`

Mirrors `LectionaryReadingCache`'s exact shape and rationale (day-of-week
caching to avoid repeated external calls), added to `web/models.py`:

```python
class LectionaryThemeCache(Base):
    """
    Caches each of the upcoming Sunday's four readings' extracted theme
    keywords, so Signals doesn't re-fetch full text and re-call Claude on
    every page load. Mirrors LectionaryReadingCache's day-granularity
    caching pattern.
    """

    __tablename__ = "lectionary_theme_cache"

    id = Column(Integer, primary_key=True)
    reading_date = Column(Date, nullable=False, index=True)
    reading_type = Column(String(20), nullable=False)  # "gospel", "ot", "psalm", "epistle"
    themes = Column(Text, nullable=False)  # JSON array of theme keyword strings
    fetched_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("reading_date", "reading_type", name="uq_theme_date_type"),
    )
```

New table — created automatically by `Base.metadata.create_all()`, no migration
entry needed (same as `LectionaryReadingCache`'s precedent).

### New service: `web/services/signals_service.py`

One function: `get_this_week_signals(db: Session, claude: ClaudeClient) -> list[dict]`.

1. Calls the existing `get_this_week_readings(db)` (from Today's homepage
   service) to get this week's reference per available reading type.
2. For each present reading type, checks `LectionaryThemeCache` for
   (upcoming-Sunday-date, reading_type). On a cache hit, uses the stored theme
   list. On a miss: fetches full text via `TextFetcher().fetch(reference)`,
   calls `extract_themes(claude, reference, text)`, and caches the result
   (even an empty list — `extract_themes` already returns `[]` on failure per
   its own docstring, and caching that avoids retrying a failing extraction on
   every request for the rest of the week).
3. Computes all pairs among the reading types that ended up with a non-empty
   theme list (up to `C(4,2) = 6` pairs, fewer if some types are missing/failed).
   For each pair, computes the case-insensitive set intersection of their theme
   lists — exact string match after lowercasing only (`"Hospitality" ==
   "hospitality"`), no stemming or singular/plural normalization
   (`"outsider"` and `"outsiders"` do not match). `extract_themes()` already
   `.strip()`s each keyword, so no separate whitespace handling is needed here.
4. Filters to pairs with at least one shared theme, sorted by number of shared
   themes descending (most-overlapping pairs first).
5. Returns a list of dicts: `{"reading_a_type": str, "reading_a_label": str,
   "reading_a_reference": str, "reading_b_type": str, "reading_b_label": str,
   "reading_b_reference": str, "shared_themes": list[str]}`. `*_label` is the
   same display mapping Today's homepage already uses (`ot` → "Hebrew
   Scripture," others capitalized). Empty list if fewer than 2 readings have
   themes, or no pairs share a theme.

`ClaudeClient` is instantiated by the caller (route) the same way every other
route in this codebase does — `ClaudeClient(config.anthropic_api_key)` — not
constructed inside the service, matching the existing pattern in
`web/routes/workshop.py`/`web/routes/resonance.py`.

### New route + page: `GET /signals`

A new `web/routes/signals.py` router, `web/templates/signals.html` (extends
`base.html`), calling `get_this_week_signals()` and rendering the connection
list — each pair shown with both readings' labels/references and their shared
theme keywords. Empty state ("No connections detected this week" or similar)
when the list is empty.

### Sidebar nav

`base.html` gets a new `Signals` link, positioned immediately after `Engines`
and still before the first `sidebar-divider` — matching the parent spec's IA
table ordering (Today, Workbench, Library, Engines, Signals, all in the primary
group) and the exact pattern already used when `Engines` itself was added.

### Today homepage widget

`web/templates/index.html` gets a new section, `Signals`, inserted after "This
Week in the Lectionary" and before "Choose Your Engine" (matching the mockup's
vertical ordering). Shows up to 3 of the returned connections (if more than 3
exist, truncate to the top 3 by shared-theme count — keeps the dashboard
compact; the full list is always available on `/signals`), each as a compact
"[Reading A] ↔ [Reading B]" line with a link to `/signals`. `web/app.py`'s `/`
route calls `get_this_week_signals()` alongside its existing `get_this_week_readings()`
call and passes the (possibly truncated) result to the template.

## Testing

- `get_this_week_signals()`: unit tests mocking `TextFetcher.fetch` and
  `extract_themes` to verify (a) a cache hit skips both the fetch and the
  extraction call, (b) a cache miss fetches text, extracts themes, and caches
  the result, (c) two readings with a shared theme produce a correctly-shaped
  connection dict, (d) two readings with no shared themes produce no
  connection for that pair, (e) fewer than 2 available reading types (e.g. a
  `get_this_week_readings()` failure) returns an empty list without error, (f)
  results are sorted by shared-theme count descending when more than one pair
  qualifies.
- Route-smoke coverage: `GET /signals` returns 200; the Today homepage route
  still returns 200 with the new widget section present.

## Out of scope (belongs to a later piece or later tier)

- Readings vs. recent studies (needs `Study.themes` persistence — a real
  follow-up once there's enough study history for it to be useful)
- "Emerging Currents" (mockup-only, not in any tier's written spec)
- Notes system (separate, not-yet-scoped Today widget slot)
- Semantic/fuzzy theme matching (would require new embedding infrastructure)
