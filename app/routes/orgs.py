from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Org
from ..security import require_api_key
from ..schemas import OrgOut

router = APIRouter(prefix="/orgs", tags=["orgs"])

@router.get("/me", response_model=OrgOut)
def get_current_org(
    db: Session = Depends(get_db),
    org_id: int = Depends(require_api_key)
):
    """Return the organization associated with the API key."""
    org = db.get(Org, org_id)
    return org
