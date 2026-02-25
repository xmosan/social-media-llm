from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models import SourceDocument, SourceChunk
from typing import List, Dict, Any
import re

def retrieve_relevant_chunks(db: Session, org_id: int, query: str, k: int = 5) -> List[Dict[str, Any]]:
    """Retrieves relevant chunks from the organizational library using simple keyword scoring."""
    if not query:
        return []
    
    # Tokenize query into keywords (lowercase, alphanumeric)
    keywords = set(re.findall(r'\w+', query.lower()))
    if not keywords:
        return []
    
    # Fetch all chunks for the organization
    # In a real vector DB this would be a similarity search.
    # For now, we fetch all and score in memory if the library is small,
    # or use LIKE clauses if we want database-level filtering.
    
    # Let's use a slightly more efficient approach: find chunks that contain at least one keyword
    # This is still O(N) but restricted to the organization.
    chunks = db.query(SourceChunk, SourceDocument.title, SourceDocument.original_url)\
        .join(SourceDocument, SourceChunk.document_id == SourceDocument.id)\
        .filter(SourceChunk.org_id == org_id)\
        .all()
    
    scored_chunks = []
    for chunk, doc_title, doc_url in chunks:
        chunk_text_lower = chunk.chunk_text.lower()
        score = 0
        for kw in keywords:
            if kw in chunk_text_lower:
                score += 1
        
        if score > 0:
            scored_chunks.append({
                "score": score,
                "doc_title": doc_title,
                "url": doc_url,
                "chunk_text": chunk.chunk_text,
                "chunk_metadata": chunk.chunk_metadata
            })
    
    # Sort by score descending and return top k
    scored_chunks.sort(key=lambda x: x["score"], reverse=True)
    return scored_chunks[:k]
