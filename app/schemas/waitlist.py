from pydantic import BaseModel, EmailStr
from typing import Optional

class WaitlistJoinRequest(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    wants_updates: bool = True
    source: str = "homepage"
    
    # Optional UTM fields in payload
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
