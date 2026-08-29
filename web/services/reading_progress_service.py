"""
Reading-progress persistence: scroll-based reading progress, shared
across all four Library content types (study/workshop/currents/
resonance) via one table. See
docs/superpowers/specs/2026-08-29-tier-1c-today-chrome-design.md.
"""

from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import update as sa_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from web.models import ReadingProgress


def save_progress(db: Session, user_id: int, content_type: str, content_id: int, percent: int) -> None:
    """
    Upserts a ReadingProgress row. Percent only ever increases - a lower
    value than what's already stored is silently ignored, not an error
    (the caller is a debounced client-side scroll tracker that can post
    out of order, e.g. after scrolling back up).

    The increase check is done as a single atomic conditional UPDATE
    (`WHERE ... AND percent < :new`), not a Python-level read-then-write.
    Two concurrent calls for the same (user_id, content_type, content_id)
    - e.g. two browser tabs open on the same content - can't lose an
    update this way: the database's own WHERE clause is the only thing
    deciding whether a write happens, so there's no window between "read
    the current value" and "write the new one" for a second writer to
    land in.

    Clamps/coerces percent to an int in [0, 100] first: this is the one
    place every caller's percent passes through, and Tasks 6/7 interpolate
    the stored value directly into inline `style="width: {{ percent }}%"`
    HTML on two display surfaces, so an out-of-range or non-int value here
    has a bigger blast radius than it used to.
    """
    percent = max(0, min(100, int(percent)))

    def _try_conditional_update() -> bool:
        result = db.execute(
            sa_update(ReadingProgress)
            .where(
                ReadingProgress.user_id == user_id,
                ReadingProgress.content_type == content_type,
                ReadingProgress.content_id == content_id,
                ReadingProgress.percent < percent,
            )
            .values(percent=percent, updated_at=datetime.utcnow())
        )
        db.commit()
        return result.rowcount > 0

    if _try_conditional_update():
        return

    # The UPDATE matched no row - either no row exists yet for this key,
    # or one exists but already has percent >= what we're trying to save
    # (a correct, race-safe no-op - nothing left to do in that case).
    existing = (
        db.query(ReadingProgress)
        .filter(
            ReadingProgress.user_id == user_id,
            ReadingProgress.content_type == content_type,
            ReadingProgress.content_id == content_id,
        )
        .first()
    )
    if existing is not None:
        return

    try:
        db.add(ReadingProgress(
            user_id=user_id,
            content_type=content_type,
            content_id=content_id,
            percent=percent,
        ))
        db.commit()
    except IntegrityError:
        # Another concurrent request inserted the row first, in the
        # window between our UPDATE attempt and this INSERT - back off
        # and retry as an update against the row that now exists.
        db.rollback()
        _try_conditional_update()


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
