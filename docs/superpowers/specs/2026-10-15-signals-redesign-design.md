# Signals Redesign: Cross-Canon Signals, Generated Every Two Days

Date: 2026-10-15
Status: Draft, awaiting review

## Purpose

Signals today is a weekly keyword-overlap check between the four lectionary
readings. It has no generation step, stores nothing, and rarely surprises.

The new Signals is a feed of standalone, researched signals: a theme that runs
across Scripture, connected to the present world and to books the reader can
chase down. The goal is for a reader to think "I have never seen that before"
and to leave with somewhere to dig deeper.

## Decisions (from the design conversation)

- Subject: a theme that runs across the canon. Not tied to the current
  week's readings.
- Reach: the contemporary illustration spans world events, art, culture,
  news, religion, and science. The "dig deeper" list includes fiction,
  nonfiction, and literature.
- Grounding: live web search for the contemporary illustration and for every
  book. Nothing is named from model memory alone.
- Model: `claude-sonnet-5-5` by default, as one setting (`SIGNALS_MODEL`) so
  it can be raised to `claude-opus-5-5` (or lowered) without a code change.
  Cost matters because the app bills to the Anthropic API key, not a Claude
  subscription. Estimated at roughly $3-5 a month on Sonnet 5.5 (about 15
  signals), $6-10 on Opus 5.5; these are estimates until real usage is
  recorded. Plan: read the first five or six signals, then decide whether
  to move up or down a model.
- Cadence: a new signal at least every two days, generated automatically by a
  scheduled job.
- Replaces the existing keyword-overlap signals entirely.

## The five-part format

Each signal has:

1. **Signal detected**: the theme or pattern, stated plainly, with a title.
2. **Connection**: what it connects to (the passages, figures, or ideas linked).
3. **Nature of the connection**: how they are connected (echo, inversion,
   reversal, fulfillment, tension, shared image, and so on), and why it is
   not obvious.
4. **Intratextual signal**: where the pattern recurs inside the text itself,
   with specific references.
5. **Modern illustration**: where this is visible now (world, art, culture,
   news, religion, or science), tied to a real, searchable source.

Plus a **Dig deeper** list: books and works (fiction, nonfiction, literature)
with author, and a one-line reason each is worth reading.

## Architecture

### Data: `Signal` table (new, in `web/models.py`)

- `id`, `created_at`
- `title`, `theme` (short string, used for repeat-avoidance)
- `signal_detected`, `connection`, `nature_of_connection`,
  `intratextual`, `modern_illustration` (text)
- `modern_illustration_category` (world, art, culture, news, religion, science)
- `dig_deeper` (JSON list of `{title, author, kind, why}`)
- `sources` (JSON list of `{title, url}` from search results)
- `model` (which model produced it)
- `input_tokens`, `output_tokens`, `search_count` (from the response usage,
  so real cost per signal can be checked)

`init_db()` already runs `Base.metadata.create_all()`, so the table is created
on the next deploy with no migration.

### Generation: `web/services/signal_generator.py` (new)

One function, `generate_signal(db)`:

1. Load the last N signals' `theme` and `title` values (N = 30).
2. Call the model with the web search tool and a system prompt (below), told
   to avoid those themes.
3. Parse a JSON object from the response, validate that all required fields
   are present and non-empty, and require at least one source URL and at least
   two `dig_deeper` entries.
4. On a validation failure, retry once. On a second failure, log a warning and
   save nothing.
5. Save the `Signal` row.

Model call settings:

- `model`: `SIGNALS_MODEL` (default `claude-sonnet-5-5`).
- Adaptive thinking left on (Sonnet 5.5's default), and a large `max_tokens` (16000) so thinking cannot
  use up the output budget. `stop_reason == "max_tokens"` counts as a failure
  (nothing saved) and logs a warning.
- Web search server tool: `web_search_20250305` (the older variant; a live
  test used about half the input tokens of `web_search_20260209`), with a
  `max_uses` cap per signal.
- Read only the `text` blocks of the response (as `ClaudeClient` now does).

Prompt rules (kept in `lectionary_engines/protocols/signals_protocol.py`,
matching how the other engines keep their protocols):

- Prefer connections a thoughtful reader would not expect. Reject the obvious
  (a theme everyone already links to the passage).
- Every book and the modern illustration must come from a search result. If
  nothing verifiable is found, return an error object and no signal.
- Output JSON in the schema above. No text outside the JSON.
- Plain, concrete writing. No em dashes (house style, see the humanizer
  feedback).

### Scheduling: in-app loop

- Started from the existing `lifespan` in `web/app.py` as an `asyncio` task
  and cancelled on shutdown.
- Every hour it checks the newest `Signal.created_at`. If none exists or it is
  more than 48 hours old, it runs `generate_signal` in a thread pool (the
  Claude call is blocking).
- Because "is a signal due" is answered from the database, a redeploy or
  restart loses nothing: the next check catches up.
- Single-flight guard so two checks never generate at once (an in-process lock
  plus a re-check of the newest row inside it).
- The loop never raises: any exception is logged and the loop continues.
- A setting, `SIGNALS_ENABLED` (default on), allows turning generation off
  without a deploy. Tests and local dev set it off.

### Display

- `/signals`: signals newest first, three at a time. One card per signal shows
  the title and the five parts in order, then the Dig deeper list and source
  links. An "Explore more signals" link (`/signals?n=6`, `?n=9`, ...) reveals
  three more each time, up to 60. Empty state: "The first signal is on its way."
- Today widget (`index.html`): the latest three signals as compact cards
  (title, signal detected, link to the full card on `/signals`).
- `/signals` and the widget read from the database only; no Claude call happens
  during a page view.

## Removal (replaced code)

- `web/services/signals_service.py` and its use in `web/routes/signals.py` and
  `web/app.py`.
- The `LectionaryThemeCache` model. The table is left in place in the
  database (dropping it is not needed and not reversible).
- `tests/test_signals_service.py` and the keyword-signals cases in
  `tests/test_route_smoke.py`.
- Kept, because other features use them: `extract_themes`,
  `lectionary_engines/liturgical_calendar.py`, and `lectionary_widget_service`.

## Error handling

- Search returns nothing usable, bad JSON, missing fields, or a truncated
  response: nothing is saved, a warning is logged, and the hourly check tries
  again.
- API errors (rate limit, 5xx): logged, retried at the next check. The SDK
  already retries transient errors.
- A failed generation never affects page views.

## Testing

- Generator: a fake client returns canned responses. Cases: valid signal is
  saved; missing field is rejected and retried once; second failure saves
  nothing; `max_tokens` stop saves nothing; recent themes appear in the
  prompt.
- Scheduler due-check: no signals means due; a 47-hour-old signal means not
  due; a 49-hour-old signal means due; concurrent checks produce one signal.
- Routes: `/signals` renders signals and the empty state; the Today widget
  shows the latest three; neither triggers a Claude call.
- One manual live run before shipping, to read an actual signal and check the
  sources.

## Out of scope

- Editing or approving signals before they publish.
- User-facing controls (favorites, sharing, subscriptions).
- Backfilling missed signals after a long gap (one signal per due check).
- Dropping the old `lectionary_theme_cache` table.

## Open items to settle during implementation

- Pick the `max_uses` value for web search from a trial run.
- Recommend a monthly spend limit in the Anthropic Console as a backstop.
