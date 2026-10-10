"""Private preview invitations; public signup stays governed by its existing flag."""
import re
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.routing import APIRoute
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from app.config import settings
from app.db import get_db
from app.models import TesterInvitation, User
from app.schemas import CreatorPassword
from app.security.auth import create_user_access_token, clear_legacy_domain_cookie
from app.security.rbac import require_superadmin
from app.services import tester_invitations as invitations
from app.services.usage_limits import check_auth_attempt

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"
PRIVATE_HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"}


class PrivateRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def private(request):
            try:
                response = await handler(request)
            except RequestValidationError:
                # FastAPI's default validation payload can echo passwords/tokens.
                detail = ("Check your invitation, email and existing password. Passwords must fit within 72 UTF-8 bytes."
                          if request.url.path.endswith('/return') else
                          "Check your invitation, email and form fields. Passwords need at least 8 characters and at most 72 UTF-8 bytes.")
                response = JSONResponse({"detail": detail}, status_code=422)
            except HTTPException as exc:
                response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)
            response.headers.update(PRIVATE_HEADERS)
            return response
        return private


router = APIRouter(route_class=PrivateRoute)


def private_response(response: Response):
    response.headers.update(PRIVATE_HEADERS)


def same_origin(request: Request):
    expected, actual = urlsplit(settings.public_base_url), urlsplit(request.headers.get("origin", ""))
    if (expected.scheme, expected.netloc) != (actual.scheme, actual.netloc) or actual.path not in {"", "/"}:
        raise HTTPException(403, "Open this page in Sabeel Studio before continuing.")


class EmailPayload(BaseModel):
    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def email_address(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email address")
        return value


class IssuePayload(EmailPayload):
    invitation_days: int = Field(default=7, ge=1, le=30)
    pilot_days: int = Field(default=30, ge=1, le=90)
    returning: bool = Field(default=False, strict=True)


class TokenPayload(BaseModel):
    token: str = Field(min_length=43, max_length=43, pattern=r"^[A-Za-z0-9_-]+$")


class RedeemPayload(TokenPayload, EmailPayload):
    name: str = Field(min_length=1, max_length=80)
    password: CreatorPassword

    @field_validator("name")
    @classmethod
    def creator_name(cls, value):
        if not value.strip():
            raise ValueError("Enter your name")
        return value.strip()


class ReturnPayload(TokenPayload, EmailPayload):
    # Existing passwords are not subjected to today's new-password policy.
    password: str = Field(min_length=1, max_length=72)

    @field_validator("password")
    @classmethod
    def bounded_password(cls, value):
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password exceeds 72 UTF-8 bytes")
        return value


@router.get("/join", response_class=HTMLResponse)
def join_page():
    return HTMLResponse((TEMPLATES / "tester-join.html").read_text(), headers=PRIVATE_HEADERS)


@router.get("/admin/testers", response_class=HTMLResponse)
def admin_page(admin: User = Depends(require_superadmin)):
    return HTMLResponse((TEMPLATES / "tester-admin.html").read_text(), headers=PRIVATE_HEADERS)


@router.post("/auth/tester-invitations/check", dependencies=[Depends(same_origin), Depends(private_response)])
def check(payload: TokenPayload, db: Session = Depends(get_db)):
    check_auth_attempt("tester-invitation:" + invitations.digest(payload.token))
    row = invitations.pending(db, payload.token)
    # Do not disclose the recipient's address to whoever has a link.
    return {"pilot_days": row.pilot_days, "expires_at": row.expires_at,
            "daily_images": settings.ai_workspace_daily_images, "daily_text": settings.ai_workspace_daily_text,
            "returning": row.user_id is not None}


@router.post("/auth/tester-invitations/redeem", dependencies=[Depends(same_origin), Depends(private_response)])
def redeem(payload: RedeemPayload, response: Response, db: Session = Depends(get_db)):
    check_auth_attempt("tester-invitation:" + invitations.digest(payload.token))
    check_auth_attempt(payload.email)
    user = invitations.redeem(db, **payload.model_dump())
    clear_legacy_domain_cookie(response)
    response.set_cookie("access_token", create_user_access_token(user),
                        httponly=True, secure=True, samesite="lax", max_age=7 * 24 * 60 * 60)
    return {"next": "/app", "access_expires_at": user.tester_expires_at}


@router.post("/auth/tester-invitations/return", dependencies=[Depends(same_origin), Depends(private_response)])
def return_creator(payload: ReturnPayload, response: Response, db: Session = Depends(get_db)):
    check_auth_attempt("tester-invitation:" + invitations.digest(payload.token))
    check_auth_attempt(payload.email)
    user = invitations.restore(db, **payload.model_dump())
    clear_legacy_domain_cookie(response)
    response.set_cookie("access_token", create_user_access_token(user),
                        httponly=True, secure=True, samesite="lax", max_age=7 * 24 * 60 * 60)
    return {"next": "/app", "access_expires_at": user.tester_expires_at}


@router.get("/api/admin/tester-invitations", dependencies=[Depends(private_response)])
def list_invitations(admin: User = Depends(require_superadmin), db: Session = Depends(get_db)):
    rows = db.query(TesterInvitation).order_by(TesterInvitation.created_at.desc()).limit(200).all()
    return {"items": [invitations.describe(row) for row in rows], "limit": 200}


@router.post("/api/admin/tester-invitations", dependencies=[Depends(same_origin), Depends(private_response)])
def issue(payload: IssuePayload, admin: User = Depends(require_superadmin), db: Session = Depends(get_db)):
    check_auth_attempt("tester-admin:" + str(admin.id))
    row, token = invitations.issue(db, admin_id=admin.id, **payload.model_dump())
    return {"invitation": invitations.describe(row),
            "link": settings.public_base_url.rstrip("/") + "/join#invite=" + token}


@router.post("/api/admin/tester-invitations/{invitation_id}/revoke", dependencies=[Depends(same_origin), Depends(private_response)])
def revoke(invitation_id: str, admin: User = Depends(require_superadmin), db: Session = Depends(get_db)):
    return invitations.describe(invitations.revoke(db, invitation_id, admin.id))
