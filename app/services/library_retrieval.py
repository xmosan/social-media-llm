from sqlalchemy.orm import Session
from sqlalchemy import func, or_, cast, String
from app.models import SourceDocument, SourceChunk, ContentItem, ContentSource
from typing import List, Dict, Any
import re

def retrieve_relevant_chunks(db: Session, org_id: int, query: str, k: int = 5, topic_slug: str = None) -> List[Dict[str, Any]]:
    """Retrieves relevant knowledge snippets from BOTH documents and structured library entries."""
    if not query and not topic_slug:
        return []
    
    keywords = set(re.findall(r'\w+', query.lower())) if query else set()
    
    scored_results = []
    
    # --- 1. SEARCH UNSTRUCTURED CHUNKS (SourceDocs) ---
    if keywords:
        chunks = db.query(SourceChunk, SourceDocument.title, SourceDocument.original_url)\
            .join(SourceDocument, SourceChunk.document_id == SourceDocument.id)\
            .filter(SourceChunk.org_id == org_id)\
            .all()
            
        for chunk, doc_title, doc_url in chunks:
            text_lower = chunk.chunk_text.lower()
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scored_results.append({
                    "score": score,
                    "type": "unstructured",
                    "source": doc_title,
                    "url": doc_url,
                    "text": chunk.chunk_text,
                    "metadata": chunk.chunk_metadata
                })

    # --- 2. SEARCH STRUCTURED ENTRIES (ContentItems) ---
    # Merge items where org_id matches OR is NULL (System)
    entries = db.query(ContentItem, ContentSource.name)\
        .join(ContentSource, ContentItem.source_id == ContentSource.id)\
        .filter(or_(ContentItem.org_id == org_id, ContentItem.org_id == None))\
        .all()
        
    for entry, src_name in entries:
        score = 0
        text_lower = (entry.text or "").lower()
        
        # Keyword matches
        if keywords:
            score += sum(1 for kw in keywords if kw in text_lower)
            entry_topics = [t.lower() for t in (entry.topics or [])]
            score += sum(5 for kw in keywords if kw in entry_topics)

        # Topic Slug match (EXACT GROUNDING)
        if topic_slug and topic_slug in (entry.topics_slugs or []):
            score += 25 # High priority for the linked topic
        
        if score > 0:
            item_ref = src_name
            if entry.item_type == 'quran':
                surah = entry.meta.get('surah_number') or entry.meta.get('surah') or entry.meta.get('sura')
                verse = entry.meta.get('verse_start') or entry.meta.get('verse') or entry.meta.get('ayah')
                if surah and verse:
                    item_ref = f"Quran {surah}:{verse}"
                else:
                    item_ref = None
            elif entry.item_type == 'hadith':
                coll = entry.meta.get('collection') or entry.meta.get('book') or "Hadith"
                num = entry.meta.get('hadith_number') or entry.meta.get('number') or entry.meta.get('id')
                if num:
                    item_ref = f"{coll} #{num}"
                else:
                    item_ref = None

            scored_results.append({
                "score": score,
                "type": "structured",
                "item_type": entry.item_type,
                "source": item_ref,
                "text": entry.text,
                "arabic": entry.arabic_text,
                "metadata": entry.meta
            })
    
    # Sort and return top k
    scored_results.sort(key=lambda x: x["score"], reverse=True)
    return scored_results[:k]
