# Tier 1c — Today Page Chrome & Visual Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the visual gap between the live site and the original beta workspace mockup — header chrome, scroll-based reading progress, sidebar visual regrouping, and a quote banner with a real illustration.

**Architecture:** `AuthMiddleware` is extended to attach the current user to `request.state`, so the header (rendered once in `base.html`, on every page) needs no per-route changes. A new `ReadingProgress` table and service module track scroll-based reading progress uniformly across all four content types, fed by a small debounced-save endpoint and a client-side JS tracker; two display surfaces (the sidebar widget and "Continue Your Studies") both read from the same service functions. The quote banner and illustration are pure template/CSS additions using an asset the user has already generated.

**Tech Stack:** FastAPI, SQLAlchemy, Jinja2, vanilla JS (matching `content-actions.js`'s established IIFE/`var` style), pytest.

## Global Constraints

- **No notification bell, no notification system, in any form.** Not even inert UI.
- **No real notes system.** Out of scope entirely for this plan.
- **No full sidebar consolidation.** `/workshop`, `/currents`, `/resonance` keep their existing routes and generation forms untouched — only their sidebar link styling changes (visual de-emphasis), not their structure or the app's routing.
- **Reading progress only ever increases** for a given `(user, content_type, content_id)` — a lower `percent` value posted after a higher one must not overwrite it.
- **`content_type` vocabulary is `"study"` / `"workshop"` / `"currents"` / `"resonance"`** — reuse Tier 4's exact strings (`web/services/library_service.py`), not new ones.
- **`ReadingProgress` is a new table, not new columns** — `Base.metadata.create_all()` creates it automatically, no `COLUMN_MIGRATIONS` entry in `web/database.py`.
- **JS style:** match `web/static/js/content-actions.js`'s existing conventions exactly — IIFE wrapper (`(function () { ... })();`), `var` declarations, `function` expressions, no arrow functions, no `const`/`let`.
- **The existing test suite must stay green** (175 tests at branch point — confirm the exact count via `python3 -m pytest tests/ -v` before starting, don't assume it hasn't drifted).

---

### Task 1: Attach the current user to `request.state`

**Files:**
- Modify: `web/app.py` (the `AuthMiddleware` class, `~line 54-69`)
- Test: `tests/test_route_smoke.py`

**Interfaces:**
- Produces: after this task, every authenticated request has `request.state.user` set to the logged-in `User` object (or left unset/`None`-equivalent only on public paths, which never reach the lookup). Every later task in this plan reads `request.state.user` from `base.html`'s Jinja context (Jinja templates receive `request` already, unchanged) rather than requiring any route handler to pass a user explicitly.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_route_smoke.py`:

```python
def test_authenticated_request_populates_request_state_user(client):
    response = client.get("/engines")
    assert response.status_code == 200
    # /engines is fully static (no template context beyond request) but the
    # middleware should still have populated request.state.user before the
    # route ran - the response text doesn't reflect this directly, so we
    # check it can't have broken by asserting the page still renders full
    # HTML rather than an error page.
    assert "<html" in response.text.lower()


def test_public_path_does_not_require_user_lookup(client):
    response = TestClient(app).get("/health")
    assert response.status_code == 200
```

Note: `request.state.user` isn't independently visible through a page response body yet — Task 5 (the header) is what actually renders it, and that task's own tests assert on the visible "Welcome back, {name}" text, which is the real proof this task's middleware change works. This task's tests exist to confirm the middleware change itself doesn't break existing authenticated/public request handling — a regression guard, not a feature-visibility test (there's no feature to see yet).

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
python3 -m pytest tests/test_route_smoke.py -v -k "request_state_user or public_path_does_not_require"
```

Expected: both currently PASS already (this task doesn't change existing visible behavior) — this is one of the rare cases where the "new" tests pass before the implementation, because they're regression guards for a change that has no independently-visible effect yet. That's fine; proceed to the implementation and re-run afterward to confirm they *still* pass (i.e., the middleware change didn't break anything).

- [ ] **Step 3: Extend the middleware**

In `web/app.py`, find:

```python
class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # Always allow: login/logout/static/health/admin (admin has its own Basic Auth)
        if (
            path in PUBLIC_PATHS
            or path.startswith("/static/")
            or path.startswith("/admin/")
        ):
            return await call_next(request)

        token = request.cookies.get(COOKIE_NAME)
        if not token or not decode_session_cookie(token):
            return RedirectResponse(url=f"/login?next={path}", status_code=303)

        return await call_next(request)
```

Replace with:

```python
from contextlib import contextmanager


@contextmanager
def _middleware_db():
    """
    AuthMiddleware runs outside FastAPI's dependency injection (it's raw
    ASGI middleware, not a route with Depends()), so it can't use
    Depends(get_db) directly. Calling SessionLocal() straight from here
    would silently bypass app.dependency_overrides[get_db] - which is
    exactly what every test fixture in this codebase uses to point routes
    at an in-memory test database instead of the real lectionary.db. This
    helper looks up whatever provider is currently active for get_db
    (the test override if one is set, the real get_db otherwise) and
    drives its generator manually, the same way FastAPI's own dependency
    resolution would, including running its cleanup (db.close()) when
    this context manager exits.
    """
    provider = app.dependency_overrides.get(get_db, get_db)
    db_gen = provider()
    db = next(db_gen)
    try:
        yield db
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # Always allow: login/logout/static/health/admin (admin has its own Basic Auth)
        if (
            path in PUBLIC_PATHS
            or path.startswith("/static/")
            or path.startswith("/admin/")
        ):
            return await call_next(request)

        token = request.cookies.get(COOKIE_NAME)
        user_id = token and decode_session_cookie(token)
        if not user_id:
            return RedirectResponse(url=f"/login?next={path}", status_code=303)

        # Attach the current user to request.state so base.html's header
        # (rendered on every page) can read request.state.user directly -
        # every route already passes `request` into its template context,
        # so no individual route handler needs to change. Tasks 5 and 6
        # add more request.state attachments inside this same `with`
        # block (reusing the one db session for the whole request rather
        # than opening several) - do not close this block off here in a
        # way that later tasks can't extend.
        with _middleware_db() as db:
            request.state.user = db.query(User).filter(User.id == user_id, User.is_active == True).first()

        return await call_next(request)
```

**Important — this function must be defined *after* `app = FastAPI(...)` and `get_db` are both in scope**, since `_middleware_db()` references `app.dependency_overrides` and `get_db` by name. Python resolves names inside a function body at call time, not definition time, so this works correctly even though `AuthMiddleware`/`_middleware_db` are defined textually *before* `app = FastAPI(...)` appears later in the file (the middleware is never actually invoked until the app is fully constructed and handling requests) — but place `_middleware_db()` and the modified `AuthMiddleware` class in the same location they already occupy in the file; don't move them below `app = FastAPI(...)`, since `app.add_middleware(AuthMiddleware)` needs the class defined first and the codebase's existing structure already relies on this ordering for other reasons.

`User` needs to be importable in `web/app.py` — it already is (`from .models import Base, Study` is the current import line; change it to `from .models import Base, Study, User`). `get_db` is already imported (`from .database import init_db, close_db, get_db`).

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
python3 -m pytest tests/test_route_smoke.py -v -k "request_state_user or public_path_does_not_require"
```

Expected: both PASS.

- [ ] **Step 5: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS, 0 failures.

- [ ] **Step 6: Commit**

```bash
git add web/app.py tests/test_route_smoke.py
git commit -m "Attach the current user to request.state in AuthMiddleware

Lets base.html's header read request.state.user directly on every
page without touching every route handler's template context. One
extra indexed primary-key lookup per authenticated request.

See docs/superpowers/specs/2026-08-29-tier-1c-today-chrome-design.md."
```

---

### Task 2: `ReadingProgress` model and service

**Files:**
- Modify: `web/models.py` (add `ReadingProgress`)
- Create: `web/services/reading_progress_service.py`
- Test: `tests/test_reading_progress_service.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `web.models.ReadingProgress` (new model). `save_progress(db: Session, user_id: int, content_type: str, content_id: int, percent: int) -> None` — upserts, only increasing `percent`, never decreasing it. `get_current_read(db: Session, user_id: int) -> Optional[dict]` — returns `{"content_type": str, "content_id": int, "percent": int}` for the single most-recently-updated row where `percent < 100` for that user, or `None` if none exists. `get_progress_map(db: Session, user_id: int, content_type: str, content_ids: List[int]) -> Dict[int, int]` — bulk lookup, keyed by `content_id`, value is `percent`; content items with no `ReadingProgress` row are simply absent from the returned dict (callers should treat a missing key as 0%). Task 3 imports `save_progress`. Task 6 imports `get_current_read`. Task 7 imports `get_progress_map`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_reading_progress_service.py`:

```python
"""
Tests for reading-progress persistence: scroll-based reading progress,
shared across all four Library content types via one table. See
docs/superpowers/specs/2026-08-29-tier-1c-today-chrome-design.md.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from web.models import Base, ReadingProgress
from web.services.reading_progress_service import (
    get_current_read,
    get_progress_map,
    save_progress,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


def test_save_progress_creates_a_row_on_first_save(db):
    save_progress(db, user_id=1, content_type="study", content_id=10, percent=25)

    row = db.query(ReadingProgress).filter(
        ReadingProgress.user_id == 1,
        ReadingProgress.content_type == "study",
        ReadingProgress.content_id == 10,
    ).first()
    assert row is not None
    assert row.percent == 25


def test_save_progress_increases_percent_on_higher_value(db):
    save_progress(db, user_id=1, content_type="study", content_id=10, percent=25)
    save_progress(db, user_id=1, content_type="study", content_id=10, percent=60)

    row = db.query(ReadingProgress).filter(ReadingProgress.content_id == 10).first()
    assert row.percent == 60


def test_save_progress_does_not_decrease_percent_on_lower_value(db):
    save_progress(db, user_id=1, content_type="study", content_id=10, percent=60)
    save_progress(db, user_id=1, content_type="study", content_id=10, percent=25)

    row = db.query(ReadingProgress).filter(ReadingProgress.content_id == 10).first()
    assert row.percent == 60


def test_save_progress_is_scoped_per_user_and_content_type(db):
    save_progress(db, user_id=1, content_type="study", content_id=10, percent=50)
    save_progress(db, user_id=2, content_type="study", content_id=10, percent=15)
    save_progress(db, user_id=1, content_type="workshop", content_id=10, percent=80)

    rows = db.query(ReadingProgress).filter(ReadingProgress.content_id == 10).all()
    by_key = {(r.user_id, r.content_type): r.percent for r in rows}
    assert by_key == {(1, "study"): 50, (2, "study"): 15, (1, "workshop"): 80}


def test_get_current_read_returns_none_when_no_progress_exists(db):
    assert get_current_read(db, user_id=1) is None


def test_get_current_read_returns_most_recently_updated_incomplete_item(db):
    save_progress(db, user_id=1, content_type="study", content_id=1, percent=40)
    save_progress(db, user_id=1, content_type="workshop", content_id=2, percent=70)

    result = get_current_read(db, user_id=1)

    assert result == {"content_type": "workshop", "content_id": 2, "percent": 70}


def test_get_current_read_ignores_completed_items(db):
    save_progress(db, user_id=1, content_type="study", content_id=1, percent=100)

    assert get_current_read(db, user_id=1) is None


def test_get_current_read_ignores_other_users(db):
    save_progress(db, user_id=2, content_type="study", content_id=1, percent=50)

    assert get_current_read(db, user_id=1) is None


def test_get_progress_map_returns_percent_by_content_id(db):
    save_progress(db, user_id=1, content_type="study", content_id=1, percent=30)
    save_progress(db, user_id=1, content_type="study", content_id=2, percent=90)

    result = get_progress_map(db, user_id=1, content_type="study", content_ids=[1, 2, 3])

    assert result == {1: 30, 2: 90}


def test_get_progress_map_is_scoped_to_the_given_content_type(db):
    save_progress(db, user_id=1, content_type="workshop", content_id=1, percent=55)

    result = get_progress_map(db, user_id=1, content_type="study", content_ids=[1])

    assert result == {}
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
python3 -m pytest tests/test_reading_progress_service.py -v
```

Expected: FAIL — `web.services.reading_progress_service` does not exist yet.

- [ ] **Step 3: Add the model**

In `web/models.py`, add this class at the end of the file:

```python
class ReadingProgress(Base):
    """
    Scroll-based reading progress, shared across all four Library content
    types via one table (content_type/content_id, matching Tier 4's
    ContentTheme pattern) rather than a column bolted onto each of the
    four unrelated content models. Percent only ever increases for a
    given (user, content_type, content_id) - see
    reading_progress_service.save_progress().
    """

    __tablename__ = "reading_progress"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    content_type = Column(String(20), nullable=False)  # 'study'/'workshop'/'currents'/'resonance'
    content_id = Column(Integer, nullable=False)
    percent = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('idx_reading_progress_user', 'user_id'),
        UniqueConstraint('user_id', 'content_type', 'content_id', name='uq_reading_progress_item'),
    )

    def __repr__(self):
        return f"<ReadingProgress(user_id={self.user_id}, content_type='{self.content_type}', content_id={self.content_id}, percent={self.percent})>"
```

`Column`, `Integer`, `String`, `DateTime`, `Index`, `UniqueConstraint`, `datetime`, and `Base` are all already imported/defined earlier in `web/models.py` (used by `LectionaryReadingCache`/`ContentTheme`) — no new imports needed.

- [ ] **Step 4: Create the service**

Create `web/services/reading_progress_service.py`:

```python
"""
Reading-progress persistence: scroll-based reading progress, shared
across all four Library content types (study/workshop/currents/
resonance) via one table. See
docs/superpowers/specs/2026-08-29-tier-1c-today-chrome-design.md.
"""

from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from web.models import ReadingProgress


def save_progress(db: Session, user_id: int, content_type: str, content_id: int, percent: int) -> None:
    """
    Upserts a ReadingProgress row. Percent only ever increases - a lower
    value than what's already stored is silently ignored, not an error
    (the caller is a debounced client-side scroll tracker that can post
    out of order, e.g. after scrolling back up).
    """
    row = (
        db.query(ReadingProgress)
        .filter(
            ReadingProgress.user_id == user_id,
            ReadingProgress.content_type == content_type,
            ReadingProgress.content_id == content_id,
        )
        .first()
    )

    if row is None:
        db.add(ReadingProgress(
            user_id=user_id,
            content_type=content_type,
            content_id=content_id,
            percent=percent,
        ))
        db.commit()
        return

    if percent > row.percent:
        row.percent = percent
        db.commit()


def get_current_read(db: Session, user_id: int) -> Optional[dict]:
    """
    Returns {"content_type": str, "content_id": int, "percent": int} for
    the single most-recently-updated ReadingProgress row where percent <
    100 for this user, across all content types - or None if the user
    has no in-progress item.
    """
    row = (
        db.query(ReadingProgress)
        .filter(
            ReadingProgress.user_id == user_id,
            ReadingProgress.percent < 100,
        )
        .order_by(ReadingProgress.updated_at.desc())
        .first()
    )
    if row is None:
        return None
    return {
        "content_type": row.content_type,
        "content_id": row.content_id,
        "percent": row.percent,
    }


def get_progress_map(db: Session, user_id: int, content_type: str, content_ids: List[int]) -> Dict[int, int]:
    """
    Bulk lookup for a list of content_ids of one content_type. Returns a
    dict keyed by content_id -> percent; content items with no
    ReadingProgress row are simply absent - callers should treat a
    missing key as 0%.
    """
    if not content_ids:
        return {}

    rows = (
        db.query(ReadingProgress)
        .filter(
            ReadingProgress.user_id == user_id,
            ReadingProgress.content_type == content_type,
            ReadingProgress.content_id.in_(content_ids),
        )
        .all()
    )
    return {row.content_id: row.percent for row in rows}
```

- [ ] **Step 5: Run the tests to confirm they pass**

```bash
python3 -m pytest tests/test_reading_progress_service.py -v
```

Expected: all 10 PASS.

- [ ] **Step 6: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS, 0 failures.

- [ ] **Step 7: Commit**

```bash
git add web/models.py web/services/reading_progress_service.py tests/test_reading_progress_service.py
git commit -m "Add ReadingProgress model and service

One table spanning all four Library content types (study/workshop/
currents/resonance), matching Tier 4's ContentTheme precedent.
save_progress() only ever increases percent for a given
(user, content_type, content_id); get_current_read() and
get_progress_map() power the two display surfaces added in later
tasks.

See docs/superpowers/specs/2026-08-29-tier-1c-today-chrome-design.md."
```

---

### Task 3: `POST /api/progress` endpoint

**Files:**
- Modify: `web/app.py` (new route)
- Test: `tests/test_route_smoke.py`

**Interfaces:**
- Consumes: `save_progress(db, user_id, content_type, content_id, percent)` from Task 2. `request.state.user` from Task 1.
- Produces: `POST /api/progress` accepting JSON body `{"content_type": str, "content_id": int, "percent": int}`, returns `204 No Content` on success. Task 4's client JS posts to this endpoint.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_route_smoke.py` (this file already has `study_client`-style fixtures seeding a session-backed in-memory DB and an authenticated `TestClient` — reuse that pattern; if a fixture named `study_client` already exists in this file from earlier work, reuse it directly rather than writing a new one):

```python
from web.models import ReadingProgress
from web.services.reading_progress_service import save_progress


def test_post_progress_creates_a_row(study_client):
    client, SessionLocal = study_client

    response = client.post("/api/progress", json={
        "content_type": "study",
        "content_id": 42,
        "percent": 35,
    })

    assert response.status_code == 204

    session = SessionLocal()
    row = session.query(ReadingProgress).filter(ReadingProgress.content_id == 42).first()
    assert row is not None
    assert row.percent == 35
    session.close()


def test_post_progress_does_not_decrease_existing_percent(study_client):
    client, SessionLocal = study_client

    session = SessionLocal()
    save_progress(session, user_id=1, content_type="study", content_id=42, percent=80)
    session.close()

    response = client.post("/api/progress", json={
        "content_type": "study",
        "content_id": 42,
        "percent": 20,
    })

    assert response.status_code == 204

    session = SessionLocal()
    row = session.query(ReadingProgress).filter(ReadingProgress.content_id == 42).first()
    assert row.percent == 80
    session.close()


def test_post_progress_requires_authentication():
    response = TestClient(app).post("/api/progress", json={
        "content_type": "study",
        "content_id": 1,
        "percent": 10,
    })
    assert response.status_code in (303, 401)
```

Note: `test_post_progress_requires_authentication` uses a plain unauthenticated `TestClient(app)` (no session cookie) rather than the `study_client`/`client` fixtures, which both set an auth cookie — matching how `test_login_page_renders_without_auth` and `test_health_endpoint` already do this elsewhere in this file. `AuthMiddleware` redirects unauthenticated non-public requests to `/login` with a `303`, which `TestClient` follows by default unless told not to (per this file's own established note about `follow_redirects=False` for POST redirect assertions from Tier 4's work) — accepting either `303` or `401` in the assertion avoids coupling this test to that redirect-following detail, since the only thing this test actually needs to prove is "an unauthenticated request cannot reach the real 204 success path."

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
python3 -m pytest tests/test_route_smoke.py -v -k "post_progress"
```

Expected: all 3 FAIL — the route doesn't exist yet (404).

- [ ] **Step 3: Add the route**

In `web/app.py`, add this import near the other `.services` imports:

```python
from .services.reading_progress_service import save_progress
```

Add this route (a sensible location is right after the `/` home route, since it's closely related to what that page displays):

```python
@app.post("/api/progress", status_code=204)
async def save_reading_progress(request: Request, db: Session = Depends(get_db)):
    """
    Saves scroll-based reading progress for the current user. Called by
    web/static/js/reading-progress.js on content-detail pages.
    """
    body = await request.json()
    save_progress(
        db,
        user_id=request.state.user.id,
        content_type=body["content_type"],
        content_id=body["content_id"],
        percent=body["percent"],
    )
    return Response(status_code=204)
```

`request.state.user` is guaranteed to be set here — `AuthMiddleware` (Task 1) already redirects any unauthenticated request to `/login` before this handler ever runs, since `/api/progress` is not in `PUBLIC_PATHS` and doesn't start with `/static/` or `/admin/`. `Response` is already imported in `web/app.py` (`from fastapi.responses import HTMLResponse, RedirectResponse, Response`).

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
python3 -m pytest tests/test_route_smoke.py -v -k "post_progress"
```

Expected: all 3 PASS.

- [ ] **Step 5: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS, 0 failures.

- [ ] **Step 6: Commit**

```bash
git add web/app.py tests/test_route_smoke.py
git commit -m "Add POST /api/progress endpoint

Saves scroll-based reading progress via Task 2's save_progress(),
using request.state.user from Task 1's middleware extension. Returns
204 on success; the monotonic-increase guarantee lives entirely in
save_progress(), not duplicated here.

See docs/superpowers/specs/2026-08-29-tier-1c-today-chrome-design.md."
```

---

### Task 4: Client-side scroll tracking

**Files:**
- Create: `web/static/js/reading-progress.js`
- Modify: `web/templates/study.html`, `web/templates/workshop_result.html`, `web/templates/currents_result.html`, `web/templates/resonance_result.html`

**Interfaces:**
- Consumes: `POST /api/progress` from Task 3.
- Produces: nothing consumed by later tasks — Task 6 and Task 7 read persisted `ReadingProgress` data via Task 2's service functions directly, not through this JS file.

- [ ] **Step 1: Create the JS file**

Create `web/static/js/reading-progress.js`:

```javascript
/**
 * Scroll-based reading progress: tracks how far the reader has scrolled
 * through a content-detail page and saves it (debounced) to
 * POST /api/progress. See
 * docs/superpowers/specs/2026-08-29-tier-1c-today-chrome-design.md.
 *
 * No-ops entirely if the page has no [data-content-type]/[data-content-id]
 * container - safe to include unconditionally.
 */
(function () {
    var container = document.querySelector('[data-content-type][data-content-id]');
    if (!container) {
        return;
    }

    var contentType = container.dataset.contentType;
    var contentId = parseInt(container.dataset.contentId, 10);
    var debounceTimer = null;
    var highestSent = 0;

    function currentPercent() {
        var scrollable = document.documentElement.scrollHeight - window.innerHeight;
        if (scrollable <= 0) {
            return 100;
        }
        var percent = Math.round((window.scrollY / scrollable) * 100);
        return Math.max(0, Math.min(100, percent));
    }

    function sendProgress(percent, useBeacon) {
        if (percent <= highestSent) {
            return;
        }
        highestSent = percent;

        var payload = JSON.stringify({
            content_type: contentType,
            content_id: contentId,
            percent: percent
        });

        if (useBeacon && navigator.sendBeacon) {
            var blob = new Blob([payload], { type: 'application/json' });
            navigator.sendBeacon('/api/progress', blob);
            return;
        }

        fetch('/api/progress', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: payload
        });
    }

    function onScroll() {
        var percent = currentPercent();
        if (debounceTimer) {
            clearTimeout(debounceTimer);
        }
        debounceTimer = setTimeout(function () {
            sendProgress(percent, false);
        }, 2000);
    }

    window.addEventListener('scroll', onScroll, { passive: true });

    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'hidden') {
            sendProgress(currentPercent(), true);
        }
    });
})();
```

- [ ] **Step 2: Wire the data attributes and script tag into the four templates**

In `web/templates/study.html`, find:

```html
<div class="container study-container{% if palimpsest_rail %} study-container--with-rail{% endif %}" data-share-title="{{ study.reference }} — {{ study.engine | title }}">
```

Replace with:

```html
<div class="container study-container{% if palimpsest_rail %} study-container--with-rail{% endif %}" data-share-title="{{ study.reference }} — {{ study.engine | title }}" data-content-type="study" data-content-id="{{ study.id }}">
```

Then find this file's `extra_scripts` block and add the new script (after the existing scripts, so it loads last):

```html
{% block extra_scripts %}
<script src="/static/js/content-actions.js" defer></script>
{% if palimpsest_rail %}
<script src="/static/js/palimpsest-rail.js" defer></script>
{% endif %}
<script src="/static/js/reading-progress.js" defer></script>
{% endblock %}
```

In `web/templates/workshop_result.html`, find:

```html
<div class="container workshop-result-container" data-share-title="{{ prep.reference }} — {{ prep.lens_name }}">
```

Replace with:

```html
<div class="container workshop-result-container" data-share-title="{{ prep.reference }} — {{ prep.lens_name }}" data-content-type="workshop" data-content-id="{{ prep.id }}">
```

Find this file's `extra_scripts` block:

```html
{% block extra_scripts %}
<script src="/static/js/content-actions.js" defer></script>
<script>
function expandAll() {
```

Add the new script tag right after the `content-actions.js` line, before the existing inline `<script>` block:

```html
{% block extra_scripts %}
<script src="/static/js/content-actions.js" defer></script>
<script src="/static/js/reading-progress.js" defer></script>
<script>
function expandAll() {
```

In `web/templates/currents_result.html`, find:

```html
<div class="container currents-result-container" data-share-title="{{ analysis.headline_summary or 'Theological News Analysis' }}">
```

Replace with:

```html
<div class="container currents-result-container" data-share-title="{{ analysis.headline_summary or 'Theological News Analysis' }}" data-content-type="currents" data-content-id="{{ analysis.id }}">
```

Find this file's `extra_scripts` block:

```html
{% block extra_scripts %}
<script src="/static/js/content-actions.js" defer></script>
{% endblock %}
```

Replace with:

```html
{% block extra_scripts %}
<script src="/static/js/content-actions.js" defer></script>
<script src="/static/js/reading-progress.js" defer></script>
{% endblock %}
```

In `web/templates/resonance_result.html`, find:

```html
<div class="container resonance-result-container" data-share-title="{{ resonance.reference or 'Cultural Connections' }}">
```

Replace with:

```html
<div class="container resonance-result-container" data-share-title="{{ resonance.reference or 'Cultural Connections' }}" data-content-type="resonance" data-content-id="{{ resonance.id }}">
```

Find this file's `extra_scripts` block:

```html
{% block extra_scripts %}
<script src="/static/js/content-actions.js" defer></script>
{% endblock %}
```

Replace with:

```html
{% block extra_scripts %}
<script src="/static/js/content-actions.js" defer></script>
<script src="/static/js/reading-progress.js" defer></script>
{% endblock %}
```

- [ ] **Step 3: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS, 0 failures. This task adds no new automated tests — scroll-position tracking and `sendBeacon` behavior aren't meaningfully testable via the FastAPI `TestClient` (no real browser layout/scroll), matching the precedent already set for `palimpsest-rail.js` in Tier 3.

- [ ] **Step 4: Verify by eye**

Start the dev server, sign in, open a study, scroll down partway, wait ~2-3 seconds, then check (via a database query or the sidebar widget once Task 6 ships) that a `ReadingProgress` row was created with a reasonable percent. Confirm no JS console errors on a page that has no `[data-content-type]` container (e.g. `/browse`) — the guard at the top of the file should make it silently no-op there.

- [ ] **Step 5: Commit**

```bash
git add web/static/js/reading-progress.js web/templates/study.html web/templates/workshop_result.html web/templates/currents_result.html web/templates/resonance_result.html
git commit -m "Add client-side scroll-based reading-progress tracking

Debounced scroll listener posts to Task 3's endpoint; a
visibilitychange/sendBeacon fallback saves the last position on
page-leave so a save isn't lost mid-debounce. Wired into all four
content-detail templates via a shared data-content-type/
data-content-id container attribute. No-ops safely on any page
without that container.

See docs/superpowers/specs/2026-08-29-tier-1c-today-chrome-design.md."
```

---

### Task 5: Header chrome

**Files:**
- Modify: `web/templates/base.html`
- Create: `web/static/js/header-search.js`
- Modify: `web/static/css/styles.css`
- Test: `tests/test_route_smoke.py`

**Interfaces:**
- Consumes: `request.state.user` from Task 1.
- Produces: nothing consumed by later tasks — Task 6 and Task 7 both add to `base.html`/`index.html` independently of this task's header work (different regions of the same files).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_route_smoke.py`:

```python
def test_header_shows_greeting_and_search(client):
    response = client.get("/engines")
    body = response.text

    assert "Welcome back," in body
    assert 'action="/browse"' in body
    assert 'name="q"' in body


def test_header_has_no_notification_markup(client):
    response = client.get("/engines")
    body = response.text.lower()

    assert "notification" not in body
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
python3 -m pytest tests/test_route_smoke.py -v -k "header_shows or header_has_no_notification"
```

Expected: `test_header_shows_greeting_and_search` FAILs (no header exists yet). `test_header_has_no_notification_markup` currently PASSes trivially (there's no notification markup anywhere yet, header or otherwise) — it exists as a regression guard for this task's explicit "no notifications" constraint, the same pattern used in Task 1's tests.

- [ ] **Step 3: Add the header to `base.html`**

In `web/templates/base.html`, find:

```html
        <main class="main-content">
            {% block content %}{% endblock %}
        </main>
```

Replace with:

```html
        <main class="main-content">
            <header class="topbar">
                <div class="topbar-date">
                    <span class="topbar-date-text">{{ today_display }}</span>
                    {% if request.state.user %}
                    <h1 class="topbar-greeting">Welcome back, {{ request.state.user.name.split(' ')[0] }}.</h1>
                    {% endif %}
                </div>

                <form action="/browse" method="get" class="topbar-search">
                    <input type="text" name="q" placeholder="Search passages, studies, themes, authors...">
                    <kbd class="topbar-search-hint">⌘K</kbd>
                </form>

                {% if request.state.user %}
                <div class="topbar-avatar-wrap">
                    <button type="button" class="topbar-avatar" style="background: {{ avatar_color(request.state.user.name) }};">
                        {{ avatar_initials(request.state.user.name) }}
                    </button>
                    <div class="topbar-avatar-menu">
                        <a href="/profiles">Profiles</a>
                        <form action="/logout" method="POST">
                            <button type="submit">Sign out</button>
                        </form>
                    </div>
                </div>
                {% endif %}
            </header>

            {% block content %}{% endblock %}
        </main>
```

`today_display`, `avatar_color`, and `avatar_initials` need to be available in every template's context without every route passing them individually — add them as Jinja globals, set once where `templates` is constructed in `web/app.py`. Find:

```python
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))
```

Replace with:

```python
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))


def _avatar_initials(name: str) -> str:
    parts = name.split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return name[:2].upper() if name else "?"


def _avatar_color(name: str) -> str:
    # Deterministic hue from the name so the same person always gets the
    # same color and different people get visually distinct ones.
    hue = sum(ord(c) for c in name) % 360
    return f"hsl({hue}, 45%, 45%)"


templates.env.globals["avatar_initials"] = _avatar_initials
templates.env.globals["avatar_color"] = _avatar_color
```

`today_display` is simpler as a per-request value rather than a Jinja global (it needs `datetime.now()`, not a pure function of an argument already in scope) — instead of adding it to every route's context, expose it the same way `request.state.user` is exposed: attach it inside the same `with _middleware_db() as db:` block Task 1 opened (it needs no `db` access itself, but stays in this block so all of `AuthMiddleware`'s `request.state` attachments live in one place, and so Task 6 can keep extending the same block after this). In `web/app.py`, find the line added in Task 1:

```python
        with _middleware_db() as db:
            request.state.user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
```

Replace with:

```python
        with _middleware_db() as db:
            request.state.user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
            request.state.today_display = datetime.now().strftime('%A, %B %d, %Y')
```

This needs `from datetime import datetime` at the top of `web/app.py` — check whether it's already imported (`web/app.py` may already import `datetime` for other purposes; if not, add the import near the other stdlib imports).

Then in `base.html`, change `{{ today_display }}` to `{{ request.state.today_display }}`.

- [ ] **Step 4: Add `header-search.js`**

Create `web/static/js/header-search.js`:

```javascript
/**
 * Focuses the header search input on Cmd+K / Ctrl+K. The search form
 * itself is plain HTML (works via normal submission with JS entirely
 * absent) - this is a pure keyboard-shortcut enhancement.
 */
(function () {
    var input = document.querySelector('.topbar-search input[name="q"]');
    if (!input) {
        return;
    }

    document.addEventListener('keydown', function (event) {
        var isShortcut = (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k';
        if (isShortcut) {
            event.preventDefault();
            input.focus();
        }
    });
})();
```

Add it to `base.html`, right before the closing `</body>` tag (so it loads on every page, unlike the per-content-type `extra_scripts` block):

Find:

```html
    {% block extra_scripts %}{% endblock %}
</body>
```

Replace with:

```html
    <script src="/static/js/header-search.js" defer></script>
    {% block extra_scripts %}{% endblock %}
</body>
```

- [ ] **Step 5: Add CSS**

In `web/static/css/styles.css`, find:

```css
.main-content {
    width: 100%;
    max-width: var(--content-max);
    margin: 0 auto;
    padding: 28px 36px 64px;
}
```

Add immediately after it (before the `/* Sidebar */` comment block that follows). Note: `.topbar` deliberately has no horizontal padding of its own — `.main-content` already insets its children by 36px on each side, and `.topbar` is a direct child of `.main-content` (same as every other section on the page), so it should align flush with them rather than adding a second layer of side padding:

```css
/* ============================================================================
   Topbar (header chrome)
   ============================================================================ */

.topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-lg);
    padding-bottom: var(--space-md);
    margin-bottom: var(--space-lg);
    border-bottom: 1px solid var(--border-light);
}

.topbar-date-text {
    display: block;
    font-family: var(--font-ui);
    font-size: 0.8rem;
    color: var(--ink-600);
    margin-bottom: 2px;
}

.topbar-greeting {
    font-family: var(--font-heading);
    font-size: 1.5rem;
    color: var(--ink-950);
    margin: 0;
}

.topbar-search {
    flex: 0 1 min(420px, 40vw);
    position: relative;
    display: flex;
    align-items: center;
}

.topbar-search input[type="text"] {
    width: 100%;
    height: 42px;
    padding: 0 44px 0 14px;
    border: 1px solid var(--border-light);
    border-radius: var(--radius-md);
    background: var(--surface-white);
    color: var(--ink-950);
    font-family: var(--font-ui);
    font-size: 0.9rem;
}

.topbar-search input[type="text"]:focus {
    outline: none;
    border-color: var(--blue-400);
    box-shadow: 0 0 0 3px rgba(25, 118, 210, 0.10);
}

.topbar-search-hint {
    position: absolute;
    right: 12px;
    font-family: var(--font-ui);
    font-size: 0.75rem;
    color: var(--ink-400);
    background: var(--surface-muted);
    padding: 2px 6px;
    border-radius: var(--radius-sm);
    pointer-events: none;
}

.topbar-avatar-wrap {
    position: relative;
}

.topbar-avatar {
    width: 38px;
    height: 38px;
    border-radius: 50%;
    border: none;
    color: #fff;
    font-family: var(--font-ui);
    font-weight: 600;
    font-size: 0.85rem;
    cursor: pointer;
}

.topbar-avatar-menu {
    display: none;
    position: absolute;
    right: 0;
    top: 46px;
    background: var(--surface-white);
    border: 1px solid var(--border-light);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-md);
    padding: var(--space-xs);
    min-width: 140px;
    z-index: 20;
}

.topbar-avatar-wrap:hover .topbar-avatar-menu,
.topbar-avatar-wrap:focus-within .topbar-avatar-menu {
    display: flex;
    flex-direction: column;
}

.topbar-avatar-menu a,
.topbar-avatar-menu button {
    display: block;
    width: 100%;
    text-align: left;
    padding: var(--space-xs) var(--space-sm);
    border: none;
    background: none;
    color: var(--ink-800);
    font-family: var(--font-ui);
    font-size: 0.85rem;
    text-decoration: none;
    border-radius: var(--radius-sm);
    cursor: pointer;
}

.topbar-avatar-menu a:hover,
.topbar-avatar-menu button:hover {
    background: var(--surface-muted);
}
```

Every token used here (`--space-*`, `--border-light`, `--font-ui`, `--font-heading`, `--ink-*`, `--surface-white`, `--surface-muted`, `--radius-*`, `--blue-400`, `--shadow-md`) already exists in `:root` per Tier 1a's token set — do not invent new tokens.

- [ ] **Step 6: Run the tests to confirm they pass**

```bash
python3 -m pytest tests/test_route_smoke.py -v -k "header_shows or header_has_no_notification"
```

Expected: both PASS.

- [ ] **Step 7: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS, 0 failures.

- [ ] **Step 8: Verify by eye**

Start the dev server, sign in, confirm the header appears on every page (not just Today): date, "Welcome back, {name}," search bar, avatar with correct initials. Type in the search bar and submit — confirm it lands on `/browse?q=...` with results. Press Cmd+K (or Ctrl+K) from anywhere on the page and confirm the search input focuses. Hover the avatar and confirm the dropdown shows Profiles/Sign out and both work. Confirm no notification bell appears anywhere.

- [ ] **Step 9: Commit**

```bash
git add web/templates/base.html web/static/js/header-search.js web/static/css/styles.css web/app.py
git commit -m "Add header chrome: date, greeting, search, avatar

Renders once in base.html so it appears on every page. Search reuses
the existing /browse search (no new backend). Avatar is initials-only
(no User photo field) with a deterministic per-name color. Cmd+K
focuses the search input. No notification bell - explicitly out of
scope per the design spec.

See docs/superpowers/specs/2026-08-29-tier-1c-today-chrome-design.md."
```

---

### Task 6: Sidebar visual regrouping and progress widget

**Files:**
- Modify: `web/templates/base.html`
- Modify: `web/app.py` (attach current-read data to every request, or query directly in `base.html`'s rendering path — see Step 2)
- Modify: `web/static/css/styles.css`
- Test: `tests/test_route_smoke.py`

**Interfaces:**
- Consumes: `get_current_read(db, user_id)` from Task 2. `request.state.user` from Task 1.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_route_smoke.py`:

```python
def test_secondary_sidebar_links_are_marked(client):
    response = client.get("/engines")
    body = response.text

    assert 'href="/workshop" class="sidebar-link sidebar-link--secondary' in body
    assert 'href="/currents" class="sidebar-link sidebar-link--secondary' in body
    assert 'href="/resonance" class="sidebar-link sidebar-link--secondary' in body


def test_sidebar_progress_widget_shows_current_read(study_client):
    client, SessionLocal = study_client
    session = SessionLocal()
    study = Study(engine="palimpsest", reference="John 3:16-21", content="content", word_count=10)
    session.add(study)
    session.commit()
    study_id = study.id
    session.close()

    session = SessionLocal()
    save_progress(session, user_id=1, content_type="study", content_id=study_id, percent=40)
    session.close()

    response = client.get("/engines")
    body = response.text

    assert "John 3:16-21" in body
    assert "40%" in body or "40 %" in body


def test_sidebar_progress_widget_absent_when_no_progress(client):
    response = client.get("/engines")
    assert "sidebar-progress-widget" not in response.text
```

`Study` and `save_progress` need importing at the top of `tests/test_route_smoke.py` if not already present (`from web.models import ..., Study, ReadingProgress` and `from web.services.reading_progress_service import save_progress` — check the file's existing imports first and only add what's missing).

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
python3 -m pytest tests/test_route_smoke.py -v -k "secondary_sidebar or progress_widget"
```

Expected: all 3 FAIL.

- [ ] **Step 3: Mark the secondary sidebar links**

In `web/templates/base.html`, find:

```html
                <a href="/workshop" class="sidebar-link {% if request.url.path.startswith('/workshop') %}active{% endif %}">Workshop</a>
                <a href="/currents" class="sidebar-link {% if request.url.path.startswith('/currents') %}active{% endif %}">Currents</a>
                <a href="/resonance" class="sidebar-link {% if request.url.path.startswith('/resonance') %}active{% endif %}">Resonance</a>
```

Replace with:

```html
                <a href="/workshop" class="sidebar-link sidebar-link--secondary {% if request.url.path.startswith('/workshop') %}active{% endif %}">Workshop</a>
                <a href="/currents" class="sidebar-link sidebar-link--secondary {% if request.url.path.startswith('/currents') %}active{% endif %}">Currents</a>
                <a href="/resonance" class="sidebar-link sidebar-link--secondary {% if request.url.path.startswith('/resonance') %}active{% endif %}">Resonance</a>
```

- [ ] **Step 4: Add the sidebar progress widget**

In `web/templates/base.html`, find:

```html
            <form action="/logout" method="POST" class="sidebar-signout">
                <button type="submit" class="sidebar-link sidebar-link--button">Sign out</button>
            </form>
        </aside>
```

Replace with:

```html
            {% if current_read %}
            <div class="sidebar-progress-widget">
                <span class="sidebar-progress-badge">{{ current_read.content_type | title }}</span>
                <p class="sidebar-progress-title">{{ current_read.title }}</p>
                <div class="sidebar-progress-bar">
                    <div class="sidebar-progress-fill" style="width: {{ current_read.percent }}%;"></div>
                </div>
                <a href="{{ current_read.url }}" class="sidebar-progress-link">{{ current_read.percent }}% complete →</a>
            </div>
            {% endif %}

            <form action="/logout" method="POST" class="sidebar-signout">
                <button type="submit" class="sidebar-link sidebar-link--button">Sign out</button>
            </form>
        </aside>
```

This needs `current_read` (a dict with `content_type`, `title`, `percent`, `url` — note this is a richer shape than Task 2's `get_current_read()`, which only returns `content_type`/`content_id`/`percent`; this task adds the title/url lookup on top) present in every route's template context, the same "needs to be everywhere without touching every route" problem the header solved via `request.state`. Attach it the same way, reusing the same `db` session already open in the `with` block: in `web/app.py`'s `AuthMiddleware.dispatch()`, find the block from Task 1/5:

```python
        with _middleware_db() as db:
            request.state.user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
            request.state.today_display = datetime.now().strftime('%A, %B %d, %Y')
```

Replace with:

```python
        with _middleware_db() as db:
            request.state.user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
            request.state.today_display = datetime.now().strftime('%A, %B %d, %Y')

            current_read_data = get_current_read(db, user_id)
            if current_read_data:
                title = _title_for_content(db, current_read_data["content_type"], current_read_data["content_id"])
                request.state.current_read = {
                    "content_type": current_read_data["content_type"],
                    "title": title,
                    "percent": current_read_data["percent"],
                    "url": f"{DETAIL_URL_PREFIXES[current_read_data['content_type']]}{current_read_data['content_id']}",
                } if title else None
            else:
                request.state.current_read = None
```

This needs two new imports near the top of `web/app.py`, alongside the other `.services` imports:

```python
from .services.reading_progress_service import get_current_read
from .services.library_service import DETAIL_URL_PREFIXES
```

And calls a new small helper, `_title_for_content`, added just above the `AuthMiddleware` class in `web/app.py`:

```python
def _title_for_content(db: Session, content_type: str, content_id: int) -> Optional[str]:
    """
    Looks up a display title for a (content_type, content_id) pair - used
    by the sidebar's current-read widget. Returns None if the row no
    longer exists (e.g. deleted after progress was recorded), so the
    widget can skip rendering rather than showing a broken link.
    """
    if content_type == "study":
        row = db.query(Study).filter(Study.id == content_id).first()
        return row.reference if row else None
    if content_type == "workshop":
        from .models import WorkshopPrep
        row = db.query(WorkshopPrep).filter(WorkshopPrep.id == content_id).first()
        return row.reference if row else None
    if content_type == "currents":
        from .models import CurrentsAnalysis
        row = db.query(CurrentsAnalysis).filter(CurrentsAnalysis.id == content_id).first()
        return (row.headline_summary or "Theological News Analysis") if row else None
    if content_type == "resonance":
        from .models import CulturalResonance
        row = db.query(CulturalResonance).filter(CulturalResonance.id == content_id).first()
        return row.reference if row else None
    return None
```

`Optional` needs importing (`from typing import Optional`) if not already present in `web/app.py`.

Then in `base.html`, change `{% if current_read %}` to `{% if request.state.current_read %}` and every `current_read.X` reference in that block to `request.state.current_read.X`.

- [ ] **Step 5: Add CSS**

In `web/static/css/styles.css`, add near the existing `.sidebar-signout` rule:

```css
.sidebar-link--secondary {
    font-size: 0.82rem;
    color: rgba(255, 255, 255, 0.55);
}

.sidebar-link--secondary:hover {
    color: rgba(255, 255, 255, 0.8);
}

.sidebar-progress-widget {
    margin: var(--space-md) 12px;
    padding: var(--space-sm);
    background: rgba(255, 255, 255, 0.06);
    border-radius: var(--radius-md);
}

.sidebar-progress-badge {
    display: inline-block;
    font-family: var(--font-ui);
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--blue-400);
    margin-bottom: 4px;
}

.sidebar-progress-title {
    font-family: var(--font-heading);
    font-size: 0.85rem;
    color: #fff;
    margin: 0 0 8px 0;
}

.sidebar-progress-bar {
    height: 4px;
    border-radius: 2px;
    background: rgba(255, 255, 255, 0.15);
    overflow: hidden;
    margin-bottom: 6px;
}

.sidebar-progress-fill {
    height: 100%;
    background: var(--orange-400);
    border-radius: 2px;
}

.sidebar-progress-link {
    font-family: var(--font-ui);
    font-size: 0.78rem;
    color: rgba(255, 255, 255, 0.7);
    text-decoration: none;
}

.sidebar-progress-link:hover {
    color: #fff;
}
```

Every token used (`--space-*`, `--radius-md`, `--font-ui`, `--font-heading`, `--blue-400`, `--orange-400`) already exists.

- [ ] **Step 6: Run the tests to confirm they pass**

```bash
python3 -m pytest tests/test_route_smoke.py -v -k "secondary_sidebar or progress_widget"
```

Expected: all 3 PASS.

- [ ] **Step 7: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS, 0 failures.

- [ ] **Step 8: Commit**

```bash
git add web/templates/base.html web/app.py web/static/css/styles.css tests/test_route_smoke.py
git commit -m "De-emphasize Workshop/Currents/Resonance in the sidebar; add current-read widget

Visual regrouping only - no route changes, no page redesigns (full
consolidation remains explicitly deferred). The sidebar's new
current-read widget shows the user's single most-recently-updated
in-progress item across all four content types, populated via
request.state the same way Task 1/5 already solved the
every-page-needs-this problem.

See docs/superpowers/specs/2026-08-29-tier-1c-today-chrome-design.md."
```

---

### Task 7: "Continue Your Studies" progress bars, quote banner, and illustration

**Files:**
- Modify: `web/app.py` (the `/` route)
- Modify: `web/templates/index.html`
- Modify: `web/static/css/styles.css`
- Create: `web/static/images/today-illustration.png` (copied from the user-supplied asset)
- Test: `tests/test_route_smoke.py`

**Interfaces:**
- Consumes: `get_progress_map(db, user_id, content_type, content_ids)` from Task 2.
- Produces: nothing consumed by later tasks — this is the last task in this plan.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_route_smoke.py`:

```python
@patch("web.services.lectionary_widget_service.TextFetcher")
@patch("web.services.signals_service.TextFetcher")
@patch("web.services.signals_service.extract_themes")
def test_continue_your_studies_shows_progress_bar(
    mock_extract_themes, mock_signals_fetcher_class, mock_readings_fetcher_class, study_client
):
    mock_readings_fetcher_class.return_value.fetch_sunday_lectionary_readings.return_value = {}
    mock_extract_themes.return_value = []

    client, SessionLocal = study_client
    session = SessionLocal()
    study = Study(engine="threshold", reference="Mark 5:1-5", content="content", word_count=10)
    session.add(study)
    session.commit()
    study_id = study.id
    session.close()

    session = SessionLocal()
    save_progress(session, user_id=1, content_type="study", content_id=study_id, percent=66)
    session.close()

    response = client.get("/")
    body = response.text

    assert "66%" in body


@patch("web.services.lectionary_widget_service.TextFetcher")
@patch("web.services.signals_service.TextFetcher")
@patch("web.services.signals_service.extract_themes")
def test_today_page_shows_quote_banner(
    mock_extract_themes, mock_signals_fetcher_class, mock_readings_fetcher_class, isolated_client
):
    mock_readings_fetcher_class.return_value.fetch_sunday_lectionary_readings.return_value = {}
    mock_extract_themes.return_value = []

    response = isolated_client.get("/")
    assert "today-quote" in response.text
```

`isolated_client` is the existing fixture already used elsewhere in this file for hitting `/` (a plain unauthenticated `TestClient(app).get("/")` would just redirect to `/login` — this file's established pattern for testing `/` is always through `isolated_client`, which carries an authenticated session cookie). The three `@patch` decorators match the exact pattern already used by other tests hitting `/` in this same file (e.g. `test_today_homepage_shows_signals_widget`) — mocked bottom-up, so the decorator closest to the function signs up as the first positional mock argument. `Study`, `save_progress`, and `patch` (from `unittest.mock`) need importing at the top of `tests/test_route_smoke.py` if not already present — check the file's existing imports first and only add what's missing.

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
python3 -m pytest tests/test_route_smoke.py -v -k "continue_your_studies_shows_progress or today_page_shows_quote"
```

Expected: both FAIL.

- [ ] **Step 3: Update the `/` route**

In `web/app.py`, find the `home()` route (the one Task 1/5/6 have not otherwise modified — this is `/`, not `/api/progress`):

```python
@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    """
    Today homepage - This Week in the Lectionary, Signals, engine cards,
    quick actions, and recent studies
    """
    from lectionary_engines.claude_client import ClaudeClient
    from .services.lectionary_widget_service import get_this_week_readings
    from .services.signals_service import get_this_week_signals

    # Get recent studies (last 5)
    recent_studies = db.query(Study).order_by(Study.created_at.desc()).limit(5).all()

    this_week = get_this_week_readings(db)

    claude = ClaudeClient(config.anthropic_api_key)
    signals = get_this_week_signals(db, claude)[:3]  # top 3 for the compact widget; full list on /signals

    return templates.TemplateResponse("index.html", {
        "request": request,
        "recent_studies": recent_studies,
        "this_week": this_week,
        "signals": signals,
        "config": config
    })
```

Replace with:

```python
QUOTES = [
    ("We do not read the Bible to have it confirmed; we read it to be changed.", "N.T. Wright"),
    ("Scripture is not a quarry from which we can extract proof texts to bolster our arguments, but a river in which we swim.", "Eugene Peterson"),
    ("The Bible is not a book which yields its treasures to the lazy.", "J.I. Packer"),
    ("A text without a context is a pretext for a proof text.", "D.A. Carson"),
    ("Read the Bible as if it were written yesterday, and you were meant to understand it today.", "Karl Barth"),
    ("The Word of God is not chained.", "2 Timothy 2:9"),
    ("Every text has a context, and every context has a story.", "N.T. Wright"),
]


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    """
    Today homepage - This Week in the Lectionary, Signals, engine cards,
    quick actions, and recent studies
    """
    from datetime import date
    from lectionary_engines.claude_client import ClaudeClient
    from .services.lectionary_widget_service import get_this_week_readings
    from .services.signals_service import get_this_week_signals
    from .services.reading_progress_service import get_progress_map

    # Get recent studies (last 5)
    recent_studies = db.query(Study).order_by(Study.created_at.desc()).limit(5).all()

    this_week = get_this_week_readings(db)

    claude = ClaudeClient(config.anthropic_api_key)
    signals = get_this_week_signals(db, claude)[:3]  # top 3 for the compact widget; full list on /signals

    progress_by_study_id = {}
    if request.state.user:
        progress_by_study_id = get_progress_map(
            db, request.state.user.id, "study", [s.id for s in recent_studies]
        )

    quote_text, quote_author = QUOTES[date.today().timetuple().tm_yday % len(QUOTES)]

    return templates.TemplateResponse("index.html", {
        "request": request,
        "recent_studies": recent_studies,
        "this_week": this_week,
        "signals": signals,
        "config": config,
        "progress_by_study_id": progress_by_study_id,
        "quote_text": quote_text,
        "quote_author": quote_author,
    })
```

- [ ] **Step 4: Update `index.html`**

Find the "Continue Your Studies" section:

```html
    {% if recent_studies %}
    <section class="recent-studies">
        <h2>Continue Your Studies</h2>
        <div class="studies-list">
            {% for study in recent_studies %}
            <div class="study-item">
                <a href="/study/{{ study.id }}" class="study-link">
                    <span class="engine-badge engine-{{ study.engine }}">{{ study.engine }}</span>
                    <span class="study-reference">{{ study.reference }}</span>
                    <span class="study-meta">
                        {{ study.word_count }} words | {{ study.created_at.strftime('%B %d, %Y') }}
                    </span>
                </a>
            </div>
            {% endfor %}
        </div>
        <div class="section-footer">
            <a href="/browse" class="btn btn-link">View all studies →</a>
        </div>
    </section>
    {% endif %}
</div>
{% endblock %}
```

Replace with:

```html
    {% if recent_studies %}
    <section class="recent-studies">
        <h2>Continue Your Studies</h2>
        <div class="studies-list">
            {% for study in recent_studies %}
            <div class="study-item">
                <a href="/study/{{ study.id }}" class="study-link">
                    <span class="engine-badge engine-{{ study.engine }}">{{ study.engine }}</span>
                    <span class="study-reference">{{ study.reference }}</span>
                    <span class="study-meta">
                        {{ study.word_count }} words | {{ study.created_at.strftime('%B %d, %Y') }}
                    </span>
                </a>
                {% if study.id in progress_by_study_id %}
                <div class="study-progress-bar">
                    <div class="study-progress-fill" style="width: {{ progress_by_study_id[study.id] }}%;"></div>
                </div>
                <span class="study-progress-label">{{ progress_by_study_id[study.id] }}% complete</span>
                {% endif %}
            </div>
            {% endfor %}
        </div>
        <div class="section-footer">
            <a href="/browse" class="btn btn-link">View all studies →</a>
        </div>
    </section>
    {% endif %}

    <section class="today-quote" id="today-quote">
        <blockquote>
            <p>"{{ quote_text }}"</p>
            <cite>— {{ quote_author }}</cite>
        </blockquote>
    </section>
</div>
{% endblock %}
```

- [ ] **Step 5: Copy the illustration asset**

```bash
cp "docs/superpowers/specs/assets/today-illustration-2026-08-29.png" web/static/images/today-illustration.png
```

(This is the same file already saved alongside the design spec during brainstorming — `docs/superpowers/specs/assets/today-illustration-2026-08-29.png`, 1920×819px.)

- [ ] **Step 6: Add CSS**

In `web/static/css/styles.css`, add near the existing `.recent-studies`/`.study-item` rules:

```css
.study-progress-bar {
    height: 4px;
    border-radius: 2px;
    background: var(--surface-muted);
    overflow: hidden;
    margin-top: 8px;
    margin-bottom: 4px;
}

.study-progress-fill {
    height: 100%;
    background: var(--orange-400);
    border-radius: 2px;
}

.study-progress-label {
    font-family: var(--font-ui);
    font-size: 0.78rem;
    color: var(--ink-600);
}

/* ============================================================================
   Today quote banner
   ============================================================================ */

.today-quote {
    position: relative;
    margin-top: var(--space-2xl);
    padding: var(--space-xl) var(--space-lg);
    border-radius: var(--radius-lg);
    background-image: url('/static/images/today-illustration.png');
    background-size: cover;
    background-position: center;
    overflow: hidden;
}

.today-quote::before {
    content: "";
    position: absolute;
    inset: 0;
    background: var(--ivory-50);
    opacity: 0.87;
    mix-blend-mode: normal;
}

.today-quote blockquote {
    position: relative;
    z-index: 1;
    margin: 0;
    max-width: 620px;
}

.today-quote p {
    font-family: var(--font-heading);
    font-style: italic;
    font-size: 1.3rem;
    color: var(--ink-950);
    margin: 0 0 var(--space-sm) 0;
}

.today-quote cite {
    font-family: var(--font-ui);
    font-style: normal;
    font-size: 0.9rem;
    color: var(--ink-600);
}
```

Note on the opacity/blend approach: the aesthetic guardrail specifies the *illustration itself* renders at very low opacity via `mix-blend-mode: multiply` against the page background. Since this section has its own background image (not an inline `<img>` composited over the page), the equivalent effect here is a near-opaque ivory overlay (`.today-quote::before`) sitting on top of the full-strength illustration — this keeps the quote text readable while still showing the illustration as a faint, textural background rather than a bold foreground image. Adjust the `0.87` opacity value during Step 8's visual check if the illustration reads too strong or too faint against the actual quote text.

- [ ] **Step 7: Run the tests to confirm they pass**

```bash
python3 -m pytest tests/test_route_smoke.py -v -k "continue_your_studies_shows_progress or today_page_shows_quote"
```

Expected: both PASS.

- [ ] **Step 8: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS, 0 failures.

- [ ] **Step 9: Verify by eye**

Start the dev server, sign in, visit `/`. Confirm: studies with recorded progress show a bar and percentage; the quote banner appears at the bottom with the illustration visible but subtle behind readable text. Reload the page and confirm the same quote appears (deterministic for today's date) — check back the next day (or temporarily adjust the modulo test) to confirm it changes.

- [ ] **Step 10: Commit**

```bash
git add web/app.py web/templates/index.html web/static/css/styles.css web/static/images/today-illustration.png tests/test_route_smoke.py
git commit -m "Add progress bars to Continue Your Studies and a quote banner

Today's homepage now shows real progress (Task 2's get_progress_map())
on recent studies, and a daily-rotating quote over the user-supplied
illustration asset, matching the aesthetic guardrail's engraved/
subtle-texture direction. This completes Tier 1c.

See docs/superpowers/specs/2026-08-29-tier-1c-today-chrome-design.md."
```

---
