import requests
from bs4 import BeautifulSoup
import io
import re
from typing import List, Dict
from sqlalchemy.orm import Session
from app.models import SourceDocument, SourceChunk
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
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except ImportError:
        logger.error("pypdf not installed. Cannot extract text from PDF.")
        return "[Error: pypdf not installed]"
    except Exception as e:
        logger.error(f"Error extracting PDF: {e}")
        return f"[Error extracting PDF: {e}]"

def extract_text_from_url(url: str) -> str:
    """Fetches URL and extracts readable text."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
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
    except Exception as e:
        logger.error(f"Error extracting URL {url}: {e}")
        return f"[Error extracting URL: {e}]"

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
                metadata={}
            )
            db.add(chunk)
            
    db.commit()
    db.refresh(doc)
    return doc
