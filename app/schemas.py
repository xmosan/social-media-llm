from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any

class PostOut(BaseModel):
    id: int
    status: str
    source_type: str
    source_text: str | None = None
    media_url: str | None = None

    caption: str | None = None
    hashtags: list[str] | None = None
    alt_text: str | None = None

    flags: dict[str, Any] = Field(default_factory=dict)

    scheduled_time: datetime | None = None
    published_time: datetime | None = None

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ApproveIn(BaseModel):
    scheduled_time: datetime
    approve_anyway: bool = False

class GenerateOut(BaseModel):
    caption: str
    hashtags: list[str]
    alt_text: str
    flags: dict
    status: str