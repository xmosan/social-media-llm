import csv
import io
import json
import hashlib
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session
from app.db import SessionLocal
from app.models import ContentItem, Org
from app.schemas import ContentItemOut, ContentItemCreate, ContentItemUpdate
from app.security import get_current_org
from app.services.content_library import normalize_topic

router = APIRouter(prefix="/library", tags=["library"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def generate_content_hash(org_id: int, source_name: str, reference: str, text_en: str) -> str:
    """Creates a unique hash to prevent duplicates."""
    raw = f"{org_id}|{source_name or ''}|{reference or ''}|{text_en}"
    return hashlib.md5(raw.encode()).hexdigest()

@router.get("/", response_model=List[ContentItemOut])
def list_library(
    topic: str | None = Query(None),
    type: str | None = Query(None),
    limit: int = 50,
    db: Session = Depends(get_db),
    org: Org = Depends(get_current_org)
):
    query = db.query(ContentItem).filter(ContentItem.org_id == org.id)
    
    if topic:
        norm_topic = normalize_topic(topic)
        if db.bind.dialect.name == 'postgresql':
            query = query.filter(ContentItem.topics.contains([norm_topic]))
        else:
            query = query.filter(ContentItem.topics.like(f'%"{norm_topic}"%'))
            
    if type:
        query = query.filter(ContentItem.type == type)
        
    return query.limit(limit).all()

@router.post("/import")
async def import_content(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    org: Org = Depends(get_current_org)
):
    """
    Import content items from JSON or CSV.
    CSV Columns: type, title, text_en, text_ar, source_name, reference, url, grade, topics (comma separated)
    """
    content = await file.read()
    filename = file.filename.lower()
    
    items_to_add = []
    
    if filename.endswith(".json"):
        try:
            data = json.loads(content)
            if not isinstance(data, list):
                data = [data]
            for d in data:
                # Normalize topics
                topics = d.get("topics", [])
                if isinstance(topics, str):
                    topics = [normalize_topic(t) for t in topics.split(",")]
                else:
                    topics = [normalize_topic(str(t)) for t in topics]
                    
                items_to_add.append({
                    "org_id": org.id,
                    "type": d.get("type", "hadith"),
                    "title": d.get("title"),
                    "text_en": d.get("text_en"),
                    "text_ar": d.get("text_ar"),
                    "source_name": d.get("source_name"),
                    "reference": d.get("reference"),
                    "url": d.get("url"),
                    "grade": d.get("grade"),
                    "topics": topics,
                    "language": d.get("language", "english")
                })
        except Exception as e:
            raise HTTPException(400, f"Invalid JSON: {str(e)}")
            
    elif filename.endswith(".csv"):
        try:
            stream = io.StringIO(content.decode("utf-8"))
            reader = csv.DictReader(stream)
            for row in reader:
                topics = [normalize_topic(t) for t in row.get("topics", "").split(",") if t.strip()]
                items_to_add.append({
                    "org_id": org.id,
                    "type": row.get("type", "hadith"),
                    "title": row.get("title"),
                    "text_en": row.get("text_en"),
                    "text_ar": row.get("text_ar"),
                    "source_name": row.get("source_name"),
                    "reference": row.get("reference"),
                    "url": row.get("url"),
                    "grade": row.get("grade"),
                    "topics": topics,
                    "language": row.get("language", "english")
                })
        except Exception as e:
            raise HTTPException(400, f"Invalid CSV: {str(e)}")
    else:
        raise HTTPException(400, "Only .json and .csv files supported")

    # Upsert logic (simple skip duplicates by text/source match in this session)
    count = 0
    for item_data in items_to_add:
        if not item_data["text_en"]:
            continue
            
        # Check if exists
        exists = db.query(ContentItem).filter(
            ContentItem.org_id == org.id,
            ContentItem.text_en == item_data["text_en"],
            ContentItem.source_name == item_data["source_name"],
            ContentItem.reference == item_data["reference"]
        ).first()
        
        if not exists:
            new_item = ContentItem(**item_data)
            db.add(new_item)
            count += 1
            
    db.commit()
    return {"status": "success", "imported": count}

@router.post("/seed-demo")
def seed_demo(db: Session = Depends(get_db), org: Org = Depends(get_current_org)):
    """Seeds some sample Hadiths for testing."""
    samples = [
        {
            "type": "hadith",
            "text_en": "Actions are but by intentions.",
            "source_name": "Sahih al-Bukhari",
            "reference": "1",
            "topics": ["intention", "basics"]
        },
        {
            "type": "hadith",
            "text_en": "Cleanliness is half of faith.",
            "source_name": "Sahih Muslim",
            "reference": "223",
            "topics": ["cleanliness", "faith"]
        },
        {
            "type": "reminder",
            "text_en": "Remember Allah and He will remember you.",
            "topics": ["dhikr", "connection"]
        }
    ]
    
    count = 0
    for s in samples:
        exists = db.query(ContentItem).filter(
            ContentItem.org_id == org.id,
            ContentItem.text_en == s["text_en"]
        ).first()
        if not exists:
            s["org_id"] = org.id
            s["topics"] = [normalize_topic(t) for t in s["topics"]]
            db.add(ContentItem(**s))
            count += 1
    db.commit()
    return {"status": "seeded", "count": count}

@router.get("/{item_id}", response_model=ContentItemOut)
def get_item(item_id: int, db: Session = Depends(get_db), org: Org = Depends(get_current_org)):
    item = db.query(ContentItem).filter(ContentItem.id == item_id, ContentItem.org_id == org.id).first()
    if not item:
        raise HTTPException(404, "Not found")
    return item
