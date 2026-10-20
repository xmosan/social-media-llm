"""Owner second factor: expiring challenges, encrypted TOTP and one-use recovery.

Every state transition locks the user row. A challenge is not an access token.
No email/SMS fallback or browser endpoint can disable the enrolled factor.
"""
import base64
import hashlib
import hmac
import logging
import secrets
import time
from datetime import timedelta

import jwt
import pyotp
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy import select

from app.config import settings
from app.models import User
from app.services.usage_limits import check_auth_attempt

logger = logging.getLogger(__name__)
COOKIE = "owner_challenge"
PATH = "/auth/owner-security"
CHALLENGE_SECONDS = 300
SESSION_SECONDS = 8 * 3600
FRESH_SECONDS = 15 * 60


def now():
    return int(time.time())


def state(user):
    return dict(getattr(user, "owner_mfa", None) or {})


def enabled(user):
    # An incomplete/corrupt enrolled record must never silently disable MFA.
    return bool(state(user).get("enabled_at"))


def _digest(value, purpose):
    return hmac.new(settings.secret_key.encode(),
                    ("owner-mfa-v1:" + purpose + ":" + value).encode(),
                    hashlib.sha256).hexdigest()


def _cipher():
    key = hmac.new(settings.secret_key.encode(), b"sabeel-owner-mfa-storage-v1",
                   hashlib.sha256).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def _open(value):
    try:
        return _cipher().decrypt(value.encode()).decode()
    except (InvalidToken, AttributeError, ValueError, UnicodeError):
        raise HTTPException(503, "Owner verification is unavailable. Use the recovery procedure.") from None


def _locked(db, user_id):
    user = db.execute(select(User).where(User.id == user_id).with_for_update()
                      .execution_options(populate_existing=True)).scalar_one_or_none()
    from app.security.rbac import is_platform_owner
    if not is_platform_owner(user):
        raise HTTPException(403, "This area is available only to the Sabeel owner.")
    return user


def clear_challenge(response):
    response.delete_cookie(COOKIE, path=PATH, httponly=True, secure=True, samesite="strict")


def issue_challenge(db, user, response):
    user = _locked(db, user.id)
    value = state(user)
    nonce, issued = secrets.token_urlsafe(32), now()
    value.update(challenge_hash=_digest(nonce, "challenge"),
                 challenge_expires=issued + CHALLENGE_SECONDS)
    value.pop("pending_secret", None)
    user.owner_mfa = value
    db.commit()
    token = jwt.encode({"sub": str(user.id), "sv": user.session_version or 0,
                        "jti": nonce, "iat": issued, "exp": issued + CHALLENGE_SECONDS,
                        "aud": "sabeel-owner-challenge"}, settings.secret_key, algorithm="HS256")
    response.set_cookie(COOKIE, token, max_age=CHALLENGE_SECONDS, path=PATH,
                        httponly=True, secure=True, samesite="strict")


def challenge_user(request, db, *, lock=False):
    try:
        payload = jwt.decode(request.cookies.get(COOKIE, ""), settings.secret_key,
                             algorithms=["HS256"], audience="sabeel-owner-challenge",
                             options={"require": ["sub", "sv", "jti", "iat", "exp", "aud"]})
        sub, nonce = payload["sub"], payload["jti"]
        if (not isinstance(sub, str) or not sub.isascii() or not sub.isdecimal()
                or len(sub) > 10 or not 0 < int(sub) <= 2147483647
                or not isinstance(nonce, str) or len(nonce) > 100):
            raise ValueError()
    except (jwt.PyJWTError, ValueError, TypeError):
        raise HTTPException(401, "Verification expired. Sign in again.") from None
    user = _locked(db, int(sub)) if lock else db.get(User, int(sub))
    from app.security.rbac import is_platform_owner
    if not is_platform_owner(user):
        raise HTTPException(401, "Verification expired. Sign in again.")
    value = state(user)
    if (payload["sv"] != (user.session_version or 0)
            or value.get("challenge_expires", 0) <= now()
            or not hmac.compare_digest(value.get("challenge_hash", ""), _digest(nonce, "challenge"))):
        raise HTTPException(401, "Verification expired. Sign in again.")
    return user


def access_valid(user, payload):
    timestamp = payload.get("mfa_at")
    return (payload.get("mfa") in {"totp", "recovery"}
            and type(timestamp) is int and 0 <= now() - timestamp < SESSION_SECONDS)


def require_recent(request, user):
    if enabled(user):
        verified = getattr(request.state, "owner_mfa_at", 0) if request else 0
        if type(verified) is not int or not 0 <= now() - verified < FRESH_SECONDS:
            raise HTTPException(403, "Verify your owner access again before this action.",
                                headers={"X-Sabeel-Owner-Verification": PATH,
                                         "Cache-Control": "no-store"})


def _attempt(user):
    # Durable, shared across replicas, independent of attacker-supplied IPs.
    check_auth_attempt("owner-second-factor:" + str(user.id))


def begin_enrollment(request, db):
    candidate = challenge_user(request, db)
    _attempt(candidate)
    user = challenge_user(request, db, lock=True)
    if enabled(user):
        raise HTTPException(409, "Owner verification is already enabled.")
    value = state(user)
    if not value.get("pending_secret"):
        value["pending_secret"] = _cipher().encrypt(pyotp.random_base32().encode()).decode()
        user.owner_mfa = value
        db.commit()
    secret = _open(value["pending_secret"])
    return secret, pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name="Sabeel Studio")


def _totp_step(secret, code, previous=-1):
    if not isinstance(code, str) or len(code) != 6 or not code.isascii() or not code.isdecimal():
        return None
    step = now() // 30
    otp = pyotp.TOTP(secret)
    for candidate in (step, step - 1, step + 1):
        if candidate > previous and hmac.compare_digest(otp.at(candidate * 30), code):
            return candidate
    return None


def _recovery_codes(user_id):
    codes = []
    for _ in range(10):
        raw = secrets.token_hex(16)
        codes.append("-".join(raw[i:i + 8] for i in range(0, 32, 8)))
    hashes = [_digest(code.replace("-", ""), f"recovery:{user_id}") for code in codes]
    return codes, hashes


def _issue_access(user, response, method, *, verified_at=None):
    from app.security.auth import create_user_access_token, clear_legacy_domain_cookie
    token = create_user_access_token(user, timedelta(seconds=SESSION_SECONDS),
                                    extra={"mfa": method, "mfa_at": now() if verified_at is None else verified_at})
    clear_legacy_domain_cookie(response)
    clear_challenge(response)
    response.set_cookie("access_token", token, max_age=SESSION_SECONDS,
                        httponly=True, secure=True, samesite="lax", path="/")


def finish_verification(request, db, response, code):
    candidate = challenge_user(request, db)
    _attempt(candidate)
    user = challenge_user(request, db, lock=True)
    value = state(user)
    enrolling = not enabled(user)
    secret = _open(value.get("pending_secret") if enrolling else value.get("secret"))
    step = _totp_step(secret, code, value.get("last_step", -1))
    method, codes = "totp", None
    if step is None and not enrolling:
        normalized = code.replace("-", "").strip().lower()
        digest = _digest(normalized, f"recovery:{user.id}")
        hashes = value.get("recovery_hashes", [])
        matched = next((item for item in hashes if hmac.compare_digest(item, digest)), None)
        if matched:
            value["recovery_hashes"] = [item for item in hashes if item != matched]
            method = "recovery"
            user.session_version = (user.session_version or 0) + 1
        else:
            raise HTTPException(400, "Code not accepted. Use a new authenticator code or an unused recovery code.")
    elif step is None:
        raise HTTPException(400, "Code not accepted. Wait for a new authenticator code and try again.")
    else:
        value["last_step"] = step
    if enrolling:
        codes, hashes = _recovery_codes(user.id)
        value.update(secret=value["pending_secret"], enabled_at=now(), recovery_hashes=hashes)
        user.session_version = (user.session_version or 0) + 1
    for key in ("pending_secret", "challenge_hash", "challenge_expires"):
        value.pop(key, None)
    user.owner_mfa = value
    db.commit()
    _issue_access(user, response, method)
    logger.info("owner_verification_succeeded", extra={"event": "owner_verification_succeeded",
                "method": method, "enrollment": enrolling})
    return {"verified": True, "recovery_codes": codes, "next": "/admin"}


def rotate_recovery(request, db, response, user, code):
    _attempt(user)
    user = _locked(db, user.id)
    if getattr(request.state, "session_version", None) != (user.session_version or 0):
        raise HTTPException(401, "Sign in again.")
    require_recent(request, user)
    value = state(user)
    if not enabled(user):
        raise HTTPException(409, "Set up owner verification first.")
    step = _totp_step(_open(value.get("secret")), code, value.get("last_step", -1))
    if step is None:
        raise HTTPException(400, "Use a new authenticator code to replace recovery codes.")
    codes, hashes = _recovery_codes(user.id)
    value.update(last_step=step, recovery_hashes=hashes)
    user.owner_mfa = value
    user.session_version = (user.session_version or 0) + 1
    db.commit()
    _issue_access(user, response, "totp")
    return {"recovery_codes": codes}


def revoke_sessions(request, db, response, user):
    user = _locked(db, user.id)
    if getattr(request.state, "session_version", None) != (user.session_version or 0):
        raise HTTPException(401, "Sign in again.")
    if not enabled(user):
        raise HTTPException(409, "Set up owner verification first.")
    require_recent(request, user)
    value = state(user)
    for key in ("challenge_hash", "challenge_expires", "pending_secret"):
        value.pop(key, None)
    user.owner_mfa = value
    user.session_version = (user.session_version or 0) + 1
    db.commit()
    _issue_access(user, response, "totp", verified_at=request.state.owner_mfa_at)
    return {"revoked": True}
