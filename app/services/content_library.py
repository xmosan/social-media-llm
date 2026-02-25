import random
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select, and_, not_, or_
from sqlalchemy.orm import Session
from app.models import ContentItem, ContentUsage

def normalize_topic(topic: str) -> str:
    """Lowercase, strip, and replace spaces with underscores."""
    if not topic:
        return ""
    return topic.strip().lower().replace(" ", "_")

def pick_content_item(
    db: Session, 
    org_id: int, 
    topic: str, 
    content_type: str | None = None,
    avoid_repeat_days: int = 30,
    automation_id: int | None = None,
    ig_account_id: int | None = None
) -> ContentItem | None:
    """
    Selects a ContentItem by topic while avoiding items used recently.
    """
    norm_topic = normalize_topic(topic)
    
    # 1. Base query for items belonging to this org
    # Using JSON column for topics; check if the normalized topic is in the list.
    query = db.query(ContentItem).filter(
        ContentItem.org_id == org_id
    )
    
    # Filter by topic: iterate and check if norm_topic is in the list
    from sqlalchemy.types import String
    from sqlalchemy import cast
    # Cast the JSON column to String so LIKE works universally
    query = query.filter(cast(ContentItem.topics, String).like(f'%"{norm_topic}"%'))
        
    if content_type:
        query = query.filter(ContentItem.type == content_type)
        
    # 2. Exclude recently used items
    repeat_cutoff = datetime.now(timezone.utc) - timedelta(days=avoid_repeat_days)
    
    # Subquery for recently used content item IDs
    used_subquery = db.query(ContentUsage.content_item_id).filter(
        ContentUsage.org_id == org_id,
        ContentUsage.used_at >= repeat_cutoff
    )
    
    # Optionally filter "recent" by account or automation if we want to be less strict
    # but the requirement says "avoid repeats" generally for the org/flow.
    
    query = query.filter(not_(ContentItem.id.in_(used_subquery)))
    
    # 3. Random selection
    # order_by(func.random()) works for both Postgres and SQLite
    item = query.order_by(func.random()).first()
    
    if not item:
        # Secondary fallback: if no unused item, pick the least recently used one?
        # For now, let's stick to the requirement: return None if none found.
        print(f"[DEBUG] No available content found for topic '{topic}' in org {org_id}")
        return None
        
    return item
