"""
Study routes - API endpoints for study generation and retrieval
"""

from fastapi import APIRouter, Depends, HTTPException, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
import markdown

from ..database import get_db
from ..models import Study
from ..services.study_generator import StudyGeneratorService
from ..config import WebConfig

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
        study_data = generator.generate_study(
            engine_name=engine,
            reference=reference,
            text=text,
            translation=translation,
            source=source
        )

        # Create database record
        study = Study(
            engine=study_data['engine'],
            reference=study_data['reference'],
            content=study_data['content'],
            word_count=study_data.get('metadata', {}).get('word_count'),
            source=source,
            translation=translation,
            biblical_text=study_data.get('biblical_text'),
            reference_normalized=reference.lower().strip()
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
