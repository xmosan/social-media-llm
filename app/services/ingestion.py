# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

from bs4 import BeautifulSoup
import io
import re
from typing import List, Dict
from sqlalchemy.orm import Session
from app.models import SourceDocument, SourceChunk
from app.security.public_fetch import fetch_public_document
import logging

logger = logging.getLogger(__name__)

def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 150) -> List[str]:
    """Chunks text into segments of fixed size with overlap."""
    if not text:
        return []
    
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
        
    return chunks

def extract_text_from_pdf(content: bytes) -> str:
    """Extracts text from PDF bytes using pypdf."""
    from fastapi import HTTPException
    try:
        from pypdf import PdfReader
    except ImportError:
        raise HTTPException(503, "PDF import is unavailable. Paste the source text instead.") from None
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted or len(reader.pages) > 100:
            raise ValueError()
        pages, size = [], 0
        for page in reader.pages:
            value = page.extract_text() or ""
            size += len(value)
            if size > 500_000:
                raise ValueError()
            pages.append(value)
        return "\n".join(pages).strip()
    except Exception:
        raise HTTPException(422, "Use an unencrypted PDF up to 100 pages, or paste the relevant text.") from None

def extract_text_from_url(url: str) -> str:
    """Fetches URL and extracts readable text."""
    try:
        content = fetch_public_document(url)
        soup = BeautifulSoup(content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
            
        # Get text
        text = soup.get_text()
        
        # Break into lines and remove leading and trailing whitespace
        lines = (line.strip() for line in text.splitlines())
        # Break multi-headlines into a line each
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        # Drop blank lines
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        return text
    except ValueError as error:
        from fastapi import HTTPException
        raise HTTPException(422, str(error)) from None
    except Exception:
        from fastapi import HTTPException
        logger.error("source_url_import_failed")
        raise HTTPException(422, "The page could not be imported. Paste the source text instead.") from None

def ingest_document(db: Session, org_id: int, title: str, source_type: str, content: str = None, file_bytes: bytes = None, url: str = None) -> SourceDocument:
    """Handles the ingestion of a new document into the library."""
    raw_text = ""
    original_url = url
    
    if source_type == "text":
        raw_text = content or ""
    elif source_type == "pdf" and file_bytes:
        raw_text = extract_text_from_pdf(file_bytes)
    elif source_type == "url" and url:
        raw_text = extract_text_from_url(url)
    
    if not raw_text.strip() or len(raw_text) > 500_000:
        from fastapi import HTTPException
        raise HTTPException(422, "Provide readable source text up to 500,000 characters.")

    # Create the document record
    doc = SourceDocument(
        org_id=org_id,
        title=title,
        source_type=source_type,
        original_url=original_url,
        raw_text=raw_text,
        status="active" if raw_text and not raw_text.startswith("[Error") else "error"
    )
    db.add(doc)
    db.flush() # Get ID
    
    # Chunk and store
    if doc.status == "active":
        chunks = chunk_text(raw_text)
        for i, chunk_content in enumerate(chunks):
            chunk = SourceChunk(
                org_id=org_id,
                document_id=doc.id,
                chunk_index=i,
                chunk_text=chunk_content,
                chunk_metadata={}
            )
            db.add(chunk)
            
    db.commit()
    db.refresh(doc)
    return doc
