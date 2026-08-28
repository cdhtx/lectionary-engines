"""
Unified Library query: spans Study, WorkshopPrep, CurrentsAnalysis, and
CulturalResonance in one paginated, chronologically-ordered result set.

Each content type is projected into a common shape (id, content_type,
title, badge_label, created_at) via a SQLAlchemy select(), then combined
with union_all() and paginated over the *combined* result - not fetched
and paginated separately per type and then merged, which would produce
incorrect page boundaries whenever results span more than one type.
"""

import json
from typing import Optional

from sqlalchemy import String, cast, func, literal, or_, select, union_all
from sqlalchemy.orm import Session

from web.models import CulturalResonance, CurrentsAnalysis, Study, WorkshopPrep

DETAIL_URL_PREFIXES = {
    "study": "/study/",
    "workshop": "/workshop/",
    "currents": "/currents/",
    "resonance": "/resonance/",
}


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


_SELECT_BUILDERS = {
    "study": _study_select,
    "workshop": _workshop_select,
    "currents": _currents_select,
    "resonance": _resonance_select,
}


def _format_title(content_type: str, raw_title: str) -> str:
    """
    Resonance rows with no `reference` fall back to their raw `themes`
    JSON string (e.g. '["hospitality", "empire"]') at the SQL level -
    parse and join it into a readable string here. Any other type, or a
    resonance row that already has a real reference, passes through
    unchanged.
    """
    if content_type != "resonance" or not raw_title.startswith("["):
        return raw_title
    try:
        themes = json.loads(raw_title)
        return ", ".join(t.title() for t in themes) if themes else raw_title
    except (json.JSONDecodeError, TypeError, AttributeError):
        return raw_title


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
    """
    types_to_query = [content_type] if content_type in _SELECT_BUILDERS else list(_SELECT_BUILDERS.keys())

    selects = [_SELECT_BUILDERS[t](q) for t in types_to_query]
    combined = selects[0] if len(selects) == 1 else union_all(*selects)
    subquery = combined.subquery()

    total = db.execute(select(func.count()).select_from(subquery)).scalar()

    ordered = (
        select(subquery)
        .order_by(subquery.c.created_at.desc())
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
