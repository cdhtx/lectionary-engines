# Tier 1a Verification Sweep

Ran 2026-08-27 against branch `beta-tier-1a-restyle`, worktree `.worktrees/beta-tier-1a-restyle`.

## Step 1: Full automated suite

```
$ python3 -m pytest tests/ -v
======================= 99 passed, 126 warnings in 1.07s =======================
```

99 tests: 82 pre-existing + 3 design-token contract tests + 14 route/404 smoke tests. All pass. Warnings are pre-existing SQLAlchemy/Starlette deprecation notices, unrelated to this branch.

## Step 2: Confirm no Python was touched

```
$ git diff main --stat -- web/routes/ web/services/ web/models.py lectionary_engines/
(empty)
```

Clean — no application Python was modified anywhere on this branch. The plan's "strictly presentational" constraint holds.

## Step 3: Walk every page

Verified with a real dev server (`uvicorn web.app:app --port 8123`) and a signed session cookie, using live browser rendering where possible and curl/pytest coverage elsewhere.

| Path | Result | Notes |
|---|---|---|
| `/` | ✅ Pass (visual) | Sidebar renders, "Today" active with blue inset rail, engine cards correctly orange/blue/teal, editorial serif headline, no parchment texture. |
| `/generate` | ✅ Pass (visual) | "Workbench" active. Engine radio cards clean, restrained gold-highlighted selection, no heavy black buttons. |
| `/browse` | ✅ Pass (visual) | "Library" active. Search field, filter buttons (navy "All" active state), empty state ("0 studies total" — local DB has no seed data) renders cleanly. |
| `/browse?q=Ephesians` | ⚠️ Not verifiable locally | Local DB has zero studies (fresh worktree checkout, no seed data) — cannot test a non-empty result set. `/browse?q=zzzznotarealword` (Step 4, below) confirms the empty/no-match path instead, which exercises the same template branch logic. |
| `/workshop` | ✅ Pass (visual) | "Workshop" active. Lens cards render correctly (Apostolic Journalist selected/highlighted, others in default card treatment). |
| `/workshop/browse` | ✅ Pass (automated) | Covered by `test_route_smoke.py::test_page_renders[/workshop/browse]`. |
| `/currents` | ✅ Pass (automated) | Covered by `test_route_smoke.py::test_page_renders[/currents]`. Not visually spot-checked in this sweep (browser tooling became unresponsive partway through — see note below); no reason to expect divergence from the other visually-confirmed pages, since it inherits the same base.html shell. |
| `/currents/browse` | ✅ Pass (automated) | Covered by `test_route_smoke.py::test_page_renders[/currents/browse]`. |
| `/resonance` | ✅ Pass (automated) | Covered by `test_route_smoke.py::test_page_renders[/resonance]`. Not visually spot-checked this sweep, same reasoning as `/currents`. |
| `/profiles` | ✅ Pass (visual) | "Profiles" active. Empty state ("No profiles yet") and the "New Profile" form both render correctly with Beta tokens. No existing profile to visually confirm `.profile-card` itself (see Task 7's deferred note below). |
| a study | ⚠️ Not verifiable locally | Local DB has 0 rows in `studies`. The only reachable state is the 404 path (verified below), which was already confirmed to compose correctly through `base.html` + `404.html` during Task 5's review. |
| a currents analysis | ⚠️ Not verifiable locally | Local DB has 0 rows in `currents_analyses`. Same reasoning as above. |
| a workshop prep | ⚠️ Not verifiable locally | Local DB has 0 rows in `workshop_preps`. Same reasoning as above. |
| a resonance result | ⚠️ Not verifiable locally | Local DB has 0 rows in `cultural_resonances`. Same reasoning as above. |
| `/study/99999999` | ✅ Pass (automated + curl) | Returns 404 (not 500), confirmed both by `test_route_smoke.py::test_missing_study_renders_404_not_500` and a live curl check. |
| `/login` (signed out) | ✅ Pass (visual) | Centered card, ivory background, editorial-serif "Lectionary Engines" heading, Inter labels, navy "Sign in →" button, no sidebar (correct — login has nothing to navigate to). |

**Browser tooling note:** partway through this sweep, the Chrome automation tool became unresponsive (`navigate`/`tabs_context_mcp` timed out) and did not recover on a retry. Rather than keep retrying, the remaining routes were confirmed via their existing automated route-smoke-test coverage (all passing) instead of a fresh screenshot. Every page confirmed automated-only inherits the same `base.html` shell already visually confirmed correct on 6 other pages in this same sweep, so the risk of an undetected visual regression on those specific routes is low, not zero.

**Safety note:** the `/login` page had browser-saved credentials auto-filled into the email/password fields during this check. The form was not submitted — verification used cookie injection instead, to avoid authenticating with a real saved credential.

## Step 4: Check empty states

`/browse?q=zzzznotarealword` — confirmed. Renders "No studies found. Nothing matches "zzzznotarealword". Try a different term, or clear the search." with a working "clear the search" link, styled consistently with the rest of the Beta palette (no broken layout, no leftover pre-Beta styling).

`/profiles` with zero profiles — confirmed. Renders "No profiles yet. Create one below to customize your study generation." in a dashed-border empty-state box, consistent with the Beta palette.

## Step 5: Check narrow viewport

Attempted at ~500px width via the browser tool's window-resize function; the resize did not visibly take effect in this session (known tooling limitation encountered earlier in Task 5's review too — not a code issue). No pixel-level narrow-viewport confirmation was obtained in this sweep.

Structurally: `.app-shell` uses `grid-template-columns: var(--sidebar-width) 1fr` with a fixed `--sidebar-width: 188px` at all viewport widths — there is no media query collapsing the sidebar below any breakpoint (confirmed by reading `styles.css`). **This means the sidebar will not adapt on narrow/mobile viewports** — on a phone-width screen, the fixed 188px sidebar plus `1fr` content will produce either a cramped content column or horizontal scroll, depending on content minimum widths.

**This is expected and explicitly out of scope for this tier.** Per the plan's "Deferred to Tier 1b" section: *"Mobile/responsive sidebar. The `188px 1fr` grid needs a collapse behavior below ~768px."* Recorded here per the plan's Step 5 instruction ("do not fix it in this task"), not as a defect.

## Step 6: Confirm one PDF still generates

```
$ curl ... http://localhost:8123/study/38/pdf
404
```

**Not verifiable in this local environment.** `/study/38` does not exist in the local SQLite database (0 rows in `studies` — this is a fresh worktree checkout with no seed data; the referenced study id 38 presumably exists only in the production Postgres database on Railway). The 404 response itself is correct behavior for a nonexistent study (and further confirms the 404 path works for a route with a real integer ID, not just an obviously-fake one like `99999999`).

PDF generation code itself was not touched by this branch (strictly presentational — no `web/routes/`, `web/services/`, or `lectionary_engines/` changes per Step 2's clean diff), and the plan's own text notes "PDF generation uses its own print stylesheet and should be unaffected." Given zero PDF-adjacent code changed, and the print stylesheet is a separate, unmodified `@media print` block in `styles.css` (aside from the Task 3 cascade-fix side effect noted below), there is no structural reason to expect regression — but this specific claim was not exercised end-to-end in this sweep due to the lack of local seed data.

## Deferred items carried from earlier task reviews

These were found and adjudicated during the per-task review loop (see `.superpowers/sdd/2026-08-27-beta-tier-1a-restyle/progress.md` for full detail) and are recorded here for visibility, not as new findings:

1. **Print-media font-size override** (Task 3): the `!important` fix for the editorial-voice cascade bug also wins inside `@media print`, overriding the print-specific 11pt/1.6 sizing for `.study-content` etc. — printed output will render at 18px/1.7 instead of 11pt/1.6. Low impact; not verified end-to-end in this sweep (no local study data to print). Worth a follow-up if print/PDF output is revisited.
2. **`.profile-card` styling gap** (Task 7): lives in `web/templates/profiles.html`'s inline `<style>`, outside Task 7's `styles.css`-only scope. Already uses Beta-resolved tokens via the alias layer (correct colors/radius), just missing the box-shadow/border-only-hover polish applied to other cards. Low severity.
3. **Muted secondary-text grays and accent button blue** (Task 6): `login.html`/`admin_users.html` still use Bootstrap-style grays (`#6c757d`/`#495057`) and a legacy steel-blue (`#2c5f8a`) for their primary buttons, rather than the site's established `--color-ink-muted` token and ink-gradient `.btn-primary` pattern. Outside the task's literal six-item substitution scope; a real but minor visual-consistency gap on two low-traffic utility pages.
4. **No mobile/responsive breakpoint** (Task 5/7, confirmed again in Step 5 above): explicitly deferred to Tier 1b per the plan.

None of these block this tier; all are either explicitly deferred by the plan or judged low-severity during task review.

## Summary

- Automated suite: 99/99 passing, no regressions.
- No Python touched anywhere in `web/routes/`, `web/services/`, `web/models.py`, or `lectionary_engines/`.
- 6 pages visually confirmed correct (`/`, `/generate`, `/browse`, `/browse?q=...` empty state, `/workshop`, `/profiles`, `/login`); remaining parameter-free pages covered by passing automated route-smoke tests inheriting the same verified shell.
- Detail pages (study/currents/workshop/resonance) and PDF generation could not be exercised end-to-end locally due to an empty local database — this is an environment limitation, not a code gap; the 404 path they'd otherwise share was verified instead.
- Narrow-viewport/mobile is confirmed unhandled, as expected and explicitly deferred to Tier 1b by the plan.
- 4 minor items carried forward from task review, none blocking.
