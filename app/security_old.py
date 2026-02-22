import hashlib
from fastapi import Header, HTTPException, Depends, Request
from sqlalchemy.orm import Session
from .db import get_db
from .models import ApiKey
from datetime import datetime, timezone

def hash_api_key(api_key: str) -> str:
    """Hash an API key using SHA256."""
    return hashlib.sha256(api_key.encode()).hexdigest()

def require_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db)
) -> int:
    """
    Validate the X-API-Key header against the database.
    Sets org_id in request.state on success.
    """
    if not x_api_key:
        raise HTTPException(status_code=401, detail="X-API-Key header missing")

    hashed_key = hash_api_key(x_api_key)
    
    # Query API key and check if revoked
    api_key_record = db.query(ApiKey).filter(
        ApiKey.key_hash == hashed_key,
        ApiKey.revoked_at == None
    ).first()

    if not api_key_record:
        raise HTTPException(status_code=401, detail="Invalid or revoked API key")

    # Update last used timestamp
    api_key_record.last_used_at = datetime.now(timezone.utc)
    db.commit()

    # Store org_id in request state for downstream routes
    request.state.org_id = api_key_record.org_id
    
    return api_key_record.org_id