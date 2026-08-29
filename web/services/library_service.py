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
from typing import List, Optional

from sqlalchemy import String, cast, func, literal, null, or_, select, union_all
from sqlalchemy.orm import Session

from web.models import ContentTheme, CulturalResonance, CurrentsAnalysis, Study, WorkshopPrep

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
