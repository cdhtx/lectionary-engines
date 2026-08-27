"""
Currents routes - API endpoints for theological news analysis
"""

from fastapi import APIRouter, Depends, HTTPException, Form, Request
from fastapi.responses import RedirectResponse, JSONResponse
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
from lectionary_engines.scripture_linker import link_scripture_references

router = APIRouter()

# Load configuration
config = WebConfig.load()

# Set up templates
WEB_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))

# Initialize Currents service (singleton)
_currents_service = None


def get_currents_service() -> CurrentsService:
    """Get or create Currents service instance"""
    global _currents_service
    if _currents_service is None:
        _currents_service = CurrentsService(api_key=config.anthropic_api_key)
    return _currents_service


@router.get("/currents")
async def currents_page(request: Request):
    """
    The Currents - theological news analysis form
    """
    return templates.TemplateResponse("currents.html", {
        "request": request,
    })


@router.post("/currents/fetch-headlines")
async def fetch_headlines(
    source: str = Form("npr"),
    limit: int = Form(10),
):
    """
    Fetch headlines from RSS feeds (AJAX endpoint)

    Returns JSON list of headlines for the auto-fetch UI.
    """
    try:
        service = get_currents_service()
        # fetch_headlines() is a blocking `requests` call to an RSS feed -
        # run off the event loop so it can't stall the whole app on a slow
        # or hanging feed.
        headlines = await run_in_threadpool(service.fetch_headlines, source=source, limit=limit)
        return {"headlines": headlines}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch headlines: {str(e)}")


@router.post("/currents/analyze")
async def analyze_story(
    story_context: str = Form(...),
    analysis_date: Optional[str] = Form(None),
    news_source: Optional[str] = Form(""),
    db: Session = Depends(get_db),
):
    """
    Generate a Currents theological analysis

    Form fields:
        - story_context: The news story/event to analyze
        - analysis_date: Date of analysis (defaults to today)
        - news_source: Source attribution

    Returns:
        Redirect to analysis view page
    """
    try:
        service = get_currents_service()

        # analyze_story() is a blocking Claude API call that can take
        # 30-60+ seconds for a full analysis. Running it off the event loop
        # means the single Uvicorn worker can still serve other requests
        # (including this same page reloading) while it's in flight,
        # instead of the whole app appearing to hang.
        result = await run_in_threadpool(
            service.analyze_story,
            news_context=story_context,
            date=analysis_date if analysis_date else None,
            source_info=news_source,
        )

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

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Currents analysis failed: {str(e)}")


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


@router.get("/api/currents")
async def list_currents_api(
    limit: int = 10,
    skip: int = 0,
    db: Session = Depends(get_db),
):
    """
    JSON list of past Currents analyses (used by News Integration quick-select)
    """
    query = db.query(CurrentsAnalysis).order_by(CurrentsAnalysis.created_at.desc())
    total = query.count()
    analyses = query.offset(skip).limit(limit).all()

    return {
        "total": total,
        "analyses": [a.to_dict() for a in analyses],
    }


@router.get("/currents/{analysis_id}")
async def view_currents(
    request: Request,
    analysis_id: int,
    db: Session = Depends(get_db),
):
    """
    View a Currents analysis result
    """
    analysis = db.query(CurrentsAnalysis).filter(
        CurrentsAnalysis.id == analysis_id
    ).first()

    if not analysis:
        return templates.TemplateResponse("404.html", {
            "request": request,
            "message": "Currents analysis not found"
        }, status_code=404)

    # Convert markdown to HTML, linking scripture references to Bible Gateway
    linked_content = link_scripture_references(analysis.content)
    md = markdown.Markdown(extensions=['extra', 'nl2br', 'sane_lists'])
    content_html = md.convert(linked_content)

    return templates.TemplateResponse("currents_result.html", {
        "request": request,
        "analysis": analysis,
        "content_html": content_html,
    })
