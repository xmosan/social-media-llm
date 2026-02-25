from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
from app.db import get_db
from app.models import SourceDocument
from app.schemas import SourceDocumentOut, SourceDocumentCreate
from app.security.rbac import get_current_org_id
from app.services.ingestion import ingest_document

router = APIRouter(prefix="/library", tags=["library"])

@router.get("", response_model=List[SourceDocumentOut])
def list_library_documents(
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    """Lists all documents in the organizational library."""
    docs = db.query(SourceDocument).filter(SourceDocument.org_id == org_id).order_by(SourceDocument.created_at.desc()).all()
    return docs

@router.post("/upload", response_model=SourceDocumentOut)
async def upload_document(
    title: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    """Uploads a PDF or TXT file to the library."""
    content = await file.read()
    filename = file.filename
    source_type = "pdf" if filename.lower().endswith(".pdf") else "text"
    
    doc_title = title or filename
    
    doc = ingest_document(
        db=db,
        org_id=org_id,
        title=doc_title,
        source_type=source_type,
        file_bytes=content if source_type == "pdf" else None,
        content=content.decode("utf-8", errors="ignore") if source_type == "text" else None
    )
    return doc

@router.post("/add_text", response_model=SourceDocumentOut)
def add_text_document(
    data: SourceDocumentCreate,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    """Adds a text document (pasted) to the library."""
    doc = ingest_document(
        db=db,
        org_id=org_id,
        title=data.title,
        source_type="text",
        content=data.raw_text
    )
    return doc

@router.post("/add_url", response_model=SourceDocumentOut)
def add_url_document(
    data: SourceDocumentCreate,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    """Adds a URL source to the library."""
    if not data.original_url:
        raise HTTPException(status_code=400, detail="original_url is required for URL source")
    
    doc = ingest_document(
        db=db,
        org_id=org_id,
        title=data.title or data.original_url,
        source_type="url",
        url=data.original_url
    )
    return doc

@router.delete("/{doc_id}")
def delete_document(
    doc_id: int,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    """Deletes a document and its chunks from the library."""
    doc = db.query(SourceDocument).filter(SourceDocument.id == doc_id, SourceDocument.org_id == org_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    db.delete(doc)
    db.commit()
    return {"status": "success", "message": f"Document {doc_id} deleted"}
