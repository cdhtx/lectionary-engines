# Tier 4 — Library Knowledge Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Facet the unified Library by theme, liturgical season, and source across all four content types, and retire the redundant `/currents/browse` page in favor of faceted browsing.

**Architecture:** A new `content_theme` association table (one row per content-item/theme pair) lets theme faceting span the four structurally-unrelated content models with plain indexed SQL joins. `Study`/`WorkshopPrep` gain `reading_date`/`season` columns, populated only for RCL-sourced content going forward (season is precomputed via a new liturgical-calendar utility, not derived at query time, since Lent/Easter/Pentecost are moveable feasts). `library_service.py`'s existing `union_all()` query gains theme/season/source filters and a facet-listing function; all four generation routes persist themes (and season, where applicable) at creation time; a one-time script backfills existing rows.

**Tech Stack:** SQLAlchemy, FastAPI, Jinja2, pytest, `lectionary_engines.theme_extractor.extract_themes()`.

**Spec:** `docs/superpowers/specs/2026-08-28-tier-4-library-knowledge-graph-design.md`

## Global Constraints

- **Tradition is out of scope.** No task in this plan adds a tradition field or facet.
- **Theme facet is free text, not a controlled vocabulary.** Persist `extract_themes()`'s output as-is (lowercased/trimmed); no synonym mapping, no canonical list.
- **Season is RCL-only, forward-only.** `reading_date`/`season` are only ever set when `source == "rcl"` at generation time. No historical backfill of `reading_date` for existing rows — there is no reliable way to recover it.
- **Source facet is scoped to Study/WorkshopPrep only.** `CurrentsAnalysis`/`CulturalResonance` are not folded into it.
- **`content_theme` is a new table, not new columns on the four content models.** `Base.metadata.create_all()` creates it automatically — no `COLUMN_MIGRATIONS` entry for it.
- **`reading_date`/`season` ARE new columns on existing tables (`studies`, `workshop_preps`)** — these DO need `COLUMN_MIGRATIONS` entries in `web/database.py`, since `create_all()` never alters an existing table. (The spec document mentions a `web/migrations/003_...` file for this — that directory is a legacy, unused-at-runtime pattern superseded by `COLUMN_MIGRATIONS`, confirmed by checking `web/database.py` and `web/migrations/*.py` directly; this plan uses the mechanism that's actually live.)
- **All `content_theme` writes go through `record_content_themes()`** (added in Task 2) — no route or script inserts a `ContentTheme` row directly. This is the one place lowercasing/trimming/deduping happens.
- **The existing test suite must stay green.** Run `python3 -m pytest tests/ -v` before starting and note the passing count; don't assume it if it's drifted.

---

### Task 1: Shared liturgical calendar utilities

**Files:**
- Create: `lectionary_engines/liturgical_calendar.py`
- Test: `tests/test_liturgical_calendar.py`
- Modify: `web/services/lectionary_widget_service.py` (remove duplicated `_upcoming_sunday`, use the shared one)
- Modify: `web/services/signals_service.py` (remove duplicated `_upcoming_sunday`, use the shared one)

**Interfaces:**
- Produces: `lectionary_engines.liturgical_calendar.upcoming_sunday(today: date) -> date`; `lectionary_engines.liturgical_calendar.season_for_date(d: date) -> str` (returns one of `"advent"`, `"christmas"`, `"epiphany"`, `"lent"`, `"holy_week"`, `"easter"`, `"pentecost"`, `"ordinary_time"`). Tasks 3 and 4 both consume both functions directly.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_liturgical_calendar.py`:

```python
"""
Tests for the shared liturgical calendar utilities: season_for_date()
(buckets a date into one of eight liturgical seasons, for Study/
WorkshopPrep faceting) and upcoming_sunday() (the single shared
implementation of a calculation previously duplicated privately in
lectionary_widget_service.py and signals_service.py).
"""

from datetime import date, timedelta

from lectionary_engines.liturgical_calendar import (
    _advent_start,
    _easter_sunday,
    season_for_date,
    upcoming_sunday,
)


def test_easter_sunday_matches_known_reference_dates():
    known = {
        2024: date(2024, 3, 31),
        2025: date(2025, 4, 20),
        2026: date(2026, 4, 5),
        2027: date(2027, 3, 28),
        2028: date(2028, 4, 16),
    }
    for year, expected in known.items():
        assert _easter_sunday(year) == expected


def test_advent_start_falls_within_nov_27_to_dec_3_and_is_a_sunday():
    for year in range(2024, 2031):
        d = _advent_start(year)
        assert (d.month, d.day) in [(11, 27), (11, 28), (11, 29), (11, 30), (12, 1), (12, 2), (12, 3)]
        assert d.weekday() == 6  # Sunday


def test_season_boundaries_for_2026():
    assert season_for_date(date(2026, 1, 3)) == "christmas"
    assert season_for_date(date(2026, 1, 6)) == "epiphany"
    assert season_for_date(date(2026, 2, 1)) == "epiphany"
    assert season_for_date(date(2026, 2, 18)) == "lent"          # Ash Wednesday
    assert season_for_date(date(2026, 3, 15)) == "lent"
    assert season_for_date(date(2026, 3, 29)) == "holy_week"     # Palm Sunday
    assert season_for_date(date(2026, 4, 4)) == "holy_week"      # Holy Saturday
    assert season_for_date(date(2026, 4, 5)) == "easter"         # Easter Sunday
    assert season_for_date(date(2026, 5, 1)) == "easter"
    assert season_for_date(date(2026, 5, 24)) == "pentecost"
    assert season_for_date(date(2026, 5, 25)) == "ordinary_time"
    assert season_for_date(date(2026, 10, 1)) == "ordinary_time"
    assert season_for_date(date(2026, 11, 20)) == "ordinary_time"
    assert season_for_date(date(2026, 11, 29)) == "advent"       # Advent Sunday
    assert season_for_date(date(2026, 12, 20)) == "advent"
    assert season_for_date(date(2026, 12, 24)) == "advent"
    assert season_for_date(date(2026, 12, 25)) == "christmas"
    assert season_for_date(date(2027, 1, 4)) == "christmas"


def test_ordinary_time_ends_the_day_before_advent_begins():
    for year in range(2024, 2031):
        advent_start = _advent_start(year)
        assert season_for_date(advent_start) == "advent"
        assert season_for_date(advent_start - timedelta(days=1)) == "ordinary_time"


def test_upcoming_sunday_from_various_weekdays():
    assert upcoming_sunday(date(2026, 8, 24)) == date(2026, 8, 30)  # Monday
    assert upcoming_sunday(date(2026, 8, 26)) == date(2026, 8, 30)  # Wednesday
    assert upcoming_sunday(date(2026, 8, 30)) == date(2026, 8, 30)  # Sunday itself
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
python3 -m pytest tests/test_liturgical_calendar.py -v
```

Expected: FAIL — `lectionary_engines.liturgical_calendar` does not exist yet.

- [ ] **Step 3: Create the module**

Create `lectionary_engines/liturgical_calendar.py`:

```python
"""
Liturgical calendar utilities shared across the app: computing which
Sunday is "this coming Sunday" (previously duplicated privately in both
lectionary_widget_service.py and signals_service.py - consolidated here
since Tier 4's reading_date/season capture needs the same calculation),
and bucketing a date into one of eight liturgical seasons for Study/
WorkshopPrep faceting.
"""

from datetime import date, timedelta

SEASONS = ["advent", "christmas", "epiphany", "lent", "holy_week", "easter", "pentecost", "ordinary_time"]


def _easter_sunday(year: int) -> date:
    """Gregorian Easter Sunday via the Meeus/Jones/Butcher algorithm."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _advent_start(year: int) -> date:
    """Advent Sunday: the Sunday between November 27 and December 3 inclusive."""
    nov27 = date(year, 11, 27)
    days_to_sunday = (6 - nov27.weekday()) % 7  # Monday=0 ... Sunday=6
    return nov27 + timedelta(days=days_to_sunday)


def upcoming_sunday(today: date) -> date:
    """The next Sunday on or after `today` (today itself, if today is a Sunday)."""
    days_until_sunday = (6 - today.weekday()) % 7
    return today + timedelta(days=days_until_sunday)


def season_for_date(d: date) -> str:
    """
    Buckets a date into one of SEASONS. Lent/Holy Week/Easter/Pentecost
    are moveable feasts computed from that year's Easter Sunday;
    Advent/Christmas/Epiphany are fixed-calendar-adjacent.

    'ordinary_time' covers only the post-Pentecost stretch through the
    day before the next Advent - the pre-Lent stretch (Jan 6 through the
    day before Ash Wednesday) is its own 'epiphany' bucket.
    """
    year = d.year

    if d.month == 1 and d.day <= 5:
        return "christmas"  # Jan 1-5: Christmastide begun by the previous year's Dec 25

    advent_start = _advent_start(year)
    if d.month == 12:
        if d < advent_start:
            return "ordinary_time"
        if d >= date(year, 12, 25):
            return "christmas"
        return "advent"

    if d >= advent_start:
        return "advent"

    easter = _easter_sunday(year)
    ash_wednesday = easter - timedelta(days=46)
    palm_sunday = easter - timedelta(days=7)
    pentecost = easter + timedelta(days=49)

    if date(year, 1, 6) <= d < ash_wednesday:
        return "epiphany"
    if ash_wednesday <= d < palm_sunday:
        return "lent"
    if palm_sunday <= d < easter:
        return "holy_week"
    if easter <= d < pentecost:
        return "easter"
    if d == pentecost:
        return "pentecost"
    return "ordinary_time"
```

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
python3 -m pytest tests/test_liturgical_calendar.py -v
```

Expected: all 6 PASS.

- [ ] **Step 5: Remove the duplicate from `lectionary_widget_service.py`**

In `web/services/lectionary_widget_service.py`, this exists (lines 24-39):

```python
import logging
from datetime import date, timedelta
from typing import Dict

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from lectionary_engines.text_fetcher import TextFetcher
from web.models import LectionaryReadingCache

logger = logging.getLogger(__name__)


def _upcoming_sunday(today: date) -> date:
    days_until_sunday = (6 - today.weekday()) % 7  # Monday=0 ... Sunday=6
    return today + timedelta(days=days_until_sunday)
```

Replace it with:

```python
import logging
from datetime import date
from typing import Dict

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from lectionary_engines.liturgical_calendar import upcoming_sunday
from lectionary_engines.text_fetcher import TextFetcher
from web.models import LectionaryReadingCache

logger = logging.getLogger(__name__)
```

Then, further down in the same file, find:

```python
    sunday = _upcoming_sunday(date.today())
```

Replace with:

```python
    sunday = upcoming_sunday(date.today())
```

- [ ] **Step 6: Remove the duplicate from `signals_service.py`**

In `web/services/signals_service.py`, this exists (lines 15-42):

```python
import json
import logging
from datetime import date, timedelta
from itertools import combinations
from typing import List

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from lectionary_engines.claude_client import ClaudeClient
from lectionary_engines.text_fetcher import TextFetcher
from lectionary_engines.theme_extractor import extract_themes
from web.models import LectionaryThemeCache
from web.services.lectionary_widget_service import get_this_week_readings

logger = logging.getLogger(__name__)

READING_LABELS = {
    "gospel": "Gospel",
    "epistle": "Epistle",
    "ot": "Hebrew Scripture",
    "psalm": "Psalm",
}


def _upcoming_sunday(today: date) -> date:
    days_until_sunday = (6 - today.weekday()) % 7  # Monday=0 ... Sunday=6
    return today + timedelta(days=days_until_sunday)
```

Replace it with:

```python
import json
import logging
from datetime import date
from itertools import combinations
from typing import List

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from lectionary_engines.claude_client import ClaudeClient
from lectionary_engines.liturgical_calendar import upcoming_sunday
from lectionary_engines.text_fetcher import TextFetcher
from lectionary_engines.theme_extractor import extract_themes
from web.models import LectionaryThemeCache
from web.services.lectionary_widget_service import get_this_week_readings

logger = logging.getLogger(__name__)

READING_LABELS = {
    "gospel": "Gospel",
    "epistle": "Epistle",
    "ot": "Hebrew Scripture",
    "psalm": "Psalm",
}
```

Then, further down in the same file, find:

```python
    sunday = _upcoming_sunday(date.today())
```

Replace with:

```python
    sunday = upcoming_sunday(date.today())
```

- [ ] **Step 7: Run the affected existing test suites to confirm no regression**

```bash
python3 -m pytest tests/test_lectionary_widget_service.py tests/test_signals_service.py -v
```

Expected: all PASS, unchanged from before this task (these tests mock `TextFetcher`/`extract_themes`, not the internal date helper, so this refactor should be invisible to them).

- [ ] **Step 8: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS, 0 failures.

- [ ] **Step 9: Commit**

```bash
git add lectionary_engines/liturgical_calendar.py tests/test_liturgical_calendar.py web/services/lectionary_widget_service.py web/services/signals_service.py
git commit -m "Add shared liturgical calendar utilities

season_for_date() buckets a date into one of eight liturgical seasons
via the Meeus/Jones/Butcher Easter algorithm - needed to compute
Study/WorkshopPrep.season for RCL-sourced content (Tier 4). Also
consolidates upcoming_sunday(), previously duplicated privately in
lectionary_widget_service.py and signals_service.py, into one shared
implementation."
```

---

### Task 2: `ContentTheme` model, `reading_date`/`season` columns, and `record_content_themes()` helper

**Files:**
- Modify: `web/models.py` (add `ContentTheme`; add `reading_date`/`season` to `Study` and `WorkshopPrep`)
- Modify: `web/database.py` (`COLUMN_MIGRATIONS` entries for the two new columns on each of `studies`/`workshop_preps`)
- Modify: `web/services/library_service.py` (add `record_content_themes()`)
- Test: `tests/test_library_service.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `web.models.ContentTheme` (new model, columns `id`, `content_type`, `content_id`, `theme`, `created_at`); `web.models.Study.reading_date`/`.season` and `web.models.WorkshopPrep.reading_date`/`.season` (new nullable columns); `record_content_themes(db: Session, content_type: str, content_id: int, themes: List[str]) -> None` in `web.services.library_service` — inserts one row per unique lowercased/trimmed theme, caller commits. Tasks 3, 4, 5, 6, 8, and 10 all call this function directly.

- [ ] **Step 1: Write the failing tests**

In `tests/test_library_service.py`, change the import block at the top from:

```python
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from web.models import Base, CulturalResonance, CurrentsAnalysis, Study, WorkshopPrep
from web.services.library_service import search_library
```

to:

```python
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from web.models import Base, ContentTheme, CulturalResonance, CurrentsAnalysis, Study, WorkshopPrep
from web.services.library_service import record_content_themes, search_library
```

Then append these tests at the end of the file:

```python
def test_record_content_themes_inserts_one_row_per_theme(db):
    record_content_themes(db, "study", 1, ["Hospitality", "Grace"])
    db.commit()

    rows = db.query(ContentTheme).filter(ContentTheme.content_type == "study", ContentTheme.content_id == 1).all()
    assert sorted(r.theme for r in rows) == ["grace", "hospitality"]


def test_record_content_themes_dedupes_and_skips_blank(db):
    record_content_themes(db, "study", 1, ["Hospitality", "hospitality", "  ", ""])
    db.commit()

    rows = db.query(ContentTheme).filter(ContentTheme.content_type == "study", ContentTheme.content_id == 1).all()
    assert len(rows) == 1
    assert rows[0].theme == "hospitality"


def test_reading_date_and_season_columns_exist_on_study_and_workshop(db):
    db.add(Study(
        engine="threshold", reference="John 3:16", content="text",
        reading_date=date(2026, 12, 20), season="advent",
    ))
    db.add(WorkshopPrep(
        lens="x", lens_name="X", reference="John 3:16", content="text",
        reading_date=date(2026, 12, 20), season="advent",
    ))
    db.commit()

    assert db.query(Study).one().season == "advent"
    assert db.query(WorkshopPrep).one().season == "advent"
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
python3 -m pytest tests/test_library_service.py -v -k "content_theme or reading_date"
```

Expected: FAIL — `ContentTheme` and `record_content_themes` don't exist yet, and `Study`/`WorkshopPrep` have no `reading_date`/`season` columns.

- [ ] **Step 3: Add the `ContentTheme` model**

In `web/models.py`, append this class at the end of the file (after `LectionaryThemeCache`, which currently ends at line 443):

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
    theme = Column(String(100), nullable=False, index=True)  # lowercase, trimmed
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('idx_content_theme_item', 'content_type', 'content_id'),
        UniqueConstraint('content_type', 'content_id', 'theme', name='uq_content_theme_item_theme'),
    )

    def __repr__(self):
        return f"<ContentTheme(content_type='{self.content_type}', content_id={self.content_id}, theme='{self.theme}')>"
```

- [ ] **Step 4: Add `reading_date`/`season` to `Study`**

In `web/models.py`, find (inside the `Study` class):

```python
    # Metadata
    source = Column(String(50))  # 'paste', 'run', 'moravian', 'rcl'
    translation = Column(String(20))  # 'NRSVue', 'NIV', 'CEB', 'NLT', 'MSG'
    biblical_text = Column(Text)  # Original biblical text used
```

Replace with:

```python
    # Metadata
    source = Column(String(50))  # 'paste', 'run', 'moravian', 'rcl'
    translation = Column(String(20))  # 'NRSVue', 'NIV', 'CEB', 'NLT', 'MSG'
    biblical_text = Column(Text)  # Original biblical text used

    # Lectionary season - only set for source='rcl'; a pasted or
    # Bible-Gateway-fetched passage has no inherent liturgical date
    reading_date = Column(Date, nullable=True, index=True)
    season = Column(String(30), nullable=True, index=True)
```

- [ ] **Step 5: Add `reading_date`/`season` to `WorkshopPrep`**

In `web/models.py`, find (inside the `WorkshopPrep` class):

```python
    # Metadata
    source = Column(String(50))  # 'paste', 'run', 'moravian', 'rcl'
    translation = Column(String(20))  # 'NRSVue', 'NIV', etc.
    biblical_text = Column(Text)  # Original biblical text used
```

Replace with:

```python
    # Metadata
    source = Column(String(50))  # 'paste', 'run', 'moravian', 'rcl'
    translation = Column(String(20))  # 'NRSVue', 'NIV', etc.
    biblical_text = Column(Text)  # Original biblical text used

    # Lectionary season - only set for source='rcl'; a pasted or
    # Bible-Gateway-fetched passage has no inherent liturgical date
    reading_date = Column(Date, nullable=True, index=True)
    season = Column(String(30), nullable=True, index=True)
```

- [ ] **Step 6: Add `COLUMN_MIGRATIONS` entries**

In `web/database.py`, find:

```python
    ("user_profiles", "cultural_artifacts_level", "INTEGER DEFAULT 0", "INTEGER DEFAULT 0"),
    ("user_profiles", "auto_news_integration", "BOOLEAN DEFAULT 0", "BOOLEAN DEFAULT FALSE"),
    ("users", "is_active", "BOOLEAN DEFAULT 1", "BOOLEAN DEFAULT TRUE"),
]
```

Replace with:

```python
    ("user_profiles", "cultural_artifacts_level", "INTEGER DEFAULT 0", "INTEGER DEFAULT 0"),
    ("user_profiles", "auto_news_integration", "BOOLEAN DEFAULT 0", "BOOLEAN DEFAULT FALSE"),
    ("users", "is_active", "BOOLEAN DEFAULT 1", "BOOLEAN DEFAULT TRUE"),
    ("studies", "reading_date", "DATE", "DATE"),
    ("studies", "season", "VARCHAR(30)", "VARCHAR(30)"),
    ("workshop_preps", "reading_date", "DATE", "DATE"),
    ("workshop_preps", "season", "VARCHAR(30)", "VARCHAR(30)"),
]
```

- [ ] **Step 7: Add `record_content_themes()`**

In `web/services/library_service.py`, change the top of the file from:

```python
import json
from typing import Optional

from sqlalchemy import String, cast, func, literal, or_, select, union_all
from sqlalchemy.orm import Session

from web.models import CulturalResonance, CurrentsAnalysis, Study, WorkshopPrep
```

to:

```python
import json
from typing import List, Optional

from sqlalchemy import String, cast, func, literal, or_, select, union_all
from sqlalchemy.orm import Session

from web.models import ContentTheme, CulturalResonance, CurrentsAnalysis, Study, WorkshopPrep
```

Then append this function at the end of the file:

```python


def record_content_themes(db: Session, content_type: str, content_id: int, themes: List[str]) -> None:
    """
    Inserts one ContentTheme row per unique (lowercased, trimmed) theme
    keyword for the given content item. Blank and duplicate themes
    (case-insensitively) are skipped. Callers are responsible for
    calling db.commit().
    """
    seen = set()
    for raw_theme in themes:
        theme = raw_theme.strip().lower()
        if not theme or theme in seen:
            continue
        seen.add(theme)
        db.add(ContentTheme(content_type=content_type, content_id=content_id, theme=theme))
```

- [ ] **Step 8: Run the tests to confirm they pass**

```bash
python3 -m pytest tests/test_library_service.py -v
```

Expected: all PASS (existing tests plus the 3 new ones).

- [ ] **Step 9: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS, 0 failures.

- [ ] **Step 10: Commit**

```bash
git add web/models.py web/database.py web/services/library_service.py tests/test_library_service.py
git commit -m "Add ContentTheme model, Study/WorkshopPrep season columns, and record_content_themes()

New content_theme association table (one row per content-item/theme
pair) is the uniform join target for theme faceting across all four
Library content types, which have no shared base model. New
reading_date/season columns on Study/WorkshopPrep are populated only
for RCL-sourced content (Task 3/4). record_content_themes() is the
single write path for content_theme, used by every generation route
and the backfill script."
```

---

### Task 3: Study generation persists `reading_date`/`season` and `content_theme`

**Files:**
- Modify: `web/routes/studies.py`
- Modify: `tests/conftest.py` (promote `isolated_client`/`study_client` fixtures from `test_route_smoke.py`)
- Modify: `tests/test_route_smoke.py` (remove the now-duplicated fixture definitions and their now-unused imports)
- Test: `tests/test_theme_persistence.py` (new file)

**Interfaces:**
- Consumes: `upcoming_sunday(today: date) -> date` and `season_for_date(d: date) -> str` from Task 1; `record_content_themes(db, content_type, content_id, themes)` from Task 2.
- Produces: `study_client` and `isolated_client` pytest fixtures now live in `tests/conftest.py`, available to any test file without import. Tasks 4, 5, 6 all use `study_client`.

- [ ] **Step 1: Promote `isolated_client`/`study_client` to `conftest.py`**

This is needed because Task 3's new test file (and Tasks 4-6's) need DB-backed POST-route testing, and duplicating these fixtures per-file would violate the project's existing single-definition convention for shared test fixtures.

In `tests/conftest.py`, replace the entire file:

```python
"""
Pytest configuration for web tests
"""

import pytest
from web.database import init_db, close_db


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Initialize the test database before any tests run."""
    init_db()
    yield
    close_db()
```

with:

```python
"""
Pytest configuration for web tests
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from web.app import app
from web.auth import create_session_cookie, COOKIE_NAME
from web.database import init_db, close_db, get_db
from web.models import Base


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Initialize the test database before any tests run."""
    init_db()
    yield
    close_db()


@pytest.fixture
def isolated_client():
    """
    An authenticated TestClient backed by an in-memory SQLite DB via a
    get_db override, instead of the real local lectionary.db.

    Any test that writes through a route (e.g. hits / and caches the
    mocked Sunday readings via LectionaryReadingCache) needs this: the
    plain `client` fixture in test_route_smoke.py uses the real local DB
    file with no cleanup, which would leak fake rows into it.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    c = TestClient(app)
    c.cookies.set(COOKIE_NAME, create_session_cookie(1))
    yield c

    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def study_client():
    """
    Like isolated_client, but also yields the session factory so tests
    can seed rows into (or read rows back out of) the same in-memory DB
    around the request under test.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    c = TestClient(app)
    c.cookies.set(COOKIE_NAME, create_session_cookie(1))
    yield c, SessionLocal

    app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 2: Remove the now-duplicated fixtures and unused imports from `test_route_smoke.py`**

In `tests/test_route_smoke.py`, find:

```python
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from web.app import app
from web.auth import create_session_cookie, COOKIE_NAME
from web.database import get_db
from web.models import Base, Study
```

Replace with:

```python
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from web.app import app
from web.auth import create_session_cookie, COOKIE_NAME
from web.models import Study
```

Then find and delete the entire `isolated_client` fixture definition (including its docstring and the blank lines immediately around it):

```python
@pytest.fixture
def isolated_client():
    """
    Like `client`, but backed by an in-memory SQLite DB via a get_db
    override instead of the real local lectionary.db.

    Every test that hits / needs this: that route has a write side effect
    - it caches the mocked Sunday readings via LectionaryReadingCache.
    Using the shared `client` fixture would leak those fake rows into the
    real local DB file with no cleanup. This fixture isolates that write
    and clears the override on teardown so it can't leak into other tests
    running in the same session.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    c = TestClient(app)
    c.cookies.set(COOKIE_NAME, create_session_cookie(1))
    yield c

    app.dependency_overrides.pop(get_db, None)
```

And delete the entire `study_client` fixture definition the same way:

```python
@pytest.fixture
def study_client():
    """
    Like isolated_client, but also yields the session factory so tests
    can seed a Study row into the same in-memory DB before hitting the
    route under test.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    c = TestClient(app)
    c.cookies.set(COOKIE_NAME, create_session_cookie(1))
    yield c, SessionLocal

    app.dependency_overrides.pop(get_db, None)
```

`Study` stays imported — it's still used later in the file by the Palimpsest tests that unpack `study_client`.

- [ ] **Step 3: Run the full suite to confirm the fixture move didn't break anything**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS, same count as before this task — pytest auto-discovers fixtures from `conftest.py`, so every test that referenced `isolated_client`/`study_client` by name keeps working with no changes to the test functions themselves.

- [ ] **Step 4: Write the failing tests**

Create `tests/test_theme_persistence.py`:

```python
"""
Tests that content generation persists Tier 4 taxonomy data:
reading_date/season (RCL-sourced Study/WorkshopPrep only) and
content_theme rows (every content type, every source).

Each generation route's expensive/external step (the engine's Claude
call, TextFetcher fetches) is mocked at the service-getter level so
these tests exercise real route wiring and real DB writes against an
in-memory SQLite DB, without any network or Claude API call.
"""

from unittest.mock import MagicMock, patch

from web.models import ContentTheme, Study


@patch("web.routes.studies.extract_themes")
@patch("web.routes.studies.get_generator_service")
def test_rcl_sourced_study_gets_reading_date_and_season(mock_get_generator, mock_extract_themes, study_client):
    client, SessionLocal = study_client

    mock_generator = MagicMock()
    mock_generator.fetch_rcl.return_value = ("John 3:16-21", "For God so loved the world")
    mock_generator.generate_study.return_value = {
        "engine": "threshold",
        "reference": "John 3:16-21",
        "content": "study content",
        "metadata": {"word_count": 42},
        "biblical_text": "For God so loved the world",
    }
    mock_get_generator.return_value = mock_generator
    mock_extract_themes.return_value = ["hospitality", "grace"]

    response = client.post("/generate", data={
        "engine": "threshold",
        "source": "rcl",
        "rcl_reading": "gospel",
        "translation": "NRSVue",
        "run_validation": "false",
    })

    assert response.status_code == 303

    db = SessionLocal()
    study = db.query(Study).one()
    assert study.reading_date is not None
    assert study.season is not None
    themes = {t.theme for t in db.query(ContentTheme).filter(ContentTheme.content_type == "study").all()}
    assert themes == {"hospitality", "grace"}
    db.close()


@patch("web.routes.studies.extract_themes")
@patch("web.routes.studies.get_generator_service")
def test_pasted_study_has_no_reading_date_or_season_but_still_gets_themes(
    mock_get_generator, mock_extract_themes, study_client
):
    client, SessionLocal = study_client

    mock_generator = MagicMock()
    mock_generator.generate_study.return_value = {
        "engine": "threshold",
        "reference": "John 3:16-21",
        "content": "study content",
        "metadata": {"word_count": 42},
        "biblical_text": "For God so loved the world",
    }
    mock_get_generator.return_value = mock_generator
    mock_extract_themes.return_value = ["hospitality"]

    response = client.post("/generate", data={
        "engine": "threshold",
        "source": "paste",
        "reference": "John 3:16-21",
        "text": "For God so loved the world",
        "translation": "NRSVue",
        "run_validation": "false",
    })

    assert response.status_code == 303

    db = SessionLocal()
    study = db.query(Study).one()
    assert study.reading_date is None
    assert study.season is None
    themes = {t.theme for t in db.query(ContentTheme).filter(ContentTheme.content_type == "study").all()}
    assert themes == {"hospitality"}
    db.close()
```

- [ ] **Step 5: Run the tests to confirm they fail**

```bash
python3 -m pytest tests/test_theme_persistence.py -v
```

Expected: both FAIL — `Study.reading_date`/`.season` stay `None` for the RCL case (route doesn't set them yet), and no `ContentTheme` rows exist yet (route never calls `record_content_themes`).

- [ ] **Step 6: Update imports in `web/routes/studies.py`**

Find:

```python
"""
Study routes - API endpoints for study generation and retrieval
"""

from fastapi import APIRouter, Depends, HTTPException, Form, Request
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from typing import Optional
import markdown
import traceback
import logging

logger = logging.getLogger(__name__)

from ..database import get_db
from ..models import Study, UserProfile
from ..services.study_generator import StudyGeneratorService
from ..services.currents_service import CurrentsService
from ..services.cultural_grounding_service import build_grounding_for_passage
from ..config import WebConfig
from lectionary_engines.preferences import StudyPreferences
from lectionary_engines.theme_extractor import extract_themes
import json
```

Replace with:

```python
"""
Study routes - API endpoints for study generation and retrieval
"""

from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Form, Request
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from typing import Optional
import markdown
import traceback
import logging

logger = logging.getLogger(__name__)

from ..database import get_db
from ..models import Study, UserProfile
from ..services.study_generator import StudyGeneratorService
from ..services.currents_service import CurrentsService
from ..services.cultural_grounding_service import build_grounding_for_passage
from ..services.library_service import record_content_themes
from ..config import WebConfig
from lectionary_engines.preferences import StudyPreferences
from lectionary_engines.theme_extractor import extract_themes
from lectionary_engines.liturgical_calendar import season_for_date, upcoming_sunday
import json
```

- [ ] **Step 7: Always extract themes, and compute `reading_date`/`season` for RCL**

Find:

```python
        # Shared theme extraction - one cheap call feeds both auto news
        # integration and cultural grounding below, if either is needed.
        passage_themes = None
        needs_auto_news = (
            not resolved_news_context and profile is not None and profile.auto_news_integration
        )
        needs_grounding = preferences is not None and preferences.cultural_artifacts_level > 0
        if needs_auto_news or needs_grounding:
            # extract_themes() is a blocking Claude call - run off the event loop.
            passage_themes = await run_in_threadpool(extract_themes, generator.claude, reference, text)
```

Replace with:

```python
        # Theme extraction now runs unconditionally (previously gated on
        # needs_auto_news/needs_grounding) - Tier 4 needs themes persisted
        # on every study, not just ones that needed them for another
        # feature. extract_themes() is a blocking Claude call - run off
        # the event loop.
        needs_auto_news = (
            not resolved_news_context and profile is not None and profile.auto_news_integration
        )
        needs_grounding = preferences is not None and preferences.cultural_artifacts_level > 0
        passage_themes = await run_in_threadpool(extract_themes, generator.claude, reference, text)
```

Then find:

```python
        # Create database record
        study = Study(
            engine=study_data['engine'],
            reference=study_data['reference'],
            content=study_data['content'],
            word_count=study_data.get('metadata', {}).get('word_count'),
            source=source,
            translation=translation,
            biblical_text=study_data.get('biblical_text'),
            reference_normalized=reference.lower().strip(),
            profile_name=profile_name,
            custom_preferences=custom_prefs_json,
            news_integrated=bool(resolved_news_context),
            news_context=resolved_news_context,
            news_date=resolved_news_date,
            validation_score=validation_score,
            validation_recommendation=validation_recommendation,
            validation_data=validation_data_json
        )

        # Save to database
        db.add(study)
        db.commit()
        db.refresh(study)

        # Redirect to study view page
        return RedirectResponse(url=f"/study/{study.id}", status_code=303)
```

Replace with:

```python
        # Lectionary season - only meaningful for RCL-sourced content; a
        # pasted or Bible-Gateway-fetched passage has no inherent
        # liturgical date.
        reading_date = None
        season = None
        if source == "rcl":
            reading_date = upcoming_sunday(date.today())
            season = season_for_date(reading_date)

        # Create database record
        study = Study(
            engine=study_data['engine'],
            reference=study_data['reference'],
            content=study_data['content'],
            word_count=study_data.get('metadata', {}).get('word_count'),
            source=source,
            translation=translation,
            biblical_text=study_data.get('biblical_text'),
            reference_normalized=reference.lower().strip(),
            profile_name=profile_name,
            custom_preferences=custom_prefs_json,
            news_integrated=bool(resolved_news_context),
            news_context=resolved_news_context,
            news_date=resolved_news_date,
            validation_score=validation_score,
            validation_recommendation=validation_recommendation,
            validation_data=validation_data_json,
            reading_date=reading_date,
            season=season,
        )

        # Save to database
        db.add(study)
        db.commit()
        db.refresh(study)

        # Persist extracted themes for Library theme faceting.
        record_content_themes(db, "study", study.id, passage_themes)
        db.commit()

        # Redirect to study view page
        return RedirectResponse(url=f"/study/{study.id}", status_code=303)
```

- [ ] **Step 8: Run the tests to confirm they pass**

```bash
python3 -m pytest tests/test_theme_persistence.py -v
```

Expected: both PASS.

- [ ] **Step 9: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS, 0 failures. (This is a meaningful checkpoint: `passage_themes` is now computed unconditionally, so any existing test that hits `/generate` with `run_validation` unset or `"true"` and doesn't mock `extract_themes` would now make a real Claude call. If any such test fails or hangs here, find it and add a `@patch("web.routes.studies.extract_themes")` the same way this task's own tests do.)

- [ ] **Step 10: Commit**

```bash
git add tests/conftest.py tests/test_route_smoke.py tests/test_theme_persistence.py web/routes/studies.py
git commit -m "Persist theme/season data on Study generation

extract_themes() now runs unconditionally at /generate (previously
gated on auto-news-integration/cultural-grounding needs) so every
study gets content_theme rows via record_content_themes(). RCL-sourced
studies also get reading_date/season populated via Task 1's
liturgical_calendar utilities.

Promotes isolated_client/study_client from test_route_smoke.py to
conftest.py so this task's new POST-route tests (and Tasks 4-6's) can
use them without duplicating the fixture definitions."
```

---

### Task 4: Workshop generation persists `reading_date`/`season` and `content_theme`

**Files:**
- Modify: `web/routes/workshop.py`
- Modify: `tests/test_theme_persistence.py`

**Interfaces:**
- Consumes: `upcoming_sunday`/`season_for_date` (Task 1), `record_content_themes` (Task 2), `study_client` fixture (Task 3).
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_theme_persistence.py`:

```python
from web.models import WorkshopPrep


@patch("web.routes.workshop.extract_themes")
@patch("web.routes.workshop.get_workshop_engine")
@patch("web.routes.workshop.get_text_fetcher")
def test_rcl_sourced_workshop_gets_reading_date_and_season(
    mock_get_text_fetcher, mock_get_workshop_engine, mock_extract_themes, study_client
):
    client, SessionLocal = study_client

    mock_fetcher = MagicMock()
    mock_fetcher.fetch_rcl.return_value = ("Luke 14:1-14", "Sabbath hospitality text")
    mock_get_text_fetcher.return_value = mock_fetcher

    mock_engine = MagicMock()
    mock_engine.claude = MagicMock()
    mock_engine.generate.return_value = {
        "lens": "apostolic_journalist",
        "lens_name": "The Apostolic Journalist",
        "reference": "Luke 14:1-14",
        "content": "workshop content",
        "metadata": {"word_count": 30},
    }
    mock_get_workshop_engine.return_value = mock_engine
    mock_extract_themes.return_value = ["hospitality"]

    response = client.post("/workshop/generate", data={
        "lens": "apostolic_journalist",
        "source": "rcl",
        "rcl_reading": "gospel",
        "translation": "NRSVue",
    })

    assert response.status_code == 303

    db = SessionLocal()
    prep = db.query(WorkshopPrep).one()
    assert prep.reading_date is not None
    assert prep.season is not None
    themes = {t.theme for t in db.query(ContentTheme).filter(ContentTheme.content_type == "workshop").all()}
    assert themes == {"hospitality"}
    db.close()
```

- [ ] **Step 2: Run it to confirm it fails**

```bash
python3 -m pytest tests/test_theme_persistence.py -v -k workshop
```

Expected: FAIL — `WorkshopPrep.reading_date`/`.season` stay `None`, no `ContentTheme` rows.

- [ ] **Step 3: Update imports in `web/routes/workshop.py`**

Find:

```python
"""
Workshop routes - API endpoints for Pastor's Workshop sermon prep tool
"""

from fastapi import APIRouter, Depends, HTTPException, Form, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from typing import Optional
from pathlib import Path

from ..database import get_db
from ..models import WorkshopPrep
from ..config import WebConfig
from ..services.pdf_service import render_pdf, slugify

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lectionary_engines.claude_client import ClaudeClient
from lectionary_engines.engines.workshop import WorkshopEngine
from lectionary_engines.scripture_linker import link_scripture_references
from lectionary_engines.text_fetcher import TextFetcher
from lectionary_engines.protocols import workshop_protocol
```

Replace with:

```python
"""
Workshop routes - API endpoints for Pastor's Workshop sermon prep tool
"""

from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Form, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from typing import Optional
from pathlib import Path

from ..database import get_db
from ..models import WorkshopPrep
from ..config import WebConfig
from ..services.library_service import record_content_themes
from ..services.pdf_service import render_pdf, slugify

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lectionary_engines.claude_client import ClaudeClient
from lectionary_engines.engines.workshop import WorkshopEngine
from lectionary_engines.liturgical_calendar import season_for_date, upcoming_sunday
from lectionary_engines.scripture_linker import link_scripture_references
from lectionary_engines.text_fetcher import TextFetcher
from lectionary_engines.theme_extractor import extract_themes
from lectionary_engines.protocols import workshop_protocol
```

- [ ] **Step 4: Extract themes, compute `reading_date`/`season`, and persist**

Find:

```python
        # Generate workshop scaffolding. This is a blocking Claude API call
        # that can take 30-60+ seconds - run off the event loop so the
        # single Uvicorn worker can still serve other requests while it's
        # in flight.
        result = await run_in_threadpool(
            engine.generate,
            text=text,
            reference=reference,
            lens=lens
        )

        # Save to database
        prep = WorkshopPrep(
            lens=result['lens'],
            lens_name=result['lens_name'],
            reference=result['reference'],
            content=result['content'],
            word_count=result['metadata']['word_count'],
            source=source,
            translation=translation,
            biblical_text=text
        )

        db.add(prep)
        db.commit()
        db.refresh(prep)

        # Redirect to result view
        return RedirectResponse(url=f"/workshop/{prep.id}", status_code=303)
```

Replace with:

```python
        # Generate workshop scaffolding. This is a blocking Claude API call
        # that can take 30-60+ seconds - run off the event loop so the
        # single Uvicorn worker can still serve other requests while it's
        # in flight.
        result = await run_in_threadpool(
            engine.generate,
            text=text,
            reference=reference,
            lens=lens
        )

        # extract_themes() is a blocking Claude call - run off the event loop.
        passage_themes = await run_in_threadpool(extract_themes, engine.claude, reference, text)

        # Lectionary season - only meaningful for RCL-sourced content; a
        # pasted or Bible-Gateway-fetched passage has no inherent
        # liturgical date.
        reading_date = None
        season = None
        if source == "rcl":
            reading_date = upcoming_sunday(date.today())
            season = season_for_date(reading_date)

        # Save to database
        prep = WorkshopPrep(
            lens=result['lens'],
            lens_name=result['lens_name'],
            reference=result['reference'],
            content=result['content'],
            word_count=result['metadata']['word_count'],
            source=source,
            translation=translation,
            biblical_text=text,
            reading_date=reading_date,
            season=season,
        )

        db.add(prep)
        db.commit()
        db.refresh(prep)

        # Persist extracted themes for Library theme faceting.
        record_content_themes(db, "workshop", prep.id, passage_themes)
        db.commit()

        # Redirect to result view
        return RedirectResponse(url=f"/workshop/{prep.id}", status_code=303)
```

- [ ] **Step 5: Run the tests to confirm they pass**

```bash
python3 -m pytest tests/test_theme_persistence.py -v
```

Expected: all PASS (Task 3's two tests plus this task's new one).

- [ ] **Step 6: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS, 0 failures.

- [ ] **Step 7: Commit**

```bash
git add web/routes/workshop.py tests/test_theme_persistence.py
git commit -m "Persist theme/season data on Workshop generation

Mirrors Task 3's Study treatment: /workshop/generate now calls
extract_themes() (new to this route) and persists content_theme rows
via record_content_themes(), plus reading_date/season for RCL-sourced
preps via Task 1's liturgical_calendar utilities."
```

---

### Task 5: Currents generation persists `content_theme`

**Files:**
- Modify: `web/routes/currents.py`
- Modify: `tests/test_theme_persistence.py`

**Interfaces:**
- Consumes: `record_content_themes` (Task 2), `study_client` fixture (Task 3).
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_theme_persistence.py`:

```python
from web.models import CurrentsAnalysis


@patch("web.routes.currents.extract_themes")
@patch("web.routes.currents.get_currents_service")
def test_currents_analysis_gets_content_theme_rows(mock_get_service, mock_extract_themes, study_client):
    client, SessionLocal = study_client

    mock_service = MagicMock()
    mock_service.analyze_story.return_value = {
        "date": "August 28, 2026",
        "headline_summary": "A Test Headline",
        "content": "analysis content",
        "word_count": 50,
    }
    mock_get_service.return_value = mock_service
    mock_extract_themes.return_value = ["justice", "community"]

    response = client.post("/currents/analyze", data={
        "story_context": "Some news story about justice and community.",
    })

    assert response.status_code == 303

    db = SessionLocal()
    assert db.query(CurrentsAnalysis).count() == 1
    themes = {t.theme for t in db.query(ContentTheme).filter(ContentTheme.content_type == "currents").all()}
    assert themes == {"justice", "community"}
    db.close()
```

- [ ] **Step 2: Run it to confirm it fails**

```bash
python3 -m pytest tests/test_theme_persistence.py -v -k currents
```

Expected: FAIL — `web.routes.currents.extract_themes` doesn't exist to patch yet, and no `ContentTheme` rows are created.

- [ ] **Step 3: Update imports in `web/routes/currents.py`**

Find:

```python
from fastapi import APIRouter, Depends, HTTPException, Form, Request
from fastapi.responses import RedirectResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from typing import Optional
from pathlib import Path
import markdown

from ..database import get_db
from ..models import CurrentsAnalysis
from ..config import WebConfig
from ..services.currents_service import CurrentsService
from ..services.pdf_service import render_pdf, slugify
from lectionary_engines.scripture_linker import link_scripture_references
```

Replace with:

```python
from fastapi import APIRouter, Depends, HTTPException, Form, Request
from fastapi.responses import RedirectResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from typing import Optional
from pathlib import Path
import markdown

from ..database import get_db
from ..models import CurrentsAnalysis
from ..config import WebConfig
from ..services.currents_service import CurrentsService
from ..services.library_service import record_content_themes
from ..services.pdf_service import render_pdf, slugify
from lectionary_engines.scripture_linker import link_scripture_references
from lectionary_engines.theme_extractor import extract_themes
```

- [ ] **Step 4: Extract themes and persist after save**

Find:

```python
        # Save to database
        analysis = CurrentsAnalysis(
            analysis_date=result["date"],
            news_source=news_source,
            headline_summary=result["headline_summary"],
            story_context=story_context[:5000],
            content=result["content"],
            word_count=result["word_count"],
        )

        db.add(analysis)
        db.commit()
        db.refresh(analysis)

        return RedirectResponse(url=f"/currents/{analysis.id}", status_code=303)
```

Replace with:

```python
        # Save to database
        analysis = CurrentsAnalysis(
            analysis_date=result["date"],
            news_source=news_source,
            headline_summary=result["headline_summary"],
            story_context=story_context[:5000],
            content=result["content"],
            word_count=result["word_count"],
        )

        db.add(analysis)
        db.commit()
        db.refresh(analysis)

        # extract_themes() is a blocking Claude call - run off the event
        # loop. CurrentsAnalysis has no scripture reference, so the
        # headline stands in for context in the extraction prompt.
        passage_themes = await run_in_threadpool(
            extract_themes,
            get_currents_service().claude,
            analysis.headline_summary or "Current Event",
            analysis.story_context or "",
        )
        record_content_themes(db, "currents", analysis.id, passage_themes)
        db.commit()

        return RedirectResponse(url=f"/currents/{analysis.id}", status_code=303)
```

- [ ] **Step 5: Run the tests to confirm they pass**

```bash
python3 -m pytest tests/test_theme_persistence.py -v
```

Expected: all PASS.

- [ ] **Step 6: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS, 0 failures.

- [ ] **Step 7: Commit**

```bash
git add web/routes/currents.py tests/test_theme_persistence.py
git commit -m "Persist theme data on Currents analysis generation

/currents/analyze now calls extract_themes() against the saved
analysis's headline/story context and persists content_theme rows via
record_content_themes(), matching the treatment Study/Workshop
generation got in Tasks 3-4."
```

---

### Task 6: Resonance generation persists `content_theme`

**Files:**
- Modify: `web/routes/resonance.py`
- Modify: `tests/test_theme_persistence.py`

**Interfaces:**
- Consumes: `record_content_themes` (Task 2), `study_client` fixture (Task 3).
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_theme_persistence.py`:

```python
@patch("web.routes.resonance.get_resonance_engine")
def test_resonance_find_gets_content_theme_rows(mock_get_engine, study_client):
    client, SessionLocal = study_client

    mock_engine = MagicMock()
    mock_engine.claude = MagicMock()  # truthy, so the "claude" mining_mode branch is taken
    mock_engine.mine_artifacts.return_value = "resonance content"
    mock_get_engine.return_value = mock_engine

    response = client.post("/resonance/find", data={
        "themes": "Hospitality, Empire",
        "mining_mode": "claude",
    })

    assert response.status_code == 303

    db = SessionLocal()
    themes = {t.theme for t in db.query(ContentTheme).filter(ContentTheme.content_type == "resonance").all()}
    assert themes == {"hospitality", "empire"}
    db.close()
```

This doesn't need `extract_themes` mocked — `CulturalResonance` already has its theme list in hand from the submitted form (`theme_list`), so no new Claude call is made for this route.

- [ ] **Step 2: Run it to confirm it fails**

```bash
python3 -m pytest tests/test_theme_persistence.py -v -k resonance
```

Expected: FAIL — no `ContentTheme` rows are created yet.

- [ ] **Step 3: Update imports in `web/routes/resonance.py`**

Find:

```python
from ..database import get_db
from ..models import CulturalResonance, Study, WorkshopPrep
from ..config import WebConfig
from ..services.pdf_service import render_pdf, slugify
```

Replace with:

```python
from ..database import get_db
from ..models import CulturalResonance, Study, WorkshopPrep
from ..config import WebConfig
from ..services.library_service import record_content_themes
from ..services.pdf_service import render_pdf, slugify
```

- [ ] **Step 4: Persist themes after both `CulturalResonance` save points**

Find (in `find_resonances`):

```python
        # Save to database
        resonance = CulturalResonance(
            themes=json.dumps(theme_list),
            reference=reference,
            content=content,
            artifacts_found=artifacts_found,
            sources_used=json.dumps(sources_used)
        )
        db.add(resonance)
        db.commit()
        db.refresh(resonance)

        return RedirectResponse(url=f"/resonance/{resonance.id}", status_code=303)
```

Replace with:

```python
        # Save to database
        resonance = CulturalResonance(
            themes=json.dumps(theme_list),
            reference=reference,
            content=content,
            artifacts_found=artifacts_found,
            sources_used=json.dumps(sources_used)
        )
        db.add(resonance)
        db.commit()
        db.refresh(resonance)

        # theme_list is already in hand - no new Claude call needed.
        record_content_themes(db, "resonance", resonance.id, theme_list)
        db.commit()

        return RedirectResponse(url=f"/resonance/{resonance.id}", status_code=303)
```

Find (in `resonance_from_study`):

```python
    # Save
    resonance = CulturalResonance(
        study_id=study_id,
        themes=json.dumps(theme_list),
        reference=study.reference,
        content=content,
        artifacts_found=len(artifacts),
        sources_used=json.dumps(list(set(a.source_name for a in artifacts)))
    )
    db.add(resonance)
    db.commit()
    db.refresh(resonance)

    return RedirectResponse(url=f"/resonance/{resonance.id}", status_code=303)
```

Replace with:

```python
    # Save
    resonance = CulturalResonance(
        study_id=study_id,
        themes=json.dumps(theme_list),
        reference=study.reference,
        content=content,
        artifacts_found=len(artifacts),
        sources_used=json.dumps(list(set(a.source_name for a in artifacts)))
    )
    db.add(resonance)
    db.commit()
    db.refresh(resonance)

    # theme_list is already in hand - no new Claude call needed.
    record_content_themes(db, "resonance", resonance.id, theme_list)
    db.commit()

    return RedirectResponse(url=f"/resonance/{resonance.id}", status_code=303)
```

- [ ] **Step 5: Run the tests to confirm they pass**

```bash
python3 -m pytest tests/test_theme_persistence.py -v
```

Expected: all PASS (this task's plus Tasks 3-5's).

- [ ] **Step 6: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS, 0 failures.

- [ ] **Step 7: Commit**

```bash
git add web/routes/resonance.py tests/test_theme_persistence.py
git commit -m "Persist theme data on Resonance generation

Both CulturalResonance save points (/resonance/find and
/resonance/from-study) now call record_content_themes() with the
theme_list already computed for the search - no new Claude call needed,
unlike Study/Workshop/Currents in Tasks 3-5."
```

---

### Task 7: Facet filters and `get_library_facets()` in `library_service.py`

**Files:**
- Modify: `web/services/library_service.py`
- Test: `tests/test_library_service.py`

**Interfaces:**
- Consumes: `ContentTheme`, `Study.season`/`.source`, `WorkshopPrep.season`/`.source` (Task 2).
- Produces: `search_library(db, content_type=None, q=None, theme=None, season=None, source=None, page=1, per_page=12) -> dict` (three new optional params, same return shape as before); `get_library_facets(db: Session) -> dict` returning `{"seasons": [{"value": str, "label": str}, ...], "sources": [str, ...], "themes": [{"theme": str, "count": int}, ...]}`. Task 8 consumes both directly.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_library_service.py`:

```python
from web.services.library_service import get_library_facets


def test_theme_filter_returns_only_matching_content(db):
    base_time = datetime(2026, 8, 28, 12, 0, 0)
    _seed_one_of_each(db, base_time)
    record_content_themes(db, "study", 1, ["hospitality"])
    db.commit()

    result = search_library(db, theme="hospitality")

    assert result["total"] == 1
    assert result["results"][0]["content_type"] == "study"


def test_season_filter_returns_only_matching_study(db):
    base_time = datetime(2026, 8, 28, 12, 0, 0)
    db.add(Study(engine="threshold", reference="A", content="a", season="advent", created_at=base_time))
    db.add(Study(engine="threshold", reference="B", content="b", season="lent", created_at=base_time))
    db.commit()

    result = search_library(db, season="advent")

    assert result["total"] == 1
    assert result["results"][0]["title"] == "A"


def test_source_filter_only_applies_to_study_and_workshop(db):
    base_time = datetime(2026, 8, 28, 12, 0, 0)
    _seed_one_of_each(db, base_time)  # none of the seeded rows have source set

    result = search_library(db, source="rcl")

    assert result["total"] == 0


def test_season_and_theme_filters_combine_with_and_semantics(db):
    base_time = datetime(2026, 8, 28, 12, 0, 0)
    db.add(Study(engine="threshold", reference="A", content="a", season="advent", created_at=base_time))
    db.add(Study(engine="threshold", reference="B", content="b", season="lent", created_at=base_time))
    db.commit()
    record_content_themes(db, "study", 1, ["hospitality"])
    record_content_themes(db, "study", 2, ["hospitality"])
    db.commit()

    # Both studies have the theme, but only one is in the right season -
    # AND semantics means only that one should come back.
    result = search_library(db, season="advent", theme="hospitality")

    assert result["total"] == 1
    assert result["results"][0]["title"] == "A"


def test_season_filter_combined_with_content_type_currents_returns_nothing_without_erroring(db):
    base_time = datetime(2026, 8, 28, 12, 0, 0)
    _seed_one_of_each(db, base_time)

    result = search_library(db, content_type="currents", season="lent")

    assert result["total"] == 0


def test_get_library_facets_returns_distinct_values_with_counts(db):
    base_time = datetime(2026, 8, 28, 12, 0, 0)
    db.add(Study(engine="threshold", reference="A", content="a", source="rcl", season="advent", created_at=base_time))
    db.add(Study(engine="threshold", reference="B", content="b", source="paste", season="lent", created_at=base_time))
    db.commit()
    record_content_themes(db, "study", 1, ["hospitality", "grace"])
    record_content_themes(db, "study", 2, ["hospitality"])
    db.commit()

    facets = get_library_facets(db)

    assert facets["seasons"] == [{"value": "advent", "label": "Advent"}, {"value": "lent", "label": "Lent"}]
    assert facets["sources"] == ["paste", "rcl"]
    assert facets["themes"][0] == {"theme": "hospitality", "count": 2}
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
python3 -m pytest tests/test_library_service.py -v -k "theme_filter or season_filter or source_filter or get_library_facets"
```

Expected: FAIL — `search_library()` doesn't accept `theme`/`season`/`source` yet, and `get_library_facets` doesn't exist.

- [ ] **Step 3: Add `source`/`season` to the per-type select builders**

In `web/services/library_service.py`, find:

```python
def _study_select(q: Optional[str]):
    stmt = select(
        Study.id.label("id"),
        literal("study").label("content_type"),
        cast(Study.reference, String).label("title"),
        cast(Study.engine, String).label("badge_label"),
        Study.created_at.label("created_at"),
    )
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Study.reference.ilike(like), Study.content.ilike(like)))
    return stmt


def _workshop_select(q: Optional[str]):
    stmt = select(
        WorkshopPrep.id.label("id"),
        literal("workshop").label("content_type"),
        cast(WorkshopPrep.reference, String).label("title"),
        cast(literal("Workshop"), String).label("badge_label"),
        WorkshopPrep.created_at.label("created_at"),
    )
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(WorkshopPrep.reference.ilike(like), WorkshopPrep.content.ilike(like)))
    return stmt


def _currents_select(q: Optional[str]):
    title_expr = func.coalesce(CurrentsAnalysis.headline_summary, literal("Theological News Analysis"))
    stmt = select(
        CurrentsAnalysis.id.label("id"),
        literal("currents").label("content_type"),
        cast(title_expr, String).label("title"),
        cast(literal("Currents"), String).label("badge_label"),
        CurrentsAnalysis.created_at.label("created_at"),
    )
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(
            CurrentsAnalysis.headline_summary.ilike(like),
            CurrentsAnalysis.story_context.ilike(like),
            CurrentsAnalysis.content.ilike(like),
        ))
    return stmt


def _resonance_select(q: Optional[str]):
    # title falls back to the raw `themes` JSON string when reference is
    # null; _format_title() below parses and joins it into a readable
    # string ("Hospitality, Empire") after the query runs - that
    # formatting can't be done portably in SQL.
    title_expr = func.coalesce(CulturalResonance.reference, CulturalResonance.themes)
    stmt = select(
        CulturalResonance.id.label("id"),
        literal("resonance").label("content_type"),
        cast(title_expr, String).label("title"),
        cast(literal("Resonance"), String).label("badge_label"),
        CulturalResonance.created_at.label("created_at"),
    )
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(
            CulturalResonance.reference.ilike(like),
            CulturalResonance.themes.ilike(like),
            CulturalResonance.content.ilike(like),
        ))
    return stmt
```

Replace with:

```python
def _study_select(q: Optional[str]):
    stmt = select(
        Study.id.label("id"),
        literal("study").label("content_type"),
        cast(Study.reference, String).label("title"),
        cast(Study.engine, String).label("badge_label"),
        Study.created_at.label("created_at"),
        cast(Study.source, String).label("source"),
        cast(Study.season, String).label("season"),
    )
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Study.reference.ilike(like), Study.content.ilike(like)))
    return stmt


def _workshop_select(q: Optional[str]):
    stmt = select(
        WorkshopPrep.id.label("id"),
        literal("workshop").label("content_type"),
        cast(WorkshopPrep.reference, String).label("title"),
        cast(literal("Workshop"), String).label("badge_label"),
        WorkshopPrep.created_at.label("created_at"),
        cast(WorkshopPrep.source, String).label("source"),
        cast(WorkshopPrep.season, String).label("season"),
    )
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(WorkshopPrep.reference.ilike(like), WorkshopPrep.content.ilike(like)))
    return stmt


def _currents_select(q: Optional[str]):
    title_expr = func.coalesce(CurrentsAnalysis.headline_summary, literal("Theological News Analysis"))
    stmt = select(
        CurrentsAnalysis.id.label("id"),
        literal("currents").label("content_type"),
        cast(title_expr, String).label("title"),
        cast(literal("Currents"), String).label("badge_label"),
        CurrentsAnalysis.created_at.label("created_at"),
        cast(null(), String).label("source"),
        cast(null(), String).label("season"),
    )
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(
            CurrentsAnalysis.headline_summary.ilike(like),
            CurrentsAnalysis.story_context.ilike(like),
            CurrentsAnalysis.content.ilike(like),
        ))
    return stmt


def _resonance_select(q: Optional[str]):
    # title falls back to the raw `themes` JSON string when reference is
    # null; _format_title() below parses and joins it into a readable
    # string ("Hospitality, Empire") after the query runs - that
    # formatting can't be done portably in SQL.
    title_expr = func.coalesce(CulturalResonance.reference, CulturalResonance.themes)
    stmt = select(
        CulturalResonance.id.label("id"),
        literal("resonance").label("content_type"),
        cast(title_expr, String).label("title"),
        cast(literal("Resonance"), String).label("badge_label"),
        CulturalResonance.created_at.label("created_at"),
        cast(null(), String).label("source"),
        cast(null(), String).label("season"),
    )
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(
            CulturalResonance.reference.ilike(like),
            CulturalResonance.themes.ilike(like),
            CulturalResonance.content.ilike(like),
        ))
    return stmt
```

`source`/`season` are `NULL`-filled for `currents`/`resonance` so every branch of the `union_all()` has the same column shape — required for `UNION ALL` to work at all, and the mechanism that makes the two new filters correctly return zero `currents`/`resonance` rows (Step 8's `test_source_filter_only_applies_to_study_and_workshop`).

- [ ] **Step 4: Add the `null` import**

Find:

```python
from sqlalchemy import String, cast, func, literal, or_, select, union_all
```

Replace with:

```python
from sqlalchemy import String, cast, func, literal, null, or_, select, union_all
```

- [ ] **Step 5: Add `theme`/`season`/`source` filtering to `search_library()`**

Find:

```python
def search_library(
    db: Session,
    content_type: Optional[str] = None,
    q: Optional[str] = None,
    page: int = 1,
    per_page: int = 12,
) -> dict:
    """
    Returns {"results": [...], "page": int, "total_pages": int,
    "total": int, "has_prev": bool, "has_next": bool}.

    Each result dict: {"content_type": str, "id": int, "title": str,
    "badge_label": str, "created_at": datetime, "url": str}.

    `content_type`: one of "study"/"workshop"/"currents"/"resonance", or
    any other value (including None/"") treated as "no filter" - all four
    types are included.

    `page` and `per_page` are clamped to a minimum of 1 here (not left to
    the caller) - a non-positive `page` would emit a negative SQL OFFSET,
    which Postgres rejects outright, and a non-positive `per_page` would
    divide by zero below.
    """
    page = max(1, page)
    per_page = max(1, per_page)

    types_to_query = [content_type] if content_type in _SELECT_BUILDERS else list(_SELECT_BUILDERS.keys())

    selects = [_SELECT_BUILDERS[t](q) for t in types_to_query]
    combined = selects[0] if len(selects) == 1 else union_all(*selects)
    subquery = combined.subquery()

    total = db.execute(select(func.count()).select_from(subquery)).scalar()

    ordered = (
        select(subquery)
        .order_by(subquery.c.created_at.desc(), subquery.c.content_type, subquery.c.id)
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = db.execute(ordered).all()

    results = []
    for row in rows:
        results.append({
            "content_type": row.content_type,
            "id": row.id,
            "title": _format_title(row.content_type, row.title),
            "badge_label": row.badge_label,
            "created_at": row.created_at,
            "url": f"{DETAIL_URL_PREFIXES[row.content_type]}{row.id}",
        })

    total_pages = (total + per_page - 1) // per_page if total else 0

    return {
        "results": results,
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "has_prev": page > 1,
        "has_next": page < total_pages,
    }
```

Replace with:

```python
def search_library(
    db: Session,
    content_type: Optional[str] = None,
    q: Optional[str] = None,
    theme: Optional[str] = None,
    season: Optional[str] = None,
    source: Optional[str] = None,
    page: int = 1,
    per_page: int = 12,
) -> dict:
    """
    Returns {"results": [...], "page": int, "total_pages": int,
    "total": int, "has_prev": bool, "has_next": bool}.

    Each result dict: {"content_type": str, "id": int, "title": str,
    "badge_label": str, "created_at": datetime, "url": str}.

    `content_type`: one of "study"/"workshop"/"currents"/"resonance", or
    any other value (including None/"") treated as "no filter" - all four
    types are included.

    `theme`: exact match against content_theme (case-sensitive - callers
    should pass an already-lowercased value, since that's how themes are
    stored). `season`/`source`: exact match against the study/workshop
    columns; always return zero rows for currents/resonance, which have
    no season/source concept (see _currents_select/_resonance_select).
    All active filters combine with AND.

    `page` and `per_page` are clamped to a minimum of 1 here (not left to
    the caller) - a non-positive `page` would emit a negative SQL OFFSET,
    which Postgres rejects outright, and a non-positive `per_page` would
    divide by zero below.
    """
    page = max(1, page)
    per_page = max(1, per_page)

    types_to_query = [content_type] if content_type in _SELECT_BUILDERS else list(_SELECT_BUILDERS.keys())

    selects = [_SELECT_BUILDERS[t](q) for t in types_to_query]
    combined = selects[0] if len(selects) == 1 else union_all(*selects)
    subquery = combined.subquery()

    filtered = select(subquery)
    if season:
        filtered = filtered.where(subquery.c.season == season)
    if source:
        filtered = filtered.where(subquery.c.source == source)
    if theme:
        theme_exists = (
            select(ContentTheme.id)
            .where(
                ContentTheme.content_type == subquery.c.content_type,
                ContentTheme.content_id == subquery.c.id,
                ContentTheme.theme == theme,
            )
            .exists()
        )
        filtered = filtered.where(theme_exists)

    total = db.execute(select(func.count()).select_from(filtered.subquery())).scalar()

    ordered = (
        filtered
        .order_by(subquery.c.created_at.desc(), subquery.c.content_type, subquery.c.id)
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = db.execute(ordered).all()

    results = []
    for row in rows:
        results.append({
            "content_type": row.content_type,
            "id": row.id,
            "title": _format_title(row.content_type, row.title),
            "badge_label": row.badge_label,
            "created_at": row.created_at,
            "url": f"{DETAIL_URL_PREFIXES[row.content_type]}{row.id}",
        })

    total_pages = (total + per_page - 1) // per_page if total else 0

    return {
        "results": results,
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "has_prev": page > 1,
        "has_next": page < total_pages,
    }
```

- [ ] **Step 6: Add `get_library_facets()`**

Append to the end of `web/services/library_service.py`:

```python


SEASON_LABELS = {
    "advent": "Advent",
    "christmas": "Christmas",
    "epiphany": "Epiphany",
    "lent": "Lent",
    "holy_week": "Holy Week",
    "easter": "Easter",
    "pentecost": "Pentecost",
    "ordinary_time": "Ordinary Time",
}


def get_library_facets(db: Session) -> dict:
    """
    Returns {"seasons": [{"value": str, "label": str}, ...],
    "sources": [str, ...], "themes": [{"theme": str, "count": int}, ...]}.

    Seasons are ordered by the liturgical calendar (SEASON_LABELS'
    insertion order), not alphabetically. Sources are every distinct
    non-null Study/WorkshopPrep.source value, alphabetical. Themes are
    every distinct content_theme value, most-used first. Facet counts
    are not re-scoped to the currently-active filter selection - see the
    design spec's "not a fully faceted-search experience" note.
    """
    present_seasons = {
        row[0] for row in db.execute(select(Study.season).where(Study.season.isnot(None)).distinct()).all()
    } | {
        row[0] for row in db.execute(select(WorkshopPrep.season).where(WorkshopPrep.season.isnot(None)).distinct()).all()
    }
    seasons = [
        {"value": s, "label": SEASON_LABELS[s]}
        for s in SEASON_LABELS
        if s in present_seasons
    ]

    present_sources = {
        row[0] for row in db.execute(select(Study.source).where(Study.source.isnot(None)).distinct()).all()
    } | {
        row[0] for row in db.execute(select(WorkshopPrep.source).where(WorkshopPrep.source.isnot(None)).distinct()).all()
    }
    sources = sorted(present_sources)

    theme_rows = db.execute(
        select(ContentTheme.theme, func.count().label("count"))
        .group_by(ContentTheme.theme)
        .order_by(func.count().desc())
    ).all()
    themes = [{"theme": row.theme, "count": row.count} for row in theme_rows]

    return {"seasons": seasons, "sources": sources, "themes": themes}
```

- [ ] **Step 7: Run the tests to confirm they pass**

```bash
python3 -m pytest tests/test_library_service.py -v
```

Expected: all PASS.

- [ ] **Step 8: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS, 0 failures.

- [ ] **Step 9: Commit**

```bash
git add web/services/library_service.py tests/test_library_service.py
git commit -m "Add theme/season/source facet filtering to search_library()

search_library() gains theme/season/source parameters (AND-combined
with the existing content_type/q filters). theme filters via an EXISTS
join against content_theme; season/source are plain equality checks
against columns _study_select/_workshop_select now project (NULL for
currents/resonance, so those filters correctly exclude them).

New get_library_facets() returns the distinct season/source/theme
values (with counts, for theme) to populate filter controls."
```

---

### Task 8: `/browse` facet UI

**Files:**
- Modify: `web/app.py` (the `/browse` route)
- Modify: `web/templates/browse.html`
- Modify: `tests/test_route_smoke.py`

**Interfaces:**
- Consumes: `search_library(theme=, season=, source=)` and `get_library_facets(db)` from Task 7.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_route_smoke.py`:

```python
def test_browse_page_with_facet_filters_renders(client):
    response = client.get("/browse?season=lent&source=rcl&theme=hospitality")
    assert response.status_code == 200
    assert "<html" in response.text.lower()
```

- [ ] **Step 2: Run it to confirm it fails**

```bash
python3 -m pytest tests/test_route_smoke.py -v -k facet_filters
```

Expected: FAIL — the `/browse` route doesn't accept `season`/`source`/`theme` query params yet (they're silently ignored by FastAPI today since they're not declared parameters, so this specific test would actually pass today by accident; run it anyway to establish the baseline, then confirm the *filtering itself* takes effect via Task 7's already-passing service tests plus this task's route wiring).

- [ ] **Step 3: Update the `/browse` route**

In `web/app.py`, find:

```python
@app.get("/browse", response_class=HTMLResponse)
async def browse_studies(
    request: Request,
    page: int = 1,
    type: str = None,
    q: str = None,
    db: Session = Depends(get_db)
):
    """
    Library page - unified browse across studies, workshop preps,
    currents analyses, and resonance results
    """
    from .services.library_service import search_library

    search_term = q.strip() if q and q.strip() else None
    result = search_library(db, content_type=type, q=search_term, page=page, per_page=config.studies_per_page)

    return templates.TemplateResponse("browse.html", {
        "request": request,
        "results": result["results"],
        "page": result["page"],
        "total_pages": result["total_pages"],
        "has_prev": result["has_prev"],
        "has_next": result["has_next"],
        "total": result["total"],
        "type_filter": type,
        "search_query": search_term or ""
    })
```

Replace with:

```python
@app.get("/browse", response_class=HTMLResponse)
async def browse_studies(
    request: Request,
    page: int = 1,
    type: str = None,
    q: str = None,
    theme: str = None,
    season: str = None,
    source: str = None,
    db: Session = Depends(get_db)
):
    """
    Library page - unified browse across studies, workshop preps,
    currents analyses, and resonance results, with content_type/theme/
    season/source faceting
    """
    from .services.library_service import search_library, get_library_facets

    search_term = q.strip() if q and q.strip() else None
    result = search_library(
        db, content_type=type, q=search_term, theme=theme, season=season, source=source,
        page=page, per_page=config.studies_per_page,
    )
    facets = get_library_facets(db)

    return templates.TemplateResponse("browse.html", {
        "request": request,
        "results": result["results"],
        "page": result["page"],
        "total_pages": result["total_pages"],
        "has_prev": result["has_prev"],
        "has_next": result["has_next"],
        "total": result["total"],
        "type_filter": type,
        "search_query": search_term or "",
        "theme_filter": theme,
        "season_filter": season,
        "source_filter": source,
        "facets": facets,
    })
```

- [ ] **Step 4: Rewrite the template**

Replace the entire contents of `web/templates/browse.html` with:

```html
{% extends "base.html" %}

{% block title %}Library | Lectionary Engines{% endblock %}

{% block content %}
{% macro filter_url(type=None, theme=None, season=None, source=None, q=None, page=None) %}
{%- set parts = [] -%}
{%- if type %}{% set _ = parts.append('type=' ~ type|urlencode) %}{% endif -%}
{%- if theme %}{% set _ = parts.append('theme=' ~ theme|urlencode) %}{% endif -%}
{%- if season %}{% set _ = parts.append('season=' ~ season|urlencode) %}{% endif -%}
{%- if source %}{% set _ = parts.append('source=' ~ source|urlencode) %}{% endif -%}
{%- if q %}{% set _ = parts.append('q=' ~ q|urlencode) %}{% endif -%}
{%- if page %}{% set _ = parts.append('page=' ~ page|string) %}{% endif -%}
{%- if parts -%}/browse?{{ parts|join('&') }}{%- else -%}/browse{%- endif -%}
{% endmacro %}

<div class="container">
    <div class="page-header">
        <h1>Library</h1>
        <p>{{ total }} result{% if total != 1 %}s{% endif %} total{% if search_query %} matching "{{ search_query }}"{% endif %}</p>
    </div>

    <form class="search-bar" action="/browse" method="get">
        {% if type_filter %}<input type="hidden" name="type" value="{{ type_filter }}">{% endif %}
        {% if theme_filter %}<input type="hidden" name="theme" value="{{ theme_filter }}">{% endif %}
        {% if season_filter %}<input type="hidden" name="season" value="{{ season_filter }}">{% endif %}
        {% if source_filter %}<input type="hidden" name="source" value="{{ source_filter }}">{% endif %}
        <input type="text" name="q" value="{{ search_query }}" placeholder="Search reference or content...">
        <button type="submit" class="btn btn-secondary">Search</button>
        {% if search_query %}
        <a href="{{ filter_url(type=type_filter, theme=theme_filter, season=season_filter, source=source_filter) }}" class="search-clear">Clear</a>
        {% endif %}
    </form>

    <div class="browse-layout">
        <aside class="browse-sidebar">
            <h3>Filter</h3>

            <div class="filter-group">
                <h4>Type</h4>
                <div class="filter-options">
                    <a href="{{ filter_url(theme=theme_filter, season=season_filter, source=source_filter, q=search_query) }}" class="filter-link {% if not type_filter %}active{% endif %}">
                        All
                    </a>
                    <a href="{{ filter_url(type='study', theme=theme_filter, season=season_filter, source=source_filter, q=search_query) }}" class="filter-link {% if type_filter == 'study' %}active{% endif %}">
                        Studies
                    </a>
                    <a href="{{ filter_url(type='workshop', theme=theme_filter, season=season_filter, source=source_filter, q=search_query) }}" class="filter-link {% if type_filter == 'workshop' %}active{% endif %}">
                        Workshop
                    </a>
                    <a href="{{ filter_url(type='currents', theme=theme_filter, season=season_filter, source=source_filter, q=search_query) }}" class="filter-link {% if type_filter == 'currents' %}active{% endif %}">
                        Currents
                    </a>
                    <a href="{{ filter_url(type='resonance', theme=theme_filter, season=season_filter, source=source_filter, q=search_query) }}" class="filter-link {% if type_filter == 'resonance' %}active{% endif %}">
                        Resonance
                    </a>
                </div>
            </div>

            {% if facets.seasons %}
            <div class="filter-group">
                <h4>Season</h4>
                <div class="filter-options">
                    <a href="{{ filter_url(type=type_filter, theme=theme_filter, source=source_filter, q=search_query) }}" class="filter-link {% if not season_filter %}active{% endif %}">
                        All
                    </a>
                    {% for s in facets.seasons %}
                    <a href="{{ filter_url(type=type_filter, theme=theme_filter, season=s.value, source=source_filter, q=search_query) }}" class="filter-link {% if season_filter == s.value %}active{% endif %}">
                        {{ s.label }}
                    </a>
                    {% endfor %}
                </div>
            </div>
            {% endif %}

            {% if facets.sources %}
            <div class="filter-group">
                <h4>Source</h4>
                <div class="filter-options">
                    <a href="{{ filter_url(type=type_filter, theme=theme_filter, season=season_filter, q=search_query) }}" class="filter-link {% if not source_filter %}active{% endif %}">
                        All
                    </a>
                    {% for src in facets.sources %}
                    <a href="{{ filter_url(type=type_filter, theme=theme_filter, season=season_filter, source=src, q=search_query) }}" class="filter-link {% if source_filter == src %}active{% endif %}">
                        {{ src }}
                    </a>
                    {% endfor %}
                </div>
            </div>
            {% endif %}

            {% if facets.themes %}
            <div class="filter-group">
                <h4>Theme</h4>
                <div class="filter-options">
                    <a href="{{ filter_url(type=type_filter, season=season_filter, source=source_filter, q=search_query) }}" class="filter-link {% if not theme_filter %}active{% endif %}">
                        All
                    </a>
                    {% for t in facets.themes %}
                    <a href="{{ filter_url(type=type_filter, theme=t.theme, season=season_filter, source=source_filter, q=search_query) }}" class="filter-link {% if theme_filter == t.theme %}active{% endif %}">
                        {{ t.theme|title }} ({{ t.count }})
                    </a>
                    {% endfor %}
                </div>
            </div>
            {% endif %}
        </aside>

        <div class="browse-main">
            {% if results %}
            <div class="studies-grid">
                {% for item in results %}
                <div class="study-card">
                    <a href="{{ item.url }}" class="study-card-link">
                        <div class="study-card-header">
                            {% if item.content_type == 'study' %}
                            <span class="engine-badge engine-{{ item.badge_label }}">{{ item.badge_label }}</span>
                            {% elif item.content_type == 'workshop' %}
                            <span class="workshop-badge">{{ item.badge_label }}</span>
                            {% elif item.content_type == 'currents' %}
                            <span class="currents-badge">{{ item.badge_label }}</span>
                            {% else %}
                            <span class="resonance-badge">{{ item.badge_label }}</span>
                            {% endif %}
                            <span class="study-card-date">{{ item.created_at.strftime('%b %d, %Y') }}</span>
                        </div>
                        <h3 class="study-card-reference">{{ item.title }}</h3>
                    </a>
                </div>
                {% endfor %}
            </div>

            {% if total_pages > 1 %}
            <div class="pagination">
                {% if has_prev %}
                <a href="{{ filter_url(type=type_filter, theme=theme_filter, season=season_filter, source=source_filter, q=search_query, page=page - 1) }}"
                   class="btn btn-secondary">← Previous</a>
                {% endif %}

                <span class="pagination-info">Page {{ page }} of {{ total_pages }}</span>

                {% if has_next %}
                <a href="{{ filter_url(type=type_filter, theme=theme_filter, season=season_filter, source=source_filter, q=search_query, page=page + 1) }}"
                   class="btn btn-secondary">Next →</a>
                {% endif %}
            </div>
            {% endif %}

            {% else %}
            <div class="empty-state">
                <h2>No results found</h2>
                {% if search_query %}
                <p>Nothing matches "{{ search_query }}". Try a different term, or <a href="{{ filter_url(type=type_filter, theme=theme_filter, season=season_filter, source=source_filter) }}">clear the search</a>.</p>
                {% else %}
                <p>Try adjusting your filters or <a href="/generate">generate a new study</a>.</p>
                {% endif %}
            </div>
            {% endif %}
        </div>
    </div>
</div>
{% endblock %}
```

Every class used (`.filter-group`, `.filter-options`, `.filter-link`, `.search-bar`, `.search-clear`, `.browse-layout`, `.browse-sidebar`, `.browse-main`, `.studies-grid`, `.study-card`, `.pagination`, `.empty-state`, etc.) already exists in `web/static/css/styles.css` and is reused as-is — no new CSS needed.

- [ ] **Step 5: Run the tests to confirm they pass**

```bash
python3 -m pytest tests/test_route_smoke.py -v -k "browse"
```

Expected: all PASS.

- [ ] **Step 6: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS, 0 failures.

- [ ] **Step 7: Verify by eye**

Start the dev server (`uvicorn web.app:app --port 8123`, using the venv at the repo root), sign in, visit `/browse`. Confirm: Season/Source/Theme filter groups appear in the sidebar (only for facets that have at least one value — if your local DB has no faceted content yet, generate one RCL-sourced study first via `/generate` so Season/Source have something to show). Click a few filter links and confirm the URL updates, the active filter highlights, and results narrow correctly; confirm combining two filters (e.g. a season plus a theme) narrows further. If you don't have working browser tooling, curl `/browse?season=<value>` (with an authenticated session cookie) and grep for expected content instead.

- [ ] **Step 8: Commit**

```bash
git add web/app.py web/templates/browse.html tests/test_route_smoke.py
git commit -m "Add theme/season/source facet filter UI to /browse

/browse now surfaces Task 7's get_library_facets() as three new
sidebar filter groups (only shown when at least one value is present),
alongside the existing Type filter and search box. All filters combine
via AND and are reflected in the URL, so filtered views are shareable/
bookmarkable - matching how content_type/q already worked."
```

---

### Task 9: Remove `/currents/browse`

**Files:**
- Modify: `web/routes/currents.py` (remove `browse_currents`)
- Delete: `web/templates/currents_browse.html`
- Modify: `web/templates/currents_result.html` (repoint the "Browse Past" link)
- Modify: `tests/test_route_smoke.py` (remove the `PAGES` entry)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Remove the `PAGES` entry (this makes the removal itself test-verified)**

In `tests/test_route_smoke.py`, find:

```python
PAGES = [
    "/generate",
    "/browse",
    "/workshop",
    "/workshop/browse",
    "/currents",
    "/currents/browse",
    "/resonance",
    "/profiles",
    "/engines",
]
```

Replace with:

```python
PAGES = [
    "/generate",
    "/browse",
    "/workshop",
    "/workshop/browse",
    "/currents",
    "/resonance",
    "/profiles",
    "/engines",
]


def test_currents_browse_no_longer_resolves(client):
    response = client.get("/currents/browse")
    assert response.status_code == 404
```

- [ ] **Step 2: Run it to confirm it fails**

```bash
python3 -m pytest tests/test_route_smoke.py -v -k currents_browse_no_longer_resolves
```

Expected: FAIL — the route still exists and returns 200.

- [ ] **Step 3: Remove the route**

In `web/routes/currents.py`, find and delete this entire function (including its decorator, docstring, and the blank lines immediately around it):

```python
@router.get("/currents/browse")
async def browse_currents(
    request: Request,
    page: int = 1,
    db: Session = Depends(get_db),
):
    """
    Browse past Currents analyses
    """
    per_page = 12
    skip = (page - 1) * per_page

    query = db.query(CurrentsAnalysis).order_by(CurrentsAnalysis.created_at.desc())

    total = query.count()
    analyses = query.offset(skip).limit(per_page).all()

    total_pages = (total + per_page - 1) // per_page

    return templates.TemplateResponse("currents_browse.html", {
        "request": request,
        "analyses": analyses,
        "page": page,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "total": total,
    })
```

- [ ] **Step 4: Delete the template**

```bash
rm web/templates/currents_browse.html
```

- [ ] **Step 5: Repoint the "Browse Past" link**

In `web/templates/currents_result.html`, find:

```html
        <a href="/currents/browse" class="btn btn-secondary">Browse Past</a>
```

Replace with:

```html
        <a href="/browse?type=currents" class="btn btn-secondary">Browse Past</a>
```

- [ ] **Step 6: Run the tests to confirm they pass**

```bash
python3 -m pytest tests/test_route_smoke.py -v
```

Expected: all PASS.

- [ ] **Step 7: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS, 0 failures.

- [ ] **Step 8: Commit**

```bash
git add web/routes/currents.py web/templates/currents_result.html tests/test_route_smoke.py
git rm web/templates/currents_browse.html
git commit -m "Remove /currents/browse in favor of the faceted Library

Per the Tier 4 design spec: Currents/Resonance stop being separate
browse destinations and become content_type facets in the unified
Library (Task 8). The sidebar never linked to this route directly -
its only reachable path was the 'Browse Past' link on a Currents
result page, now repointed to /browse?type=currents. The generation
form at /currents is unchanged."
```

---

### Task 10: Backfill script

**Files:**
- Create: `web/scripts/__init__.py`
- Create: `web/scripts/backfill_content_themes.py`
- Test: `tests/test_backfill_content_themes.py`

**Interfaces:**
- Consumes: `record_content_themes` (Task 2), `extract_themes` (existing).
- Produces: nothing consumed by later tasks — this is the last task in this plan.

- [ ] **Step 1: Write the failing tests**

Create `web/scripts/__init__.py` (empty file):

```bash
touch web/scripts/__init__.py
```

Create `tests/test_backfill_content_themes.py`:

```python
"""
Tests for the one-time content_theme backfill script (Tier 4 -
populates content_theme for rows created before this tier shipped).
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from web.models import Base, ContentTheme, CulturalResonance, CurrentsAnalysis, Study, WorkshopPrep
from web.scripts.backfill_content_themes import (
    backfill_currents,
    backfill_resonance,
    backfill_study,
    backfill_workshop,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


def test_backfill_resonance_parses_existing_themes_json_with_no_claude_calls(db):
    db.add(CulturalResonance(themes='["hospitality", "empire"]', content="c"))
    db.commit()

    count = backfill_resonance(db)

    assert count == 1
    themes = {t.theme for t in db.query(ContentTheme).filter(ContentTheme.content_type == "resonance").all()}
    assert themes == {"hospitality", "empire"}


def test_backfill_resonance_skips_rows_already_backfilled(db):
    db.add(CulturalResonance(themes='["hospitality"]', content="c"))
    db.commit()
    backfill_resonance(db)

    count = backfill_resonance(db)  # second run

    assert count == 0
    assert db.query(ContentTheme).count() == 1


def test_backfill_resonance_skips_non_string_theme_elements_gracefully(db):
    db.add(CulturalResonance(themes="[1, 2, 3]", content="c"))
    db.commit()

    count = backfill_resonance(db)

    assert count == 1
    themes = {t.theme for t in db.query(ContentTheme).all()}
    assert themes == {"1", "2", "3"}


@patch("web.scripts.backfill_content_themes.extract_themes")
def test_backfill_study_calls_extract_themes_once_per_unbackfilled_row(mock_extract_themes, db):
    db.add(Study(engine="threshold", reference="John 3:16", content="c1"))
    db.add(Study(engine="threshold", reference="Luke 14:1", content="c2"))
    db.commit()
    mock_extract_themes.return_value = ["grace"]

    count = backfill_study(db, claude=MagicMock())

    assert count == 2
    assert mock_extract_themes.call_count == 2
    assert db.query(ContentTheme).filter(ContentTheme.content_type == "study").count() == 2


@patch("web.scripts.backfill_content_themes.extract_themes")
def test_backfill_study_is_idempotent(mock_extract_themes, db):
    db.add(Study(engine="threshold", reference="John 3:16", content="c1"))
    db.commit()
    mock_extract_themes.return_value = ["grace"]
    backfill_study(db, claude=MagicMock())

    mock_extract_themes.reset_mock()
    count = backfill_study(db, claude=MagicMock())

    assert count == 0
    assert mock_extract_themes.call_count == 0


@patch("web.scripts.backfill_content_themes.extract_themes")
def test_backfill_workshop_calls_extract_themes_per_unbackfilled_row(mock_extract_themes, db):
    db.add(WorkshopPrep(lens="x", lens_name="X", reference="John 3:16", content="c1"))
    db.commit()
    mock_extract_themes.return_value = ["grace"]

    count = backfill_workshop(db, claude=MagicMock())

    assert count == 1
    assert db.query(ContentTheme).filter(ContentTheme.content_type == "workshop").count() == 1


@patch("web.scripts.backfill_content_themes.extract_themes")
def test_backfill_currents_calls_extract_themes_per_unbackfilled_row(mock_extract_themes, db):
    db.add(CurrentsAnalysis(
        analysis_date="Aug 28, 2026", headline_summary="A Headline",
        content="c1", story_context="story",
    ))
    db.commit()
    mock_extract_themes.return_value = ["justice"]

    count = backfill_currents(db, claude=MagicMock())

    assert count == 1
    assert db.query(ContentTheme).filter(ContentTheme.content_type == "currents").count() == 1
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
python3 -m pytest tests/test_backfill_content_themes.py -v
```

Expected: FAIL — `web.scripts.backfill_content_themes` does not exist yet.

- [ ] **Step 3: Create the script**

Create `web/scripts/backfill_content_themes.py`:

```python
#!/usr/bin/env python3
"""
One-time backfill: populates content_theme for existing Study/
WorkshopPrep/CurrentsAnalysis/CulturalResonance rows created before
Tier 4 shipped.

CulturalResonance rows already have their themes in the existing
`themes` JSON column - backfilled by parsing that, no new Claude calls.
The other three types have no persisted themes yet - backfilled by
calling extract_themes() against their content, the same cheap Haiku
call generation now makes automatically for new rows.

Idempotent: skips any (content_type, content_id) that already has
content_theme rows, so it's safe to re-run.

Run: python3 web/scripts/backfill_content_themes.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lectionary_engines.claude_client import ClaudeClient
from lectionary_engines.theme_extractor import extract_themes
from web.config import WebConfig
from web.database import SessionLocal
from web.models import ContentTheme
from web.models import CulturalResonance, CurrentsAnalysis, Study, WorkshopPrep
from web.services.library_service import record_content_themes


def _already_backfilled(db, content_type: str, content_id: int) -> bool:
    return (
        db.query(ContentTheme)
        .filter(ContentTheme.content_type == content_type, ContentTheme.content_id == content_id)
        .first()
        is not None
    )


def backfill_resonance(db) -> int:
    """No Claude calls - CulturalResonance.themes already has the data."""
    count = 0
    for resonance in db.query(CulturalResonance).all():
        if _already_backfilled(db, "resonance", resonance.id):
            continue
        raw_themes = json.loads(resonance.themes) if resonance.themes else []
        themes = [str(t) for t in raw_themes if isinstance(t, (str, int, float))]
        if themes:
            record_content_themes(db, "resonance", resonance.id, themes)
            count += 1
    db.commit()
    return count


def backfill_study(db, claude: ClaudeClient) -> int:
    count = 0
    for study in db.query(Study).all():
        if _already_backfilled(db, "study", study.id):
            continue
        themes = extract_themes(claude, study.reference, study.content)
        if themes:
            record_content_themes(db, "study", study.id, themes)
            db.commit()
            count += 1
    return count


def backfill_workshop(db, claude: ClaudeClient) -> int:
    count = 0
    for prep in db.query(WorkshopPrep).all():
        if _already_backfilled(db, "workshop", prep.id):
            continue
        themes = extract_themes(claude, prep.reference, prep.content)
        if themes:
            record_content_themes(db, "workshop", prep.id, themes)
            db.commit()
            count += 1
    return count


def backfill_currents(db, claude: ClaudeClient) -> int:
    count = 0
    for analysis in db.query(CurrentsAnalysis).all():
        if _already_backfilled(db, "currents", analysis.id):
            continue
        reference = analysis.headline_summary or "Current Event"
        text = analysis.story_context or analysis.content
        themes = extract_themes(claude, reference, text)
        if themes:
            record_content_themes(db, "currents", analysis.id, themes)
            db.commit()
            count += 1
    return count


def main():
    config = WebConfig.load()
    claude = ClaudeClient(config.anthropic_api_key)
    db = SessionLocal()

    try:
        resonance_count = backfill_resonance(db)
        print(f"Resonance: backfilled {resonance_count} rows (no Claude calls)")

        study_count = backfill_study(db, claude)
        print(f"Study: backfilled {study_count} rows")

        workshop_count = backfill_workshop(db, claude)
        print(f"WorkshopPrep: backfilled {workshop_count} rows")

        currents_count = backfill_currents(db, claude)
        print(f"CurrentsAnalysis: backfilled {currents_count} rows")
    finally:
        db.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
python3 -m pytest tests/test_backfill_content_themes.py -v
```

Expected: all PASS.

- [ ] **Step 5: Run the full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all PASS, 0 failures.

- [ ] **Step 6: Commit**

```bash
git add web/scripts/__init__.py web/scripts/backfill_content_themes.py tests/test_backfill_content_themes.py
git commit -m "Add one-time content_theme backfill script

Populates content_theme for pre-Tier-4 rows: CulturalResonance from
its existing themes JSON column (no new Claude calls), the other three
content types via extract_themes(). Idempotent - safe to re-run,
skipping any content item that already has content_theme rows. Run
manually post-deploy: python3 web/scripts/backfill_content_themes.py"
```

---
