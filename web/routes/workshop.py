"""
Workshop routes - API endpoints for Pastor's Workshop sermon prep tool
"""

from fastapi import APIRouter, Depends, HTTPException, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from typing import Optional
from pathlib import Path

from ..database import get_db
from ..models import WorkshopPrep
from ..config import WebConfig

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lectionary_engines.claude_client import ClaudeClient
from lectionary_engines.engines.workshop import WorkshopEngine
from lectionary_engines.scripture_linker import link_scripture_references
from lectionary_engines.text_fetcher import TextFetcher
from lectionary_engines.protocols import workshop_protocol

router = APIRouter()

# Load configuration
config = WebConfig.load()

# Set up templates
WEB_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))

# Initialize workshop engine (singleton pattern)
_workshop_engine = None
_text_fetcher = None


def get_workshop_engine() -> WorkshopEngine:
    """Get or create workshop engine instance"""
    global _workshop_engine
    if _workshop_engine is None:
        claude = ClaudeClient(config.anthropic_api_key)
        _workshop_engine = WorkshopEngine(claude)
    return _workshop_engine


def get_text_fetcher() -> TextFetcher:
    """Get or create text fetcher instance"""
    global _text_fetcher
    if _text_fetcher is None:
        _text_fetcher = TextFetcher(config.default_translation)
    return _text_fetcher


@router.get("/workshop")
async def workshop_page(request: Request):
    """
    Pastor's Workshop page - choose a lens and generate sermon scaffolding
    """
    return templates.TemplateResponse("workshop.html", {
        "request": request,
        "lenses": workshop_protocol.LENSES,
        "translations": ["NRSVue", "NIV", "CEB", "NLT", "MSG"],
        "default_translation": config.default_translation
    })


@router.post("/workshop/generate")
async def generate_workshop(
    lens: str = Form(...),
    reference: Optional[str] = Form(None),
    text: Optional[str] = Form(None),
    translation: Optional[str] = Form("NRSVue"),
    source: str = Form("paste"),
    rcl_reading: Optional[str] = Form("gospel"),
    moravian_context: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """
    Generate sermon scaffolding using the selected lens

    Form fields:
        - lens: Lens key (e.g., 'apostolic_journalist')
        - reference: Biblical reference (optional for moravian/rcl)
        - text: Biblical text (optional, will fetch if not provided)
        - translation: Bible translation (default: NRSVue)
        - source: Source type ('paste', 'run', 'moravian', 'rcl')
        - rcl_reading: RCL reading type (only for rcl source)

    Returns:
        Redirect to workshop result page
    """
    try:
        engine = get_workshop_engine()
        fetcher = get_text_fetcher()

        # Handle different text sources. fetch_moravian()/fetch_rcl()/fetch()
        # are all blocking network calls - run off the event loop.
        if source == "moravian":
            reference, text = await run_in_threadpool(fetcher.fetch_moravian)
        elif source == "rcl":
            reference, text = await run_in_threadpool(fetcher.fetch_rcl, rcl_reading)
        elif source == "run":
            if not reference:
                raise ValueError("Reference is required for Bible Gateway source")
            text = await run_in_threadpool(fetcher.fetch, reference, translation)
        # For 'paste' source, reference and text come from form

        # Prepend user context/question if provided (applies to all sources)
        if moravian_context and moravian_context.strip():
            source_label = {
                "moravian": "MORAVIAN DAILY TEXT",
                "rcl": "LECTIONARY READING",
                "run": "BIBLICAL TEXT",
                "paste": "BIBLICAL TEXT"
            }.get(source, "BIBLICAL TEXT")
            text = f"USER CONTEXT/QUESTION:\n{moravian_context.strip()}\n\n{'='*60}\n\n{source_label}:\n{text}"

        if not reference:
            raise ValueError("Reference is required")

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

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Workshop generation failed: {str(e)}")


@router.get("/workshop/browse")
async def browse_workshop_preps(
    request: Request,
    page: int = 1,
    lens: str = None,
    db: Session = Depends(get_db)
):
    """
    Browse past workshop preps
    """
    per_page = 10
    skip = (page - 1) * per_page

    query = db.query(WorkshopPrep)

    if lens:
        query = query.filter(WorkshopPrep.lens == lens)

    query = query.order_by(WorkshopPrep.created_at.desc())

    total = query.count()
    preps = query.offset(skip).limit(per_page).all()

    total_pages = (total + per_page - 1) // per_page

    return templates.TemplateResponse("workshop_browse.html", {
        "request": request,
        "preps": preps,
        "lenses": workshop_protocol.LENSES,
        "page": page,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "total": total,
        "lens_filter": lens
    })


@router.get("/workshop/{prep_id}")
async def view_workshop_prep(
    request: Request,
    prep_id: int,
    db: Session = Depends(get_db)
):
    """
    View workshop prep result
    """
    import markdown

    prep = db.query(WorkshopPrep).filter(WorkshopPrep.id == prep_id).first()

    if not prep:
        return templates.TemplateResponse("404.html", {
            "request": request,
            "message": "Workshop prep not found"
        }, status_code=404)

    # Convert markdown to HTML, linking scripture references to Bible Gateway
    linked_content = link_scripture_references(prep.content, prep.translation)
    md = markdown.Markdown(extensions=['extra', 'nl2br', 'sane_lists'])
    content_html = md.convert(linked_content)

    # Get lens info for display
    lens_info = workshop_protocol.LENSES.get(prep.lens, {})

    return templates.TemplateResponse("workshop_result.html", {
        "request": request,
        "prep": prep,
        "content_html": content_html,
        "lens_info": lens_info
    })


@router.get("/api/workshop/lenses")
async def list_lenses():
    """
    Get list of available lenses (API endpoint)
    """
    return {
        "lenses": [
            {
                "key": key,
                "name": lens["name"],
                "tagline": lens["tagline"],
                "description": lens["description"],
                "icon": lens["icon"]
            }
            for key, lens in workshop_protocol.LENSES.items()
        ]
    }
