from pydantic import BaseModel, EmailStr, Field
from typing import Optional

class WaitlistJoinRequest(BaseModel):
    email: EmailStr
    name: Optional[str] = Field(default=None, max_length=100)
    wants_updates: bool = True
    source: str = Field(default="homepage", max_length=100)
    
    # Optional UTM fields in payload
    utm_source: Optional[str] = Field(default=None, max_length=200)
    utm_medium: Optional[str] = Field(default=None, max_length=200)
    utm_campaign: Optional[str] = Field(default=None, max_length=200)
