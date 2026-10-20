"""Phone-friendly owner enrollment, verification and recovery controls."""
import base64
from io import BytesIO
from pathlib import Path

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.routes.auth import AuthRoute
from app.security.auth import get_current_user
from app.security.rbac import is_platform_owner, require_superadmin
from app.security import owner_mfa as mfa

router = APIRouter(prefix=mfa.PATH, tags=["owner-security"], route_class=AuthRoute)
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; "
       "img-src 'self' data:; connect-src 'self'; form-action 'self'; "
       "base-uri 'none'; frame-ancestors 'none'")


class Verification(BaseModel):
    code: SecretStr = Field(min_length=6, max_length=64)


@router.get("", response_class=HTMLResponse)
def security_page():
    page = Path(__file__).resolve().parents[1] / "templates" / "owner-security.html"
    return HTMLResponse(page.read_text(), headers={"Content-Security-Policy": CSP,
                         "Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@router.get("/status")
def security_status(request: Request, db: Session = Depends(get_db),
                    user: User | None = Depends(get_current_user)):
    if request.cookies.get(mfa.COOKIE):
        try:
            candidate = mfa.challenge_user(request, db)
            return {"mode": "verify" if mfa.enabled(candidate) else "enroll"}
        except HTTPException as error:
            if error.status_code != 401:
                raise
    if is_platform_owner(user):
        if not mfa.enabled(user):
            return {"mode": "sign_in", "setup_needed": True}
        return {"mode": "manage", "recovery_remaining": len(mfa.state(user).get("recovery_hashes", []))}
    return {"mode": "sign_in"}


@router.post("/enroll")
def enroll(request: Request, db: Session = Depends(get_db)):
    secret, uri = mfa.begin_enrollment(request, db)
    image = qrcode.make(uri)
    output = BytesIO()
    image.save(output, format="PNG")
    return {"setup_key": secret,
            "qr": "data:image/png;base64," + base64.b64encode(output.getvalue()).decode()}


@router.post("/verify")
def verify(payload: Verification, request: Request, response: Response,
           db: Session = Depends(get_db)):
    return mfa.finish_verification(request, db, response, payload.code.get_secret_value())


@router.post("/reauth")
def reauthenticate(request: Request, response: Response, db: Session = Depends(get_db),
                   user: User | None = Depends(get_current_user)):
    if not is_platform_owner(user) or not mfa.enabled(user):
        # Enrollment must follow a fresh password/Google sign-in, never an old cookie.
        raise HTTPException(401, "Sign in again before setting up owner protection.")
    locked = mfa._locked(db, user.id)
    if request.state.session_version != (locked.session_version or 0):
        raise HTTPException(401, "Sign in again.")
    mfa.issue_challenge(db, locked, response)
    return {"mode": "verify"}


@router.post("/recovery")
def recovery(payload: Verification, request: Request, response: Response,
             db: Session = Depends(get_db), user: User = Depends(require_superadmin)):
    return mfa.rotate_recovery(request, db, response, user, payload.code.get_secret_value())


@router.post("/revoke-sessions")
def revoke(request: Request, response: Response, db: Session = Depends(get_db),
           user: User = Depends(require_superadmin)):
    return mfa.revoke_sessions(request, db, response, user)
