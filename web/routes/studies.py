"""
Study routes - API endpoints for study generation and retrieval
"""

from fastapi import APIRouter, Depends, HTTPException, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
import markdown

from ..database import get_db
from ..models import Study, UserProfile
from ..services.study_generator import StudyGeneratorService
from ..config import WebConfig
from lectionary_engines.preferences import StudyPreferences
import json

router = APIRouter()

# Load configuration
config = WebConfig.load()

# Initialize study generator service (singleton pattern)
_generator_service = None


def get_generator_service() -> StudyGeneratorService:
    """Get or create study generator service instance"""
    global _generator_service
    if _generator_service is None:
        _generator_service = StudyGeneratorService(
            api_key=config.anthropic_api_key,
            default_translation=config.default_translation
        )
    return _generator_service


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
        profile_name = None
        custom_prefs_json = None

        if profile_id:
            # Load profile from database
            profile = db.query(UserProfile).filter(UserProfile.id == profile_id).first()
            if profile:
                profile_name = profile.name
                # Convert profile to StudyPreferences
                preferences = profile.to_study_preferences()

                # Apply custom overrides
                custom_overrides = {}
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

                # Save custom overrides as JSON if any
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

        if not reference:
            raise ValueError("Reference is required")

        # Generate study (this calls Claude API - may take 30-60 seconds)
        # Pass preferences if available
        study_data = generator.generate_study(
            engine_name=engine,
            reference=reference,
            text=text,
            translation=translation,
            source=source,
            preferences=preferences
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
