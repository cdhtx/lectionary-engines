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

    Clamps/coerces percent to an int in [0, 100] first: this is the one
    place every caller's percent passes through, and Tasks 6/7 now
    interpolate the stored value directly into inline
    `style="width: {{ percent }}%"` HTML on two display surfaces, so an
    out-of-range or non-int value here has a bigger blast radius than it
    used to (see comparison/percent<100-filter issues a bad stored value
    can cause downstream).
    """
    percent = max(0, min(100, int(percent)))

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
