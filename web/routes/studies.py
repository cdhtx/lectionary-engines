"""
Study routes - API endpoints for study generation and retrieval
"""

from fastapi import APIRouter, Depends, HTTPException, Form, Request
from fastapi.responses import RedirectResponse
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

router = APIRouter()

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


@router.post("/generate")
async def generate_study(
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
    Generate a new study and save to database

    Form fields:
        - engine: Engine name ('threshold', 'palimpsest', 'collision')
        - reference: Biblical reference (optional for moravian/rcl)
        - text: Biblical text (optional, will fetch if not provided)
        - translation: Bible translation (default: NRSVue)
        - source: Source type ('paste', 'run', 'moravian', 'rcl')
        - rcl_reading: RCL reading type (only for rcl source)

    Returns:
        Redirect to study view page
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

        # Handle different text sources
        if source == "moravian":
            # Fetch Moravian Daily Text
            reference, text = generator.fetch_moravian()
        elif source == "rcl":
            # Fetch RCL reading
            reference, text = generator.fetch_rcl(reading_type=rcl_reading, translation=translation)
        elif source == "run":
            # Fetch from Bible Gateway (reference required)
            if not reference:
                raise ValueError("Reference is required for Bible Gateway source")
            text = generator.fetch_text(reference, translation)
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

        # Shared theme extraction - one cheap call feeds both auto news
        # integration and cultural grounding below, if either is needed.
        passage_themes = None
        needs_auto_news = (
            not resolved_news_context and profile is not None and profile.auto_news_integration
        )
        needs_grounding = preferences is not None and preferences.cultural_artifacts_level > 0
        if needs_auto_news or needs_grounding:
            passage_themes = extract_themes(generator.claude, reference, text)

        # Auto news integration: pick a real, currently-fetched headline
        # instead of requiring the user to browse and paste one manually.
        if needs_auto_news and passage_themes:
            try:
                auto_headline = get_currents_service().auto_select_headline(passage_themes)
            except Exception as auto_news_error:
                logger.warning(f"Auto news integration skipped: {auto_news_error}")
                auto_headline = None
            if auto_headline:
                resolved_news_context = auto_headline["news_context"]
                resolved_news_date = auto_headline["news_date"]

        # Cultural grounding: ground the intensity-scaled cultural-artifacts
        # instruction (see protocol_builder.py) in real Wikipedia/TMDB
        # artifacts instead of leaving it entirely to Claude's recall.
        cultural_grounding_block = None
        if needs_grounding and passage_themes:
            cultural_grounding_block = await build_grounding_for_passage(
                claude=generator.claude,
                reference=reference,
                text=text,
                tmdb_api_key=config.tmdb_api_key if hasattr(config, "tmdb_api_key") else None,
            )

        # Generate study (this calls Claude API - may take 30-60 seconds)
        # Pass preferences if available
        study_data = generator.generate_study(
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
                validation_result = generator.validate_study(
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

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Study generation failed: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Study generation failed: {str(e)}")


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
