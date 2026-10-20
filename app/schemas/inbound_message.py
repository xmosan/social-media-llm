from pydantic import BaseModel, EmailStr, Field
from typing import Optional

class ContactMessageRequest(BaseModel):
    email: EmailStr
    name: Optional[str] = Field(default=None, max_length=100)
    subject: Optional[str] = Field(default=None, max_length=200)
    message: str = Field(min_length=1, max_length=10000)
    source: str = Field(default="contact_form", max_length=100)
