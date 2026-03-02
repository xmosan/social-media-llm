# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from app.models import ContentSource, ContentItem
from app.schemas import ContentItemCreate

def validate_entry_meta(item_type: str, text: str, arabic_text: Optional[str], meta: dict):
    if item_type == "quran":
        if not meta.get("surah_number") or not meta.get("verse_start"):
            raise HTTPException(status_code=400, detail="surah_number and verse_start are required for Quran entries.")
        if not text and not arabic_text:
            raise HTTPException(status_code=400, detail="Arabic text or English translation is required for Quran entries.")
            
    elif item_type == "hadith":
        if not meta.get("collection") or not meta.get("hadith_number"):
            raise HTTPException(status_code=400, detail="collection and hadith_number are required for Hadith entries.")
        if not text and not arabic_text:
            raise HTTPException(status_code=400, detail="Hadith text (Arabic or English) is required.")
            
    elif item_type in ["book", "article"]:
        if not meta.get("title") and not meta.get("url"):
             raise HTTPException(status_code=400, detail="Title or URL is required for books/articles.")
        if not text:
             raise HTTPException(status_code=400, detail="Excerpt text is required for books/articles.")

def generate_topics_slugs(topic: Optional[str], topics: list[str], category: Optional[str] = None) -> list[str]:
    """Generates normalized slugs (lowercase, trimmed, underscores) for matching."""
    slugs = set()
    to_process = []
    if topic: to_process.append(topic)
    if topics: to_process.extend(topics)
    if category: to_process.append(category)
    
    import re
    for text in to_process:
        if not text: continue
        # Lowercase, replace non-alphanumeric with underscore, collapse underscores
        s = text.lower().strip()
        s = re.sub(r'[^a-zA-Z0-9]', '_', s)
        s = re.sub(r'_+', '_', s).strip('_')
        if s: slugs.add(s)
    return list(slugs)

def create_library_entry(db: Session, org_id: Optional[int], data: ContentItemCreate, owner_user_id: Optional[int] = None):
    # 1. Handle Source Creation if needed
    source_id = data.source_id
    if not source_id and data.source_name:
        # Check if source already exists for this org with same name
        existing_source = db.query(ContentSource).filter(
            ContentSource.org_id == org_id,
            func.lower(ContentSource.name) == func.lower(data.source_name)
        ).first()
        
        if existing_source:
            source_id = existing_source.id
        else:
            new_source = ContentSource(
                org_id=org_id,
                name=data.source_name,
                category=data.source_category or "Manual Library",
                source_type="manual_library"
            )
            db.add(new_source)
            db.flush()
            source_id = new_source.id
    
    if not source_id:
        raise HTTPException(status_code=400, detail="Either source_id or source_name is required.")

    # 2. Validate Source Ownership
    source = db.query(ContentSource).filter(ContentSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=400, detail="Invalid source_id")
    
    if source.org_id is not None and source.org_id != org_id:
        raise HTTPException(status_code=403, detail="Access denied to this source")

    # 3. Validate Meta
    validate_entry_meta(data.item_type, data.text, data.arabic_text, data.meta)

    # 4. Generate Slugs
    slugs = generate_topics_slugs(data.topic, data.topics, source.category)

    # 5. Create Item
    item = ContentItem(
        org_id=org_id,
        source_id=source_id,
        owner_user_id=owner_user_id or data.owner_user_id,
        item_type=data.item_type,
        title=data.title,
        text=data.text,
        arabic_text=data.arabic_text,
        translation=data.translation,
        url=data.url,
        meta=data.meta,
        tags=data.tags,
        topic=data.topic,
        topics=data.topics,
        topics_slugs=slugs
    )
    db.add(item)
    db.commit()
    db.refresh(item)
from app.models import ContentSource, ContentItem, LibraryTopicSynonym

def suggest_library_topics(db: Session, text: str, max_results: int = 5):
    """
    Suggests the best matching library topics based on input text.
    Uses layered scoring: Exact Match > Synonym Match > Partial Match.
    """
    if not text:
        return []

    import re
    # Normalize input
    clean_text = text.lower().strip()
    words = set(re.findall(r'\w+', clean_text))
    
    # Get all distinct topics (slugs) from ContentItem
    # In a real app with many topics, we'd cache this or use a search index.
    all_items = db.query(ContentItem.topic, ContentItem.topics_slugs).all()
    unique_topics = {} # slug -> display_name
    for item in all_items:
        if item.topic:
            slug = generate_topics_slugs(item.topic, [])[0]
            unique_topics[slug] = item.topic
        for s in (item.topics_slugs or []):
            if s not in unique_topics:
                unique_topics[s] = s.replace('_', ' ').title()

    # Get synonyms
    synonyms_map = {s.slug: s.synonyms for s in db.query(LibraryTopicSynonym).all()}
    
    suggestions = []
    
    for slug, display in unique_topics.items():
        score = 0.0
        reason = ""
        
        # 1. Exact slug match
        if slug in words:
            score = 1.0
            reason = "exact keyword match"
        
        # 2. Synonym match
        elif any(syn in words for syn in synonyms_map.get(slug, [])):
            score = 0.9
            reason = "synonym match"
            
        # 3. Partial slug match
        elif any(word in slug for word in words if len(word) > 3):
            score = 0.7
            reason = "partial topic match"
            
        # 4. Fuzzy word match (simple containment)
        elif any(slug in word for word in words):
            score = 0.6
            reason = "contextual match"

        if score > 0:
            suggestions.append({
                "topic": display,
                "slug": slug,
                "score": score,
                "reason": reason
            })

    # Sort by score desc
    suggestions.sort(key=lambda x: x['score'], reverse=True)
    return suggestions[:max_results]
