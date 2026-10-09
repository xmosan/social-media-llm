"""Workspace-bound Instagram authorization; provider credentials stay server-side."""
import asyncio
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User, IGAccount
from app.security.auth import require_user
from app.security.rbac import get_current_org_id
from app.services.instagram_auth import instagram_auth_service
from app.services import instagram_connection as connection
from app.services.usage_limits import check_auth_attempt
from app.logging_setup import log_event

router = APIRouter(prefix="/auth/instagram", tags=["auth"])
meta_alias_router = APIRouter(prefix="/auth/meta", tags=["auth"])


@router.get("/login")
async def instagram_login(request: Request, user: User = Depends(require_user),
                          db: Session = Depends(get_db), org_id: int = Depends(get_current_org_id)):
    check_auth_attempt(str(user.id))
    instagram_auth_service.validate_configuration()
    state = connection.begin(db, request, user.id, org_id)
    return RedirectResponse(instagram_auth_service.get_auth_url(state), status_code=303,
                            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@router.get("/callback")
@meta_alias_router.get("/callback")
async def instagram_callback(request: Request, code: str | None = None, state: str | None = None,
                             db: Session = Depends(get_db), user: User = Depends(require_user),
                             org_id: int = Depends(get_current_org_id)):
    attempt_id = connection.claim_callback(db, request, user.id, org_id, state)
    if request.query_params.get("error") or not code:
        connection.abandon(db, request, attempt_id)
        return RedirectResponse("/select-account?connection=cancelled", status_code=303)
    try:
        async with asyncio.timeout(60):
            short_token = await instagram_auth_service.exchange_code_for_token(code)
            token_data = await instagram_auth_service.get_long_lived_token(short_token)
            accounts = await instagram_auth_service.discover_ig_business_account(token_data["access_token"])
        if not accounts:
            connection.abandon(db, request, attempt_id)
            return RedirectResponse("/select-account?connection=no-accounts", status_code=303)
        connection.finish_discovery(db, attempt_id, accounts, token_data)
    except Exception:
        db.rollback()
        connection.abandon(db, request, attempt_id)
        log_event("ig_connection_failed", level="warning")
        return RedirectResponse("/select-account?connection=unavailable", status_code=303)
    return RedirectResponse("/select-account", status_code=303,
                            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@router.post("/disconnect")
async def instagram_disconnect(request: Request, db: Session = Depends(get_db),
                               user: User = Depends(require_user), org_id: int = Depends(get_current_org_id)):
    connection.require_same_origin(request)
    account = db.query(IGAccount).filter(IGAccount.org_id == org_id).order_by(IGAccount.active.desc(), IGAccount.id).first()
    if account:
        account.active = False
        account.access_token = ""
        account.expires_at = None
    db.flush()
    user.has_connected_instagram = db.query(IGAccount).filter(IGAccount.org_id == org_id,
        IGAccount.active == True, IGAccount.access_token != "").first() is not None
    db.commit()
    # Preserve account rows referenced by drafts, schedules and publishing claims.
    return {"ok": True}
