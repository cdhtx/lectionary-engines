"""
Study routes - API endpoints for study generation and retrieval
"""

import asyncio
import html
from datetime import date
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Form, Request
from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates
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

router = APIRouter()

WEB_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))

# Matches the estimates already shown client-side in generate.html's
# engine-selection JS - kept in sync manually, there are only three.
ENGINE_TIME_ESTIMATES = {
    "threshold": "30-60 seconds",
    "palimpsest": "60-90 seconds",
    "collision": "90-120 seconds",
}

# How often the stream sends a keep-alive comment while generation runs.
# Purely to keep bytes flowing so no idle-timeout along the network path
# (Railway's edge, a corporate proxy, a home router's NAT table) decides
# the connection is dead and resets it out from under a 90-120 second
# Collision generation - see incident 2026-08-29: Collision requests were
# getting ERR_CONNECTION_CLOSED because /generate held one silent HTTP
# response open for the entire generation with no bytes sent until the
# very end.
GENERATE_KEEPALIVE_INTERVAL_SECONDS = 10

# Load configuration
config = WebConfig.load()

# Initialize study generator service (singleton pattern)
_generator_service = None
_currents_service = None


def get_generator_service() -> StudyGeneratorService:
    """Get or create study generator service instance"""
    global _generator_service
    if _generator_service is None:
        _generator_service = StudyGeneratorService(
            api_key=config.anthropic_api_key,
            default_translation=config.default_translation
        )
    return _generator_service


def get_currents_service() -> CurrentsService:
    """Get or create Currents service instance (used for auto news integration)"""
    global _currents_service
    if _currents_service is None:
        _currents_service = CurrentsService(api_key=config.anthropic_api_key)
    return _currents_service


async def _run_study_generation(
    db: Session,
    engine: str,
    reference: Optional[str],
    text: Optional[str],
    translation: Optional[str],
    source: str,
    rcl_reading: Optional[str],
    profile_id: Optional[int],
    custom_study_length: Optional[str],
    custom_tone_level: Optional[int],
    custom_language_complexity: Optional[str],
    custom_focus_areas: Optional[str],
    custom_cultural_artifacts_level: Optional[int],
    moravian_context: Optional[str],
    integrate_news: Optional[str],
    news_date: Optional[str],
    news_context: Optional[str],
    currents_id: Optional[int],
    run_validation: Optional[str],
) -> str:
    """
    Does the actual work behind /generate: builds preferences, fetches
    text, calls the engine, saves the Study row. Returns the redirect
    path for the new study (e.g. "/study/42") instead of a Response, so
    the /generate route can run this inside a StreamingResponse generator
    (see GENERATE_KEEPALIVE_INTERVAL_SECONDS above) and turn the return
    value into a client-side redirect once it's done.

    Raises HTTPException on failure - same status/detail as before this
    was split out, the /generate route decides how to surface it since a
    streamed response can't change its HTTP status after the fact.
    """
    try:
        # Get generator service
        generator = get_generator_service()

        # Build preferences from profile and custom overrides
        preferences = None
        profile = None
        profile_name = None
        custom_prefs_json = None

        if profile_id:
            # Load profile from database
            profile = db.query(UserProfile).filter(UserProfile.id == profile_id).first()
            if profile:
                profile_name = profile.name
                preferences = profile.to_study_preferences()

        # Apply custom overrides — works with or without a profile
        # If no profile, start from defaults so sliders still take effect
        custom_overrides = {}
        if custom_study_length or (custom_tone_level is not None and custom_tone_level >= 0) or \
                custom_language_complexity or custom_focus_areas or \
                (custom_cultural_artifacts_level is not None and custom_cultural_artifacts_level > 0):
            if preferences is None:
                from lectionary_engines.preferences import DEFAULT_PREFERENCES, StudyPreferences
                preferences = StudyPreferences(
                    study_length=DEFAULT_PREFERENCES.study_length,
                    tone_level=DEFAULT_PREFERENCES.tone_level,
                    language_complexity=DEFAULT_PREFERENCES.language_complexity,
                    focus_areas=DEFAULT_PREFERENCES.focus_areas,
                    cultural_artifacts_level=DEFAULT_PREFERENCES.cultural_artifacts_level,
                )
            if custom_study_length:
                preferences.study_length = custom_study_length
                custom_overrides['study_length'] = custom_study_length
            if custom_tone_level is not None and custom_tone_level >= 0:
                preferences.tone_level = custom_tone_level
                custom_overrides['tone_level'] = custom_tone_level
            if custom_language_complexity:
                preferences.language_complexity = custom_language_complexity
                custom_overrides['language_complexity'] = custom_language_complexity
            if custom_focus_areas:
                preferences.focus_areas = custom_focus_areas
                custom_overrides['focus_areas'] = custom_focus_areas
            if custom_cultural_artifacts_level is not None and custom_cultural_artifacts_level > 0:
                preferences.cultural_artifacts_level = custom_cultural_artifacts_level
                custom_overrides['cultural_artifacts_level'] = custom_cultural_artifacts_level

        if custom_overrides:
            custom_prefs_json = json.dumps(custom_overrides)

        # Handle different text sources. These are all blocking network
        # calls - run off the event loop.
        #
        # Temporary diagnostic (2026-09-05): a "Reference is required" report
        # came through with the Moravian tab reportedly selected, which
        # should be structurally impossible via this branch - fetch_moravian()
        # can't return a falsy reference without raising first. Logging the
        # raw source value to catch a mismatch (whitespace/case/wrong field
        # name) that's silently falling through to the no-op 'paste' branch.
        logger.info(f"_run_study_generation: source={source!r} engine={engine!r} reference={reference!r}")
        if source == "moravian":
            # Fetch Moravian Daily Text
            reference, text = await run_in_threadpool(generator.fetch_moravian)
        elif source == "rcl":
            # Fetch RCL reading
            reference, text = await run_in_threadpool(
                generator.fetch_rcl, reading_type=rcl_reading, translation=translation
            )
        elif source == "run":
            # Fetch from Bible Gateway (reference required)
            if not reference:
                raise ValueError("Reference is required for Bible Gateway source")
            text = await run_in_threadpool(generator.fetch_text, reference, translation)
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

        # Resolve news context if news integration is enabled
        resolved_news_context = None
        resolved_news_date = None
        if integrate_news:
            if currents_id:
                # Load context from a past Currents analysis
                from ..models import CurrentsAnalysis
                currents = db.query(CurrentsAnalysis).filter(CurrentsAnalysis.id == currents_id).first()
                if currents:
                    resolved_news_context = currents.story_context or currents.headline_summary
                    resolved_news_date = currents.analysis_date
            if not resolved_news_context and news_context and news_context.strip():
                resolved_news_context = news_context.strip()
                resolved_news_date = news_date or ""

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

        # Auto news integration: pick a real, currently-fetched headline
        # instead of requiring the user to browse and paste one manually.
        if needs_auto_news and passage_themes:
            try:
                # Blocking: fetches RSS headlines + a Claude call to pick one.
                auto_headline = await run_in_threadpool(
                    get_currents_service().auto_select_headline, passage_themes
                )
            except Exception as auto_news_error:
                logger.warning(f"Auto news integration skipped: {auto_news_error}")
                auto_headline = None
            if auto_headline:
                resolved_news_context = auto_headline["news_context"]
                resolved_news_date = auto_headline["news_date"]

        # Cultural grounding: ground the intensity-scaled cultural-artifacts
        # instruction (see protocol_builder.py) in real Wikipedia/TMDB
        # artifacts instead of leaving it entirely to Claude's recall.
        # Reuses passage_themes from above rather than re-extracting.
        cultural_grounding_block = None
        if needs_grounding and passage_themes:
            cultural_grounding_block = await build_grounding_for_passage(
                themes=passage_themes,
                tmdb_api_key=config.tmdb_api_key if hasattr(config, "tmdb_api_key") else None,
            )

        # Generate study (this calls Claude API - may take 30-60 seconds).
        # Blocking call - run off the event loop so the single Uvicorn
        # worker can still serve other requests while it's in flight,
        # instead of the whole app appearing to hang (see incident
        # 2026-08-27: a stalled Currents analysis stacked up abandoned
        # blocking requests and made the app unresponsive).
        study_data = await run_in_threadpool(
            generator.generate_study,
            engine_name=engine,
            reference=reference,
            text=text,
            translation=translation,
            source=source,
            preferences=preferences,
            news_context=resolved_news_context,
            news_date=resolved_news_date,
            cultural_grounding_block=cultural_grounding_block,
        )

        # Run validation pass (if enabled)
        validation_score = None
        validation_recommendation = None
        validation_data_json = None

        should_validate = run_validation and run_validation.lower() == "true"
        if should_validate:
            try:
                # Also a blocking Claude call - run off the event loop.
                validation_result = await run_in_threadpool(
                    generator.validate_study,
                    biblical_text=study_data.get('biblical_text', text),
                    reference=reference,
                    study_content=study_data['content']
                )
                validation_score = validation_result.overall_score
                validation_recommendation = validation_result.recommendation
                validation_data_json = json.dumps(validation_result.to_dict())
            except Exception as validation_error:
                # Log but don't fail - validation is non-critical
                print(f"Validation failed (non-critical): {validation_error}")
                validation_recommendation = "skipped"

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

        return f"/study/{study.id}"

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Study generation failed: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Study generation failed: {str(e)}")


@router.post("/generate")
async def generate_study(
    request: Request,
    engine: str = Form(...),
    reference: Optional[str] = Form(None),
    text: Optional[str] = Form(None),
    translation: Optional[str] = Form("NRSVue"),
    source: str = Form("paste"),
    rcl_reading: Optional[str] = Form("gospel"),
    profile_id: Optional[int] = Form(None),
    custom_study_length: Optional[str] = Form(None),
    custom_tone_level: Optional[int] = Form(None),
    custom_language_complexity: Optional[str] = Form(None),
    custom_focus_areas: Optional[str] = Form(None),
    custom_cultural_artifacts_level: Optional[int] = Form(None),
    moravian_context: Optional[str] = Form(None),
    integrate_news: Optional[str] = Form(None),
    news_date: Optional[str] = Form(None),
    news_context: Optional[str] = Form(None),
    currents_id: Optional[int] = Form(None),
    run_validation: Optional[str] = Form("true"),  # "true" or "false"
    db: Session = Depends(get_db)
):
    """
    Generate a new study and save to database.

    Streams the response instead of blocking silently for the entire
    generation (up to ~120 seconds for Collision): sends a loading page
    immediately, then periodic keep-alive comments while
    _run_study_generation() runs, then a client-side redirect once it's
    done. See GENERATE_KEEPALIVE_INTERVAL_SECONDS above for why.

    Form fields:
        - engine: Engine name ('threshold', 'palimpsest', 'collision')
        - reference: Biblical reference (optional for moravian/rcl)
        - text: Biblical text (optional, will fetch if not provided)
        - translation: Bible translation (default: NRSVue)
        - source: Source type ('paste', 'run', 'moravian', 'rcl')
        - rcl_reading: RCL reading type (only for rcl source)
    """
    async def stream():
        shell = templates.get_template("generating.html").render({
            "request": request,
            "engine_label": engine.title() if engine else "study",
            "time_estimate": ENGINE_TIME_ESTIMATES.get(engine, "a minute or two"),
        })
        yield shell
        yield " " * 1024  # pad past any proxy's minimum-buffer-before-flush size

        task = asyncio.ensure_future(_run_study_generation(
            db=db,
            engine=engine,
            reference=reference,
            text=text,
            translation=translation,
            source=source,
            rcl_reading=rcl_reading,
            profile_id=profile_id,
            custom_study_length=custom_study_length,
            custom_tone_level=custom_tone_level,
            custom_language_complexity=custom_language_complexity,
            custom_focus_areas=custom_focus_areas,
            custom_cultural_artifacts_level=custom_cultural_artifacts_level,
            moravian_context=moravian_context,
            integrate_news=integrate_news,
            news_date=news_date,
            news_context=news_context,
            currents_id=currents_id,
            run_validation=run_validation,
        ))

        while not task.done():
            # wait(timeout=...) returns as soon as the task finishes, unlike
            # sleep(...) which would always block the full interval even if
            # generation completes in milliseconds (e.g. in tests, or a
            # fast Threshold study).
            await asyncio.wait({task}, timeout=GENERATE_KEEPALIVE_INTERVAL_SECONDS)
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
    <p><a href="/generate">&larr; Back to Workbench</a></p>
</div>
"""
            return

        yield f'<script>window.location.replace({json.dumps(redirect_path)});</script>'

    return StreamingResponse(stream(), media_type="text/html")


@router.get("/api/studies/{study_id}")
async def get_study_api(study_id: int, db: Session = Depends(get_db)):
    """
    Get study by ID (API endpoint - returns JSON)

    Args:
        study_id: Study ID

    Returns:
        Study data as JSON
    """
    study = db.query(Study).filter(Study.id == study_id).first()

    if not study:
        raise HTTPException(status_code=404, detail="Study not found")

    return study.to_dict()


@router.get("/api/studies")
async def list_studies_api(
    skip: int = 0,
    limit: int = 20,
    engine: Optional[str] = None,
    source: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    List studies with optional filtering (API endpoint - returns JSON)

    Query parameters:
        - skip: Number of studies to skip (for pagination)
        - limit: Maximum number of studies to return
        - engine: Filter by engine name
        - source: Filter by source type

    Returns:
        List of studies as JSON
    """
    query = db.query(Study)

    # Apply filters
    if engine:
        query = query.filter(Study.engine == engine)
    if source:
        query = query.filter(Study.source == source)

    # Order by most recent first
    query = query.order_by(Study.created_at.desc())

    # Get total count before pagination
    total = query.count()

    # Apply pagination
    studies = query.offset(skip).limit(limit).all()

    return {
        'total': total,
        'skip': skip,
        'limit': limit,
        'studies': [study.to_dict() for study in studies]
    }
