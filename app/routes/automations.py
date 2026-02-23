from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from app.db import get_db
from app.models import TopicAutomation, IGAccount
from app.schemas import TopicAutomationOut, TopicAutomationCreate, TopicAutomationUpdate, PostOut
from app.security.rbac import get_current_org_id
from app.services.automation_runner import run_automation_once
from app.services.scheduler import reload_automation_jobs
from app.services.llm import generate_topic_caption

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
    return query.all()

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
    
    new_auto = TopicAutomation(
        org_id=org_id,
        **data.dict()
    )
    db.add(new_auto)
    db.commit()
    db.refresh(new_auto)
    reload_automation_jobs(lambda: db)
    return new_auto

@router.get("/{id}", response_model=TopicAutomationOut)
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
    for k, v in update_data.items():
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
    auto = db.query(TopicAutomation).filter(TopicAutomation.id == id, TopicAutomation.org_id == org_id).first()
    if not auto:
        raise HTTPException(status_code=404, detail="Automation not found")
    
    # We run it synchronously for the API response
    post = run_automation_once(db, auto.id)
    if not post:
        raise HTTPException(status_code=500, detail="Automation run failed. Check history.")
    
    return post

@router.get("/debug/llm-test")
def debug_llm_test(
    topic: str,
    style: str = "islamic_reminder",
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    """Smoke test for LLM generation."""
    try:
        res = generate_topic_caption(topic=topic, style=style)
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
