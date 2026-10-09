"""Private, authenticated creator feedback in the existing support inbox."""
import html
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import InboundMessage, User
from app.security.auth import require_user
from app.security.rbac import get_current_org_id, require_superadmin
from app.routes.tester_access import PRIVATE_HEADERS, same_origin

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"


class FeedbackRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def private(request: Request):
            try:
                response = await handler(request)
            except RequestValidationError:
                response = JSONResponse({"detail": "Check the required answers and character limits."}, status_code=422)
            except HTTPException as exc:
                response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)
            response.headers.update(PRIVATE_HEADERS)
            return response
        return private


router = APIRouter(route_class=FeedbackRoute)


class FeedbackPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: UUID
    device: str = Field(min_length=2, max_length=120)
    task: Literal["join", "source", "design", "edit", "save", "export", "schedule", "publish", "other"]
    outcome: Literal["completed", "needed_help", "could_not_finish"]
    confidence: Literal["ready", "after_edits", "not_ready", "not_created"]
    notes: str = Field(min_length=3, max_length=3000)


def save_feedback(db: Session, user: User, payload: FeedbackPayload):
    # Lock the existing user row: concurrent retries and the per-user limit share
    # one transaction without introducing another schema or uniqueness migration.
    db.query(User).filter(User.id == user.id).with_for_update().one()
    prefix = f"Creator feedback · {user.id} · "
    subject = prefix + str(payload.request_id)
    body = json.dumps(payload.model_dump(exclude={"request_id"}), ensure_ascii=False, sort_keys=True)
    existing = db.query(InboundMessage).filter_by(source="creator_pilot", subject=subject).first()
    if existing:
        if existing.message != body:
            raise HTTPException(409, "This feedback was already saved with different answers. Reload to start another report.")
        db.commit()
        return {"ok": True, "feedback_id": existing.id}
    since = datetime.now(timezone.utc) - timedelta(days=1)
    count = db.query(InboundMessage).filter(InboundMessage.source == "creator_pilot",
            InboundMessage.subject.startswith(prefix), InboundMessage.created_at >= since).count()
    if count >= 20:
        raise HTTPException(429, "You've sent 20 reports in the last 24 hours. Please try again later.")
    row = InboundMessage(email=user.email, name=user.name, subject=subject, message=body, source="creator_pilot")
    db.add(row)
    db.flush()
    identifier = row.id
    db.commit()
    return {"ok": True, "feedback_id": identifier}


@router.get("/app/feedback", response_class=HTMLResponse)
def feedback_page(user: User = Depends(require_user), org_id: int = Depends(get_current_org_id)):
    return HTMLResponse((TEMPLATES / "creator-feedback.html").read_text())


@router.post("/api/creator-feedback", dependencies=[Depends(same_origin)])
def submit_feedback(payload: FeedbackPayload, user: User = Depends(require_user),
                    org_id: int = Depends(get_current_org_id), db: Session = Depends(get_db)):
    try:
        return save_feedback(db, user, payload)
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        # Never return or log the submitted text, email or database exception.
        raise HTTPException(503, "We couldn't confirm your feedback was saved. Please retry with the same answers.")


@router.get("/admin/feedback", response_class=HTMLResponse)
def feedback_inbox(admin: User = Depends(require_superadmin), db: Session = Depends(get_db)):
    rows = db.query(InboundMessage).filter_by(source="creator_pilot").order_by(InboundMessage.created_at.desc(), InboundMessage.id.desc()).limit(200).all()
    cards = []
    labels = {"device": "Phone / browser", "task": "Task", "outcome": "Outcome", "confidence": "Would publish", "notes": "Creator's notes"}
    choices = {"join": "Join and get started", "source": "Choose a source", "design": "Create a design",
               "edit": "Edit a post or brand", "save": "Save or reopen a draft", "export": "Download images",
               "schedule": "Schedule a post", "publish": "Publish to Instagram", "other": "Something else",
               "completed": "Finished independently", "needed_help": "Finished with help", "could_not_finish": "Couldn't finish",
               "ready": "Yes, as it is", "after_edits": "After some edits", "not_ready": "Not ready",
               "not_created": "No image created yet"}
    for row in rows:
        try:
            answers = json.loads(row.message)
            if not isinstance(answers, dict):
                raise ValueError("Invalid saved feedback")
        except (ValueError, TypeError):
            answers = {"notes": row.message}
        fields = []
        for key, label in labels.items():
            answer = str(answers.get(key, "—"))
            if key in {"task", "outcome", "confidence"}:
                answer = choices.get(answer, answer)
            fields.append(f'<dt>{label}</dt><dd>{html.escape(answer)}</dd>')
        fields = "".join(fields)
        date = row.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if row.created_at else ""
        cards.append(f'<article class="card"><h2>Feedback #{row.id}</h2><p>{html.escape(row.name or "Creator")} · {html.escape(row.email)}</p><p class="hint">{date}</p><dl>{fields}</dl></article>')
    template = (TEMPLATES / "creator-feedback-admin.html").read_text()
    return HTMLResponse(template.replace("<!-- feedback -->", "".join(cards) or '<p class="card">No creator feedback yet.</p>'))
