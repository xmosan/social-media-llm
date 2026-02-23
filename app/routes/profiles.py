from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import ContentProfile, Org
from ..schemas import ContentProfileCreate, ContentProfileUpdate, ContentProfileOut
from ..security.rbac import get_current_org_id

router = APIRouter(prefix="/profiles", tags=["profiles"])

# Default presets mapping
PRESETS = {
    "islamic_education": {
        "name": "Islamic Education Starter",
        "niche_category": "religion",
        "focus_description": "Quran, Hadith, spiritual reminders, and Islamic daily life.",
        "content_goals": "Educate and uplift the audience spiritually. Encourage good deeds and mindfulness of Allah.",
        "tone_style": "Respectful, inspiring, and contemplative.",
        "allowed_topics": ["Quran verses", "Prophetic sayings", "Dua", "Salah", "Jumuah"],
        "banned_topics": ["Politics", "Sectarian debates", "Controversial rulings"],
    },
    "fitness_coach": {
        "name": "Fitness Coach Starter",
        "niche_category": "fitness",
        "focus_description": "Workouts, discipline routines, macronutrition, and gym lifestyle.",
        "content_goals": "Inspire the audience to stay disciplined, build muscle, and lead healthy lives. Convert to coaching programs.",
        "tone_style": "Motivational, intense, high-energy, confident.",
        "allowed_topics": ["Lifting form", "Diet tips", "Discipline mindset", "Cardio"],
        "banned_topics": ["Body-shaming", "Fad diets", "Overtraining"],
    },
    "real_estate": {
        "name": "Real Estate Starter",
        "niche_category": "real_estate",
        "focus_description": "Local market insights, modern property listings, investment tips, and buyer/seller guidance.",
        "content_goals": "Generate seller leads, display market authority, and attract local home buyers.",
        "tone_style": "Professional, trustworthy, knowledgeable, upscale.",
        "allowed_topics": ["Mortgage rates", "Home staging", "Neighborhood tours", "Closing process"],
        "banned_topics": ["Market crash fearmongering", "Unrealistic promises"],
    },
    "small_business": {
        "name": "Small Business Brand Starter",
        "niche_category": "ecommerce",
        "focus_description": "Product highlights, behind-the-scenes packing orders, customer testimonials, and brand story.",
        "content_goals": "Build brand awareness, increase website traffic, and drive product sales. Build trust.",
        "tone_style": "Friendly, approachable, enthusiastic, relatable.",
        "allowed_topics": ["Product drops", "Small business struggles", "Quality control", "Customer unboxing"],
        "banned_topics": ["Complaining about competitors", "Politics"],
    },
    "personal_branding": {
        "name": "Personal Branding Starter",
        "niche_category": "creator",
        "focus_description": "Personal storytelling, day-in-the-life thoughts, professional advice in my industry.",
        "content_goals": "Drive deep engagement, build a loyal community, and establish thought leadership.",
        "tone_style": "Authentic, raw, conversational, thought-provoking.",
        "allowed_topics": ["Lessons learned", "Daily habits", "Industry takes", "Vulnerability"],
        "banned_topics": ["Oversharing private specifics"],
    }
}

@router.get("", response_model=list[ContentProfileOut])
def get_profiles(
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id),
):
    """List all content profiles for the org."""
    return db.query(ContentProfile).filter(ContentProfile.org_id == org_id).all()

@router.post("", response_model=ContentProfileOut)
def create_profile(
    payload: ContentProfileCreate,
    preset: str | None = None,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id),
):
    """Create a new ContentProfile, optionally prefilling with a built-in preset."""
    data = payload.dict(exclude_unset=True)
    
    # Override with starter template if requested
    if preset and preset in PRESETS:
        preset_data = PRESETS[preset]
        for key, val in preset_data.items():
            if key not in data or not data[key]: # Only override if user didn't explicitly set it or left it empty
                data[key] = val

    profile = ContentProfile(org_id=org_id, **data)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile

@router.get("/{profile_id}", response_model=ContentProfileOut)
def get_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id),
):
    profile = db.query(ContentProfile).filter(ContentProfile.id == profile_id, ContentProfile.org_id == org_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Content profile not found")
    return profile

@router.patch("/{profile_id}", response_model=ContentProfileOut)
def update_profile(
    profile_id: int,
    payload: ContentProfileUpdate,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id),
):
    profile = db.query(ContentProfile).filter(ContentProfile.id == profile_id, ContentProfile.org_id == org_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Content profile not found")

    data = payload.dict(exclude_unset=True)
    for k, v in data.items():
        setattr(profile, k, v)
        
    db.commit()
    db.refresh(profile)
    return profile

@router.delete("/{profile_id}")
def delete_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id),
):
    profile = db.query(ContentProfile).filter(ContentProfile.id == profile_id, ContentProfile.org_id == org_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Content profile not found")
        
    db.delete(profile)
    db.commit()
    return {"ok": True}
