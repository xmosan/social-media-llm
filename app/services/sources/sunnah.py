import requests
from bs4 import BeautifulSoup
import logging
import hashlib
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from app.models import ContentSource, SourceItem
import time
import random

logger = logging.getLogger(__name__)

SUNNAH_BASE_URL = "https://sunnah.com"
SEARCH_URL = f"{SUNNAH_BASE_URL}/search?q="

def get_or_create_sunnah_source(db: Session):
    source = db.query(ContentSource).filter(ContentSource.type == "sunnah").first()
    if not source:
        source = ContentSource(
            name="Sunnah.com",
            type="sunnah",
            base_url=SUNNAH_BASE_URL
        )
        db.add(source)
        db.commit()
        db.refresh(source)
    return source

def sync_hadith_for_topic(db: Session, topic: str, max_results: int = 10):
    """
    Search sunnah.com for a topic and store results in SourceItem.
    Includes simple rate limiting and caching logic.
    """
    source = get_or_create_sunnah_source(db)
    
    # Simple "caching": check if we've synced this topic recently (e.g. last 1 hour)
    # For now we'll just check if we have results for this topic.
    existing_count = db.query(SourceItem).filter(SourceItem.topic == topic).count()
    if existing_count >= max_results:
        logger.info(f"Using cached hadith for topic: {topic}")
        return
    
    logger.info(f"Syncing hadith for topic: {topic}")
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        # Search request
        response = requests.get(f"{SEARCH_URL}{topic}", headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Consistent wrapper for hadith across search and collections
        records = soup.select(".actualHadithContainer")
        if not records:
            # Fallback for search-specific result containers if structure varies
            records = soup.select(".result_hadith")

        logger.info(f"Found {len(records)} potential records on Sunnah.com")

        count = 0
        for rec in records:
            if count >= max_results:
                break
                
            # Extract text (Narrator + Main Text)
            text_el = rec.select_one(".english_hadith_full") 
            if not text_el:
                # Fallback to inner text container
                text_el = rec.select_one(".hadith_text_inner")
                
            if not text_el:
                continue
            
            hadith_text = text_el.get_text(" ", strip=True)
            
            # Extract reference
            ref_el = rec.select_one(".hadith_reference") or rec.select_one(".hadith_ref_list")
            reference = ref_el.get_text(" ", strip=True) if ref_el else "Unknown Reference"
            
            # Extract URL (usually the collection link)
            link_el = rec.select_one("a[href^='/']")
            hadith_url = f"{SUNNAH_BASE_URL}{link_el['href']}" if link_el else None
            
            # Dedupe via hash
            content_hash = hashlib.md5(hadith_text.encode()).hexdigest()
            
            existing = db.query(SourceItem).filter(SourceItem.hash == content_hash).first()
            if not existing:
                new_item = SourceItem(
                    source_id=source.id,
                    topic=topic,
                    content_text=hadith_text,
                    reference=reference,
                    url=hadith_url,
                    hash=content_hash
                )
                db.add(new_item)
                count += 1
        
        db.commit()
        logger.info(f"Successfully synced {count} NEW hadiths for topic: {topic}")
        
        # Sleep to be respectful
        time.sleep(random.uniform(1, 3))
        
    except Exception as e:
        logger.error(f"Failed to sync hadith from Sunnah.com for topic '{topic}': {e}")
        db.rollback()

def pick_hadith_for_topic(db: Session, topic: str) -> SourceItem | None:
    """
    Pick a hadith for a topic, syncing if necessary.
    """
    # Try to find existing
    item = (
        db.query(SourceItem)
        .filter(SourceItem.topic == topic)
        .order_by(SourceItem.last_used_at.asc().nullsfirst())
        .first()
    )
    
    if not item:
        sync_hadith_for_topic(db, topic, max_results=5)
        item = (
            db.query(SourceItem)
            .filter(SourceItem.topic == topic)
            .order_by(SourceItem.last_used_at.asc().nullsfirst())
            .first()
        )
        
    if item:
        item.last_used_at = datetime.now(timezone.utc)
        db.commit()
        
    return item
