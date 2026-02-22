from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User, OrgMember, Org
from app.schemas import UserCreate
from app.security.auth import verify_password, create_access_token, get_current_user, require_user, get_password_hash
from typing import Any

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login")
def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    from sqlalchemy import func
    user = db.query(User).filter(func.lower(User.email) == func.lower(form_data.username.strip())).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    access_token = create_access_token(data={"sub": str(user.id)})
    
    # Set HttpOnly cookie for web clients
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax",
        secure=True, # Should be True in production (HTTPS)
        max_age=7 * 24 * 60 * 60 # 7 days
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/register")
def register(
    user_in: UserCreate,
    response: Response,
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    # 1. Check if user already exists
    existing_user = db.query(User).filter(func.lower(User.email) == func.lower(user_in.email.strip())).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists."
        )

    # 2. Create the User
    new_user = User(
        email=user_in.email.strip(),
        name=user_in.name.strip(),
        password_hash=get_password_hash(user_in.password),
        is_active=True,
        is_superadmin=False
    )
    db.add(new_user)
    db.flush() # get user ID

    # 3. Auto-provision a default Workspace (Org)
    new_org = Org(name=f"{new_user.name}'s Workspace")
    db.add(new_org)
    db.flush() # get org ID

    # 4. Bind the user to the new workspace as owner
    membership = OrgMember(org_id=new_org.id, user_id=new_user.id, role="owner")
    db.add(membership)
    db.commit()

    # 5. Automatically log them in (Session Cookie)
    access_token = create_access_token(data={"sub": str(new_user.id)})
    
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax",
        secure=True,
        max_age=7 * 24 * 60 * 60 # 7 days
    )

    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/logout")
def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(
        key="access_token",
        httponly=True,
        samesite="lax",
        secure=True
    )
    return {"message": "Logged out successfully"}

@router.get("/me")
def get_current_user_profile(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    # Fetch orgs
    orgs = []
    if current_user.is_superadmin:
        all_orgs = db.query(Org).all()
        orgs = [{"id": o.id, "name": o.name, "role": "superadmin"} for o in all_orgs]
    else:
        memberships = db.query(OrgMember).filter(OrgMember.user_id == current_user.id).all()
        for m in memberships:
            org = db.query(Org).filter(Org.id == m.org_id).first()
            if org:
                orgs.append({"id": org.id, "name": org.name, "role": m.role})
    
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "is_superadmin": current_user.is_superadmin,
        "orgs": orgs
    }
