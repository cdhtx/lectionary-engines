# Tier 1b — Workbench Reflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorder `/generate`'s existing form sections so "what you're exploring" (text source) comes before "choose an engine," per the Beta information architecture's "Generate is retired" reframing.

**Architecture:** Pure template reorder within one file — no new fields, no JS changes, no Python changes. Four existing `<div class="form-section">` blocks get relocated/relabeled; their internal contents (every `name=`/`id=` attribute and all associated `<script>` behavior) are untouched.

**Tech Stack:** Jinja2 template only.

## Global Constraints

- **Branch from `beta-tier-1a-restyle`** (or `main` once that PR has merged) — same as the Engines directory piece, for the sidebar shell and Beta CSS tokens this template relies on.
- **Pure reorder + relabel. No new capability.** All four existing source tabs (Paste Text, Bible Gateway, Moravian Daily Text, RCL) stay. Profile selection and News Integration stay as later steps, content unchanged. Confirmed 2026-08-28: do not remove Moravian, do not add theme/question as new entry types (deferred).
- **No `name=`/`id=` attribute changes anywhere.** The POST handler in `web/routes/studies.py` and every line of the existing `<script>` block read fields by name/ID, not DOM position — changing any of those would be a functional regression, not a reflow.
- **Only `web/templates/generate.html` is touched.** No Python files.
- **The existing test suite must stay green** (102 tests as of the Engines directory piece).

---

### Task 1: Reorder and relabel the form sections

**Files:**
- Modify: `web/templates/generate.html`
- Modify: `tests/test_route_smoke.py`

**Interfaces:**
- Consumes: nothing from other Tier 1b pieces — self-contained.
- Produces: nothing consumed by later tasks — this is the only task in this plan.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_route_smoke.py`:

```python
def test_workbench_reflow_orders_sections_correctly(client):
    response = client.get("/generate")
    assert response.status_code == 200
    body = response.text
    exploring_idx = body.find("What are you exploring?")
    engine_idx = body.find("Choose an Engine")
    profile_idx = body.find("Select Your Profile")
    news_idx = body.find("News Integration")
    assert exploring_idx != -1, "Missing 'What are you exploring?' heading"
    assert engine_idx != -1, "Missing 'Choose an Engine' heading"
    assert profile_idx != -1, "Missing 'Select Your Profile' heading"
    assert news_idx != -1, "Missing 'News Integration' heading"
    assert exploring_idx < engine_idx < profile_idx < news_idx, (
        "Sections are not in the expected Workbench order: "
        "What are you exploring? -> Choose an Engine -> Select Your Profile -> News Integration"
    )
```

- [ ] **Step 2: Run it to confirm it fails**

```bash
python3 -m pytest tests/test_route_smoke.py -v -k "test_workbench_reflow_orders_sections_correctly"
```

Expected: FAIL. In the current file, "Choose an Engine" (heading text, no "1.") appears before "What are you exploring?" (which doesn't exist yet at all) — the `find()` for it returns `-1`, so the `assert exploring_idx != -1` line fails first.

- [ ] **Step 3: Read the current file and locate the four section boundaries**

```bash
grep -n "form-section\|<h2>" web/templates/generate.html
```

You should see four `<div class="form-section">` blocks with these headings, in this order: `1. Choose an Engine`, `2. Select Your Profile`, `3. Choose Text Source`, `4. News Integration <span ...>(optional)</span>`. Note the exact line numbers your `grep` reports — they should be close to (but confirm exactly, in case of drift): the "Choose an Engine" block opens right after the `<form ...>` tag and its `</div>` closes right before the "Select Your Profile" block opens; the "Choose Text Source" block's `</div>` closes right before the "News Integration" block opens.

- [ ] **Step 4: Move the "Choose Text Source" block to the front**

Cut the entire third `<div class="form-section">...</div>` block (the one with `<h2>3. Choose Text Source</h2>` and the four source tabs — Paste Text, Bible Gateway, Moravian Daily Text, RCL — plus all their nested fields) and paste it immediately after the `<form method="POST" action="/generate" class="generate-form" id="generateForm">` opening tag, so it becomes the *first* `form-section` block. Do not alter anything inside this block except its heading text (next step) — every `name=`, `id=`, `placeholder=`, and nested `<div>` stays byte-for-byte identical, just relocated.

This single move is sufficient to produce the full desired order: the "Choose an Engine" and "Select Your Profile" blocks were never touched, so they keep their existing relative order and end up second and third; "News Integration" was already last and stays last.

- [ ] **Step 5: Update the four heading texts**

In the block you just moved (now first), change:

```html
<h2>3. Choose Text Source</h2>
```

to:

```html
<h2>1. What are you exploring?</h2>
```

In the "Choose an Engine" block (now second), change:

```html
<h2>1. Choose an Engine</h2>
```

to:

```html
<h2>2. Choose an Engine</h2>
```

In the "Select Your Profile" block (now third), change:

```html
<h2>2. Select Your Profile</h2>
```

to:

```html
<h2>3. Select Your Profile</h2>
```

The "News Integration" block's heading does **not** change — it was already numbered 4 and stays last, so `<h2>4. News Integration <span ...>(optional)</span></h2>` is untouched.

- [ ] **Step 6: Run the new test to confirm it passes**

```bash
python3 -m pytest tests/test_route_smoke.py -v -k "test_workbench_reflow_orders_sections_correctly"
```

Expected: PASS.

- [ ] **Step 7: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS, 0 failures. Pay particular attention to `test_page_renders[/generate]` — a mistake in the HTML move (e.g. an unclosed `<div>`) could still return 200 with malformed markup that this specific test wouldn't catch, but a badly broken Jinja template (mismatched blocks) would raise a `TemplateSyntaxError` and fail loudly here.

- [ ] **Step 8: Verify by eye**

Start the dev server (`uvicorn web.app:app --port 8123`, using the venv at the repo root), sign in, visit `/generate`. Confirm: "1. What are you exploring?" is the first section with all four source tabs working (click each tab, confirm its fields show/hide correctly — this exercises the unmoved `<script>` tab-switching logic against the relocated markup), "2. Choose an Engine" second, "3. Select Your Profile" third (profile dropdown still populates — exercises the unmoved profile-loading JS), "4. News Integration" last. Fill in a minimal paste-source submission (reference + text) and confirm the loading overlay still appears on submit (exercises the unmoved submit-handler JS) — you do not need to wait for a real Claude generation to complete; canceling/navigating away after confirming the overlay appears is sufficient.

- [ ] **Step 9: Commit**

```bash
git add web/templates/generate.html tests/test_route_smoke.py
git commit -m "Reflow Workbench: text source before engine selection

Reorders /generate's form sections per the Beta information architecture's
'Generate is retired' reframing (parent spec section 5): what you're
exploring now comes before which engine interprets it, not after.

Pure reorder + relabel — no name/id attribute changes, no JS changes, no
Python changes. All four existing source options (Paste, Bible Gateway,
Moravian, RCL) and the Profile/News Integration sections are unchanged,
just renumbered."
```

---
