# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Org
from ..security.rbac import get_current_org_id
from ..schemas import OrgOut

router = APIRouter(prefix="/orgs", tags=["orgs"])

@router.get("/me", response_model=OrgOut)
def get_current_org(
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    """Return the organization associated with the API key."""
    org = db.get(Org, org_id)
    return org
