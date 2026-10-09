"""Atomic OAuth handoff and account selection shared by current and legacy routes."""
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy import delete, or_, update
from app.config import settings
from app.models import InstagramConnectionAttempt as Attempt, IGAccount, Org


def utcnow():
    return datetime.now(timezone.utc)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def cipher():
    key = hmac.new(settings.secret_key.encode(), b"sabeel-instagram-handoff-v1", hashlib.sha256).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def clear_legacy(request):
    request.session.pop("temp_ig_token", None)
    request.session.pop("discovered_accounts", None)


def purge_expired(db_factory):
    db = db_factory()
    try:
        db.execute(delete(Attempt).where(Attempt.expires_at <= utcnow()))
        db.commit()
    finally:
        db.close()


def begin(db, request, user_id, org_id):
    clear_legacy(request)
    handle, state = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.execute(delete(Attempt).where(or_(Attempt.expires_at <= utcnow(), Attempt.user_id == user_id)))
    db.add(Attempt(id=digest(handle), user_id=user_id, org_id=org_id,
                   state_hash=digest(state), stage="pending", expires_at=utcnow() + timedelta(minutes=15)))
    db.commit()
    request.session["ig_connection"] = handle
    return state


def selector(request, user_id, org_id):
    handle = request.session.get("ig_connection")
    if not isinstance(handle, str) or not 20 <= len(handle) <= 128:
        raise HTTPException(401, "Instagram connection expired. Please connect again.")
    return (Attempt.id == digest(handle), Attempt.user_id == user_id,
            Attempt.org_id == org_id, Attempt.expires_at > utcnow())


def claim_callback(db, request, user_id, org_id, state):
    clear_legacy(request)
    if not isinstance(state, str) or not 20 <= len(state) <= 128:
        raise HTTPException(400, "Instagram connection could not be verified. Please start again.")
    attempt_id = db.execute(update(Attempt).where(*selector(request, user_id, org_id),
        Attempt.stage == "pending", Attempt.state_hash == digest(state)).values(stage="exchanging")
        .returning(Attempt.id)).scalar_one_or_none()
    db.commit()  # Consume before contacting Meta; no DB lock across the network.
    if not attempt_id:
        raise HTTPException(400, "Instagram connection expired or was already used. Please start again.")
    return attempt_id


def finish_discovery(db, attempt_id, accounts, token_data):
    payload = {"accounts": accounts, "access_token": token_data["access_token"],
               "expires_at": token_data["expires_at"].isoformat() if token_data.get("expires_at") else None}
    encrypted = cipher().encrypt(json.dumps(payload).encode()).decode()
    result = db.execute(update(Attempt).where(Attempt.id == attempt_id, Attempt.stage == "exchanging",
        Attempt.expires_at > utcnow()).values(stage="ready", encrypted_payload=encrypted))
    db.commit()
    if result.rowcount != 1:
        raise HTTPException(401, "Instagram connection expired. Please connect again.")


def abandon(db, request, attempt_id):
    db.execute(delete(Attempt).where(Attempt.id == attempt_id))
    db.commit()
    request.session.pop("ig_connection", None)


def read_discovery(db, request, user_id, org_id, *, lock=False):
    clear_legacy(request)
    query = db.query(Attempt).filter(*selector(request, user_id, org_id), Attempt.stage == "ready")
    if lock:
        query = query.with_for_update()
    row = query.first()
    if row is None:
        raise HTTPException(401, "Instagram connection expired. Please connect again.")
    try:
        payload = json.loads(cipher().decrypt(row.encrypted_payload.encode()))
    except (InvalidToken, ValueError, AttributeError):
        raise HTTPException(401, "Instagram connection expired. Please connect again.") from None
    return row, payload


def require_same_origin(request):
    expected = urlsplit(settings.public_base_url)
    origin = urlsplit(request.headers.get("origin", ""))
    if (origin.scheme, origin.netloc) != (expected.scheme, expected.netloc) or origin.path not in {"", "/"}:
        raise HTTPException(403, "Please select accounts from Sabeel Studio.")


def connect_selected(db, request, user, org_id, selections):
    require_same_origin(request)
    if not selections or len(selections) > 20 or len({i.ig_user_id for i in selections}) != len(selections):
        raise HTTPException(422, "Choose between one and 20 distinct Instagram accounts.")
    try:
        row, payload = read_discovery(db, request, user.id, org_id, lock=True)
        by_id = {a["ig_user_id"]: a for a in payload["accounts"]}
        if any(i.ig_user_id not in by_id or i.page_id != by_id[i.ig_user_id]["fb_page_id"] for i in selections):
            raise HTTPException(422, "An account selection has changed. Please choose again.")
        # Serialize account upserts across separate handoffs in this workspace.
        db.query(Org).filter(Org.id == org_id).with_for_update().one()
        ids = []
        for item in selections:
            selected = by_id[item.ig_user_id]
            account = db.query(IGAccount).filter(IGAccount.org_id == org_id,
                IGAccount.ig_user_id == item.ig_user_id).first()
            if account is None:
                account = IGAccount(org_id=org_id, ig_user_id=item.ig_user_id)
                db.add(account)
            account.name = selected.get("name") or selected.get("username") or "Instagram Account"
            account.username = selected.get("username")
            account.profile_picture_url = selected.get("profile_picture_url")
            account.fb_page_id = selected["fb_page_id"]
            account.access_token = payload["access_token"]
            account.expires_at = datetime.fromisoformat(payload["expires_at"]) if payload.get("expires_at") else None
            account.active = True
            db.flush()
            ids.append(account.id)
        user.has_connected_instagram = True
        db.delete(row)  # Selection is one use, committed together with the accounts.
        db.commit()
    except Exception:
        db.rollback()
        raise
    request.session.pop("ig_connection", None)
    return ids
