from pydantic import BaseModel, EmailStr
from typing import Optional

class ContactMessageRequest(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    subject: Optional[str] = None
    message: str
    source: str = "contact_form"
