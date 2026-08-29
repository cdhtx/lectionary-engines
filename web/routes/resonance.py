"""
Cultural Resonance routes - API endpoints for finding cultural connections
"""

import asyncio
from fastapi import APIRouter, Depends, HTTPException, Form, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from typing import Optional, List
from pathlib import Path
import json
import markdown

from ..database import get_db
from ..models import CulturalResonance, Study, WorkshopPrep
from ..config import WebConfig
from ..services.library_service import record_content_themes
from ..services.pdf_service import render_pdf, slugify

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lectionary_engines.scripture_linker import link_scripture_references

from lectionary_engines.claude_client import ClaudeClient
from lectionary_engines.cultural import ResonanceEngine, WikipediaAdapter, TMDBAdapter

router = APIRouter()

# Load configuration
config = WebConfig.load()

# Set up templates
WEB_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))

# Initialize resonance engine (singleton)
_resonance_engine = None
_claude_client = None


def get_claude_client():
    global _claude_client
    if _claude_client is None:
        _claude_client = ClaudeClient(config.anthropic_api_key)
    return _claude_client


def get_resonance_engine():
    global _resonance_engine
    if _resonance_engine is None:
        _resonance_engine = ResonanceEngine(
            claude_client=get_claude_client(),
            config={"api_key": config.tmdb_api_key} if hasattr(config, 'tmdb_api_key') else {}
        )
    return _resonance_engine


@router.get("/resonance")
async def resonance_page(request: Request):
    """
    Cultural Resonance finder page
    """
    return templates.TemplateResponse("resonance.html", {
        "request": request,
        "categories": ["music", "film", "tv", "news", "all"],
        "default_era_start": 1977,
        "default_era_end": 1999,
    })


@router.post("/resonance/find")
async def find_resonances(
    themes: str = Form(...),
    era_start: int = Form(1977),
    era_end: int = Form(1999),
    categories: Optional[str] = Form("all"),
    mining_mode: Optional[str] = Form("claude"),  # "claude" (new) or "api" (old)
    reference: Optional[str] = Form(""),
    context: Optional[str] = Form(""),
    db: Session = Depends(get_db)
):
    """
    Find cultural resonances for given themes.

    Form fields:
        - themes: Comma-separated list of themes
        - era_start: Start year (default 1977)
        - era_end: End year (default 1999)
        - categories: Comma-separated categories or "all"
        - mining_mode: "claude" for direct mining, "api" for old API approach
        - reference: Optional biblical reference for context
        - context: Optional additional context for mining
    """
    try:
        engine = get_resonance_engine()

        # Parse themes
        theme_list = [t.strip() for t in themes.split(",") if t.strip()]
        if not theme_list:
            raise ValueError("At least one theme is required")

        # Use Claude-first mining (new approach)
        # mine_artifacts()/synthesize_connections() are blocking Claude API
        # calls - run off the event loop so a slow generation can't stall
        # the whole app (find_resonances() is already async/adapter-only).
        if mining_mode == "claude" and engine.claude:
            content = await run_in_threadpool(
                engine.mine_artifacts,
                themes=theme_list,
                reference=reference,
                context=context
            )
            artifacts_found = 10  # Approximate since Claude generates directly
            sources_used = ["Claude Knowledge Base (1977-1999)"]
        else:
            # Fall back to API-based approach
            category_list = None
            if categories and categories != "all":
                category_list = [c.strip() for c in categories.split(",")]

            artifacts = await engine.find_resonances(
                themes=theme_list,
                limit_per_source=10,
                year_start=era_start,
                year_end=era_end,
                categories=category_list
            )

            if engine.claude:
                content = await run_in_threadpool(
                    engine.synthesize_connections,
                    artifacts=artifacts,
                    biblical_themes=theme_list,
                    reference=reference
                )
            else:
                content = engine._format_artifacts_simple(artifacts)

            artifacts_found = len(artifacts)
            sources_used = list(set(a.source_name for a in artifacts))

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

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Resonance search failed: {str(e)}")


@router.get("/resonance/{resonance_id}")
async def view_resonance(
    request: Request,
    resonance_id: int,
    db: Session = Depends(get_db)
):
    """
    View a cultural resonance result
    """
    resonance = db.query(CulturalResonance).filter(CulturalResonance.id == resonance_id).first()

    if not resonance:
        raise HTTPException(status_code=404, detail="Resonance not found")

    # Convert markdown to HTML, linking scripture references to Bible Gateway
    linked_content = link_scripture_references(resonance.content)
    md = markdown.Markdown(extensions=['extra', 'nl2br', 'sane_lists'])
    content_html = md.convert(linked_content)

    # Parse JSON fields
    themes = json.loads(resonance.themes) if resonance.themes else []
    sources = json.loads(resonance.sources_used) if resonance.sources_used else []

    return templates.TemplateResponse("resonance_result.html", {
        "request": request,
        "resonance": resonance,
        "content_html": content_html,
        "themes": themes,
        "sources": sources,
    })


@router.get("/resonance/{resonance_id}/pdf")
async def download_resonance_pdf(
    request: Request,
    resonance_id: int,
    db: Session = Depends(get_db)
):
    """
    Download a cultural resonance result as a PDF
    """
    resonance = db.query(CulturalResonance).filter(CulturalResonance.id == resonance_id).first()

    if not resonance:
        raise HTTPException(status_code=404, detail="Resonance not found")

    linked_content = link_scripture_references(resonance.content)
    md = markdown.Markdown(extensions=['extra', 'nl2br', 'sane_lists'])
    content_html = md.convert(linked_content)

    meta_parts = ["Cultural Resonance", resonance.created_at.strftime('%B %d, %Y')]
    if resonance.artifacts_found:
        meta_parts.append(f"{resonance.artifacts_found} artifacts found")

    pdf_bytes = await run_in_threadpool(
        render_pdf,
        title=resonance.reference or "Cultural Connections",
        meta_line=" · ".join(meta_parts),
        content_html=content_html,
        source_url=str(request.url).replace("/pdf", ""),
    )

    filename = f"{slugify(resonance.reference or 'cultural-resonance')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/resonance/from-study/{study_id}")
async def resonance_from_study(
    study_id: int,
    db: Session = Depends(get_db)
):
    """
    Generate cultural resonances from an existing study.

    Extracts themes from the study and finds matching artifacts.
    """
    study = db.query(Study).filter(Study.id == study_id).first()
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")

    engine = get_resonance_engine()
    claude = get_claude_client()

    # Extract themes from study using Claude
    theme_prompt = f"""Extract 5-7 key theological and thematic keywords from this biblical study.
Return ONLY a comma-separated list of single-word or short-phrase themes.

Study Reference: {study.reference}

Study Content:
{study.content[:3000]}

Return only the comma-separated themes, nothing else."""

    themes_response = claude.generate_study(
        text=theme_prompt,
        reference=study.reference,
        system_prompt="You extract themes from biblical studies. Return only comma-separated keywords.",
        max_tokens=200
    )

    theme_list = [t.strip() for t in themes_response.split(",") if t.strip()]

    # Find resonances
    artifacts = await engine.find_resonances(
        themes=theme_list,
        limit_per_source=10
    )

    # Synthesize
    content = engine.synthesize_connections(
        artifacts=artifacts,
        biblical_themes=theme_list,
        reference=study.reference
    )

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


@router.get("/api/resonance/sources")
async def list_sources():
    """List available cultural sources"""
    engine = get_resonance_engine()
    return {
        "sources": [
            {
                "name": adapter.name,
                "category": adapter.category,
                "era_start": adapter.era_start,
                "era_end": adapter.era_end,
            }
            for adapter in engine.adapters
        ]
    }
