# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from app.db import get_db
from app.models import TopicAutomation, IGAccount, Post
from app.schemas import TopicAutomationOut, TopicAutomationCreate, TopicAutomationUpdate, PostOut
from app.security.rbac import get_current_org_id
from app.services.scheduler import reload_automation_jobs
from app.services.llm import generate_topic_caption

# Phase 1: Route now calls automation_service instead of automation_runner directly.
# automation_runner is still the core engine — automation_service wraps it.
# This allows Phase 2 (Style DNA injection) to happen inside the service
# without changing this route file again.
from app.services.automation_service import (
    run_automation,
    get_automation_history,
    list_system_presets,
)
from app.services.library_retrieval import retrieve_relevant_chunks

router = APIRouter(prefix="/automations", tags=["automations"])

@router.get("", response_model=List[TopicAutomationOut])
def list_automations(
    ig_account_id: int | None = None,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    query = db.query(TopicAutomation).filter(TopicAutomation.org_id == org_id)
    if ig_account_id:
        query = query.filter(TopicAutomation.ig_account_id == ig_account_id)
    
    autos = query.all()
    results = []
    for a in autos:
        count = db.query(Post).filter(Post.automation_id == a.id).count()
        out = TopicAutomationOut.model_validate(a)
        out.posts_generated = count
        results.append(out)
    return results

@router.post("", response_model=TopicAutomationOut)
def create_automation(
    data: TopicAutomationCreate,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    # Verify account ownership
    acc = db.query(IGAccount).filter(IGAccount.id == data.ig_account_id, IGAccount.org_id == org_id).first()
    if not acc:
        raise HTTPException(status_code=403, detail="IG Account not found in your organization")
    
    # Filter out fields that don't exist in the model
    model_data = data.dict()
    valid_cols = [c.key for c in TopicAutomation.__table__.columns]
    filtered_data = {k: v for k, v in model_data.items() if k in valid_cols}

    new_auto = TopicAutomation(
        org_id=org_id,
        **filtered_data
    )
    db.add(new_auto)
    db.commit()
    db.refresh(new_auto)
    reload_automation_jobs(lambda: db)
    return new_auto

@router.get("/meta/style-presets")
def get_style_presets(
    org_id: int = Depends(get_current_org_id),
    db: Session = Depends(get_db)
):
    """
    Returns the available system Style DNA presets.
    Phase 1: Returns in-memory presets.
    Phase 2: Will merge in org-specific custom presets from the style_dna table.
    """
    return {"presets": list_system_presets(db)}

@router.get("/debug/llm-test")
def debug_llm_test(
    topic: str,
    style: str = "islamic_reminder",
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    """Smoke test for LLM generation with optional grounding."""
    try:
        # Step 1: Try to find any grounded content in the library for this topic
        chunks = retrieve_relevant_chunks(db, org_id, query=topic, k=1)
        extra_context = {}
        grounding_meta = None
        
        if chunks:
            chunk = chunks[0]
            grounding_meta = {
                "source": chunk.get("source"),
                "item_type": chunk.get("item_type", "reference"),
                "text": chunk.get("text")
            }
            extra_context = {
                "mode": "grounded_library",
                "snippet": {
                    "text": chunk.get("text"),
                    "reference": chunk.get("source"),
                    "source": chunk.get("source"),
                    "item_type": chunk.get("item_type")
                }
            }

        res = generate_topic_caption(topic=topic, style=style, extra_context=extra_context)
        
        # Inject grounding meta into the response for the UI to show
        if grounding_meta:
            res["grounding"] = grounding_meta
        else:
            res["grounding"] = {"item_type": "reflection", "source": "General Wisdom"}
            
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/run-scheduler-now")
def run_scheduler_now(
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    from app.services.scheduler import publish_due_posts
    try:
        count = publish_due_posts(lambda: db)
        return {"ok": True, "published": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{id}", response_model=List[TopicAutomationOut] if False else TopicAutomationOut) # Shadow prevention
def get_automation(
    id: int,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    auto = db.query(TopicAutomation).filter(TopicAutomation.id == id, TopicAutomation.org_id == org_id).first()
    if not auto:
        raise HTTPException(status_code=404, detail="Automation not found")
    return auto

@router.patch("/{id}", response_model=TopicAutomationOut)
def update_automation(
    id: int,
    data: TopicAutomationUpdate,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    auto = db.query(TopicAutomation).filter(TopicAutomation.id == id, TopicAutomation.org_id == org_id).first()
    if not auto:
        raise HTTPException(status_code=404, detail="Automation not found")
    
    update_data = data.dict(exclude_unset=True)
    valid_cols = [c.key for c in TopicAutomation.__table__.columns]
    
    for k, v in update_data.items():
        if k in valid_cols:
            setattr(auto, k, v)
    
    db.commit()
    db.refresh(auto)
    reload_automation_jobs(lambda: db)
    return auto

@router.delete("/{id}")
def delete_automation(
    id: int,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    auto = db.query(TopicAutomation).filter(TopicAutomation.id == id, TopicAutomation.org_id == org_id).first()
    if not auto:
        raise HTTPException(status_code=404, detail="Automation not found")
    
    db.delete(auto)
    db.commit()
    reload_automation_jobs(lambda: db)
    return {"ok": True}

@router.post("/{id}/run-once", response_model=PostOut)
def trigger_automation(
    id: int,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    """
    Run one automation cycle immediately.

    Phase 1: Calls automation_service.run_automation(), which wraps automation_runner.
    Phase 2: automation_service will inject Style DNA before running.
    Response shape is unchanged — still returns PostOut.
    """
    auto = db.query(TopicAutomation).filter(
        TopicAutomation.id == id, TopicAutomation.org_id == org_id
    ).first()
    if not auto:
        raise HTTPException(status_code=404, detail="Automation not found")

    result = run_automation(db, auto.id, force_publish=True)

    if not result.post:
        detail = result.error or "Automation run failed. Check history."
        raise HTTPException(status_code=500, detail=detail)
    
    if result.post.status == "failed" and "publish_error" in (result.post.flags or {}):
        raise HTTPException(status_code=500, detail=f"Instagram Publish Failed: {result.post.flags['publish_error']}")

    return result.post

@router.get("/{id}/history", response_model=List[PostOut])
def automation_history(
    id: int,
    limit: int = 20,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    """
    Returns the most recent posts generated by an automation.
    Phase 1 addition — exposes existing data that was always available in the DB.
    """
    auto = db.query(TopicAutomation).filter(
        TopicAutomation.id == id, TopicAutomation.org_id == org_id
    ).first()
    if not auto:
        raise HTTPException(status_code=404, detail="Automation not found")

    return get_automation_history(db, automation_id=id, org_id=org_id, limit=limit)
