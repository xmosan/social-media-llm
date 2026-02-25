import hashlib
from typing import Annotated
from datetime import datetime, timedelta, timezone as dt_timezone
import jwt
import bcrypt
from fastapi import Request, HTTPException, Depends, Header, Cookie, status
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User, ApiKey, OrgMember
from app.config import settings

ALGORITHM = "HS256"

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
            # Superadmin bypass
            if settings.admin_api_key and x_api_key == settings.admin_api_key:
                superadmin = db.query(User).filter(User.is_superadmin == True).first()
                if superadmin:
                    return superadmin
            
            # Legacy API key lookup
            hashed_key = hashlib.sha256(x_api_key.encode()).hexdigest()
            api_key_record = db.query(ApiKey).filter(
                ApiKey.key_hash == hashed_key, 
                ApiKey.revoked_at == None
            ).first()
            
            if api_key_record:
                request.state.api_key_org_id = api_key_record.org_id
                # Find any user in that org to act as the authenticated user
                org_member = db.query(OrgMember).filter(OrgMember.org_id == api_key_record.org_id).first()
                if org_member:
                    return db.query(User).filter(User.id == org_member.user_id).first()
                
                # Fallback to superadmin if org has no users
                superadmin = db.query(User).filter(User.is_superadmin == True).first()
                return superadmin
        return None

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            return None
    except jwt.PyJWTError:
        return None
        
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or not user.is_active:
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
