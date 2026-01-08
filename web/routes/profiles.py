"""
Profile routes - API endpoints for user profile management
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel, Field

from ..database import get_db
from ..models import UserProfile

router = APIRouter()


# Pydantic models for request/response validation
class ProfileCreate(BaseModel):
    """Request model for creating a profile"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    study_length: str = Field(default='medium', pattern='^(short|medium|long)$')
    tone_level: int = Field(default=5, ge=0, le=8)
    language_complexity: str = Field(default='standard', pattern='^(accessible|standard|advanced)$')
    focus_areas: Optional[str] = None
    is_default: bool = False


class ProfileUpdate(BaseModel):
    """Request model for updating a profile"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    study_length: Optional[str] = Field(None, pattern='^(short|medium|long)$')
    tone_level: Optional[int] = Field(None, ge=0, le=8)
    language_complexity: Optional[str] = Field(None, pattern='^(accessible|standard|advanced)$')
    focus_areas: Optional[str] = None
    is_default: Optional[bool] = None


@router.get("/api/profiles")
async def list_profiles(db: Session = Depends(get_db)):
    """
    List all user profiles

    Returns:
        List of all profiles as JSON
    """
    profiles = db.query(UserProfile).order_by(
        UserProfile.is_default.desc(),  # Default first
        UserProfile.name.asc()  # Then alphabetical
    ).all()

    return {
        'total': len(profiles),
        'profiles': [profile.to_dict() for profile in profiles]
    }


@router.get("/api/profiles/default")
async def get_default_profile(db: Session = Depends(get_db)):
    """
    Get the default profile

    Returns:
        Default profile as JSON
    """
    profile = db.query(UserProfile).filter(UserProfile.is_default == True).first()

    if not profile:
        raise HTTPException(status_code=404, detail="No default profile found")

    return profile.to_dict()


@router.get("/api/profiles/{profile_id}")
async def get_profile(profile_id: int, db: Session = Depends(get_db)):
    """
    Get a specific profile by ID

    Args:
        profile_id: Profile ID

    Returns:
        Profile data as JSON
    """
    profile = db.query(UserProfile).filter(UserProfile.id == profile_id).first()

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    return profile.to_dict()


@router.post("/api/profiles")
async def create_profile(profile_data: ProfileCreate, db: Session = Depends(get_db)):
    """
    Create a new user profile

    Args:
        profile_data: Profile data from request body

    Returns:
        Created profile as JSON
    """
    # Check if profile name already exists
    existing = db.query(UserProfile).filter(UserProfile.name == profile_data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Profile '{profile_data.name}' already exists")

    # If setting as default, unset any existing default
    if profile_data.is_default:
        db.query(UserProfile).filter(UserProfile.is_default == True).update(
            {'is_default': False}
        )

    # Create new profile
    profile = UserProfile(
        name=profile_data.name,
        description=profile_data.description,
        study_length=profile_data.study_length,
        tone_level=profile_data.tone_level,
        language_complexity=profile_data.language_complexity,
        focus_areas=profile_data.focus_areas,
        is_default=profile_data.is_default,
    )

    db.add(profile)
    db.commit()
    db.refresh(profile)

    return profile.to_dict()


@router.put("/api/profiles/{profile_id}")
async def update_profile(
    profile_id: int,
    profile_data: ProfileUpdate,
    db: Session = Depends(get_db)
):
    """
    Update an existing profile

    Args:
        profile_id: Profile ID
        profile_data: Updated profile data from request body

    Returns:
        Updated profile as JSON
    """
    # Get existing profile
    profile = db.query(UserProfile).filter(UserProfile.id == profile_id).first()

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    # Check if new name conflicts with existing profile
    if profile_data.name and profile_data.name != profile.name:
        existing = db.query(UserProfile).filter(UserProfile.name == profile_data.name).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Profile '{profile_data.name}' already exists")

    # If setting as default, unset any existing default
    if profile_data.is_default:
        db.query(UserProfile).filter(UserProfile.is_default == True).update(
            {'is_default': False}
        )

    # Update fields (only update fields that were provided)
    update_data = profile_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(profile, field, value)

    db.commit()
    db.refresh(profile)

    return profile.to_dict()


@router.delete("/api/profiles/{profile_id}")
async def delete_profile(profile_id: int, db: Session = Depends(get_db)):
    """
    Delete a profile

    Args:
        profile_id: Profile ID

    Returns:
        Success message
    """
    # Get profile
    profile = db.query(UserProfile).filter(UserProfile.id == profile_id).first()

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    # Don't allow deleting the default profile
    if profile.is_default:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete the default profile. Set another profile as default first."
        )

    # Delete profile
    db.delete(profile)
    db.commit()

    return {
        'success': True,
        'message': f"Profile '{profile.name}' deleted successfully"
    }
