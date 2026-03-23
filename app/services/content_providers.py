from abc import ABC, abstractmethod
from typing import List, Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_
import random

from app.models import ContentItem

class UnifiedContent(BaseModel):
    type: str  # "hadith" | "quote" | "verse" | "note"
    text: str
    arabic_text: Optional[str] = None
    source: str
    reference: str
    topic_tags: List[str]
    verified: bool
    provider: str
    original_id: Optional[str] = None

class BaseContentProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the provider (e.g., 'system_library')"""
        pass

    @property
    @abstractmethod
    def provider_type(self) -> str:
        """Type of provider (system, user, external)"""
        pass

    @abstractmethod
    def get_content(self, db: Session, org_id: int, topic: str, limit: int = 1) -> List[UnifiedContent]:
        """Fetch content matching the topic"""
        pass


class SystemLibraryProvider(BaseContentProvider):
    @property
    def provider_name(self) -> str:
        return "system_library"

    @property
    def provider_type(self) -> str:
        return "system"

    def get_content(self, db: Session, org_id: int, topic: str, limit: int = 1) -> List[UnifiedContent]:
        """Fetch from global system default packs where org_id is NULL"""
        norm_topic = topic.lower().strip()
        
        # We query items with NO org_id (system wide)
        query = db.query(ContentItem).filter(ContentItem.org_id == None)
        items = query.all()
        
        match_pool = []
        for item in items:
            item_topics = [t.lower() for t in (item.topics or [])]
            item_text = (item.text or "").lower()
            item_meta = item.meta or {}
            
            # Simple keyword matching
            if norm_topic in item_topics or norm_topic in item_text:
                match_pool.append(item)
                
        if not match_pool:
            return []
            
        selected = random.sample(match_pool, min(limit, len(match_pool)))
        
        results = []
        for s in selected:
            meta = s.meta or {}
            ref = meta.get("reference_display") or s.title or "Unknown Reference"
            source_name = meta.get("hadith_collection") or s.title or "System Library"
            
            results.append(UnifiedContent(
                type=s.item_type or "note",
                text=s.text,
                arabic_text=s.arabic_text,
                source=source_name,
                reference=ref,
                topic_tags=s.topics or [],
                verified=True, # System library is verified by definition
                provider=self.provider_name,
                original_id=str(s.id)
            ))
            
        return results


class UserLibraryProvider(BaseContentProvider):
    @property
    def provider_name(self) -> str:
        return "user_library"

    @property
    def provider_type(self) -> str:
        return "user"

    def get_content(self, db: Session, org_id: int, topic: str, limit: int = 1) -> List[UnifiedContent]:
        """Fetch from user's specific organization library"""
        norm_topic = topic.lower().strip()
        
        query = db.query(ContentItem).filter(ContentItem.org_id == org_id)
        items = query.all()
        
        match_pool = []
        for item in items:
            item_topics = [t.lower() for t in (item.topics or [])]
            item_text = (item.text or "").lower()
            
            if norm_topic in item_topics or norm_topic in item_text:
                match_pool.append(item)
                
        if not match_pool:
            return []
            
        selected = random.sample(match_pool, min(limit, len(match_pool)))
        
        results = []
        for s in selected:
            meta = s.meta or {}
            ref = meta.get("reference_display") or s.title or "User Content"
            source_name = s.title or "My Library"
            
            results.append(UnifiedContent(
                type=s.item_type or "note",
                text=s.text,
                arabic_text=s.arabic_text,
                source=source_name,
                reference=ref,
                topic_tags=s.topics or [],
                verified=meta.get("approval_status") == "approved", 
                provider=self.provider_name,
                original_id=str(s.id)
            ))
            
        return results
