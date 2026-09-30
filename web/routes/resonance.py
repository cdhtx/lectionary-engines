"""
Cultural Resonance routes - API endpoints for finding cultural connections
"""

import asyncio
import html
import logging
import traceback
from fastapi import APIRouter, Depends, HTTPException, Form, Request
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from typing import Optional, List
from pathlib import Path
import json
import markdown

logger = logging.getLogger(__name__)

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

# How often the stream sends a keep-alive comment while mining runs. Same
# fix as GENERATE_KEEPALIVE_INTERVAL_SECONDS in studies.py (incident
# 2026-08-29): /resonance/find held one silent HTTP response open for the
# entire Claude mining call (which can run well past a minute), so Railway's
# edge proxy was resetting the connection before the response ever arrived -
# the browser showed an error page even though the backend went on to
# finish the call and save the row, which is why the result still showed up
# in the Library. See incident 2026-09-05.
RESONANCE_KEEPALIVE_INTERVAL_SECONDS = 10

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


async def _run_resonance_generation(
    db: Session,
    themes: str,
    era_start: int,
    era_end: int,
    categories: Optional[str],
    mining_mode: Optional[str],
    reference: Optional[str],
    context: Optional[str],
) -> str:
    """
    Does the actual work behind /resonance/find: mines/synthesizes content,
    saves the CulturalResonance row. Returns the redirect path for the new
    resonance (e.g. "/resonance/42") instead of a Response, so the
    /resonance/find route can run this inside a StreamingResponse generator
    (see RESONANCE_KEEPALIVE_INTERVAL_SECONDS above) and turn the return
    value into a client-side redirect once it's done.

    Raises HTTPException on failure - same status/detail as before this was
    split out, the /resonance/find route decides how to surface it since a
    streamed response can't change its HTTP status after the fact.
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

        return f"/resonance/{resonance.id}"

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Resonance search failed: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Resonance search failed: {str(e)}")


@router.post("/resonance/find")
async def find_resonances(
    request: Request,
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

    Streams the response instead of blocking silently for the entire
    mining call (Claude mining regularly runs past a minute): sends a
    loading page immediately, then periodic keep-alive comments while
    _run_resonance_generation() runs, then a client-side redirect once
    it's done. See RESONANCE_KEEPALIVE_INTERVAL_SECONDS above for why.

    Form fields:
        - themes: Comma-separated list of themes
        - era_start: Start year (default 1977)
        - era_end: End year (default 1999)
        - categories: Comma-separated categories or "all"
        - mining_mode: "claude" for direct mining, "api" for old API approach
        - reference: Optional biblical reference for context
        - context: Optional additional context for mining
    """
    async def stream():
        shell = templates.get_template("generating_resonance.html").render({
            "request": request,
        })
        yield shell
        yield " " * 1024  # pad past any proxy's minimum-buffer-before-flush size

        task = asyncio.ensure_future(_run_resonance_generation(
            db=db,
            themes=themes,
            era_start=era_start,
            era_end=era_end,
            categories=categories,
            mining_mode=mining_mode,
            reference=reference,
            context=context,
        ))

        while not task.done():
            # wait(timeout=...) returns as soon as the task finishes, unlike
            # sleep(...) which would always block the full interval even if
            # generation completes in milliseconds (e.g. in tests).
            await asyncio.wait({task}, timeout=RESONANCE_KEEPALIVE_INTERVAL_SECONDS)
            if not task.done():
                yield "<!-- keep-alive -->\n"

        try:
            redirect_path = await task
        except HTTPException as e:
            detail = html.escape(str(e.detail))
            yield f"""
<div class="loading-content">
    <h2>Something went wrong</h2>
    <p>{detail}</p>
    <p><a href="/resonance">&larr; Back to Cultural Resonance</a></p>
</div>
"""
            return

        yield f'<script>window.location.replace({json.dumps(redirect_path)});</script>'

    return StreamingResponse(stream(), media_type="text/html")


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
