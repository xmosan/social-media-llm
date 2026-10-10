# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

import hashlib
import hmac
from datetime import datetime, timedelta, timezone as dt_timezone
import jwt
import bcrypt
from fastapi import Request, HTTPException, Depends, status
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User, ApiKey
from app.config import settings
from app.security.tester_access import user_can_sign_in

ALGORITHM = "HS256"
# Hash of the public default API key used by the retired startup bootstrap.
# Reject it even if an old database row or environment setting still contains it.
RETIRED_BOOTSTRAP_KEY_HASH = "46aabbfbfc926e9847f4edf2948414a8f69c169c94825c4bfe2fe501ef032ee0"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8')[:72], hashed_password.encode('utf-8'))
    except ValueError:
        return False

def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8')[:72], bcrypt.gensalt()).decode('utf-8')

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(dt_timezone.utc) + expires_delta
    else:
        expire = datetime.now(dt_timezone.utc) + timedelta(days=7)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> User | None:
    # 1. Check HTTP-only Cookie
    token = request.cookies.get("access_token")
    
    # 2. Check Authorization Header (Bearer) if cookie not present
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split("Bearer ")[1]
            
    # Compatibility mode for automation runners using X-API-Key
    if not token:
        x_api_key = request.headers.get("X-API-Key")
        if x_api_key:
            hashed_key = hashlib.sha256(x_api_key.encode()).hexdigest()
            if hashed_key == RETIRED_BOOTSTRAP_KEY_HASH:
                return None
            # A shared service key must never impersonate the platform owner.
            if settings.admin_api_key and hmac.compare_digest(
                x_api_key.encode(), settings.admin_api_key.encode()
            ):
                return None
            
            # Legacy API key lookup
            api_key_record = db.query(ApiKey).filter(
                ApiKey.key_hash == hashed_key, 
                ApiKey.revoked_at == None
            ).first()
            
            if api_key_record:
                # An organization key is a scoped service credential, not a user.
                # Only get_current_org_id consumes this scope; user/admin routes
                # must never inherit a member's identity or privileges.
                request.state.api_key_org_id = api_key_record.org_id
        return None

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not isinstance(user_id, str) or len(user_id) > 10 or not user_id.isascii() or not user_id.isdecimal():
            return None
        user_id = int(user_id)
        # User IDs are PostgreSQL signed integers. Reject invalid subjects before SQL.
        if not 0 < user_id <= 2_147_483_647:
            return None
    except jwt.PyJWTError:
        return None
        
    user = db.query(User).filter(User.id == user_id).first()
    if not user_can_sign_in(user):
        return None
        
    return user

def require_user(user: User | None = Depends(get_current_user)) -> User:
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

def optional_user(user: User | None = Depends(get_current_user)) -> User | None:
    return user


def clear_legacy_domain_cookie(response):
    from urllib.parse import urlparse
    domain = urlparse(settings.public_base_url).hostname
    if domain and domain not in {"localhost", "127.0.0.1"}:
        response.delete_cookie("access_token", domain=domain, path="/", httponly=True, secure=True, samesite="lax")
