from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any

class OrgOut(BaseModel):
    id: int
    name: str
    created_at: datetime
    class Config:
        from_attributes = True

class IGAccountOut(BaseModel):
    id: int
    name: str
    ig_user_id: str
    active: bool
    timezone: str
    daily_post_time: str
    created_at: datetime
    class Config:
        from_attributes = True

class PostOut(BaseModel):
    id: int
    org_id: int
    ig_account_id: int
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
    scheduled_time: datetime | None = None
    approve_anyway: bool = False

class GenerateOut(BaseModel):
    caption: str
    hashtags: list[str]
    alt_text: str
    flags: dict
    status: str

class AccountCreate(BaseModel):
    name: str
    ig_user_id: str
    access_token: str
    timezone: str = "America/Detroit"
    daily_post_time: str = "09:00"

class AccountUpdate(BaseModel):
    name: str | None = None
    ig_user_id: str | None = None
    access_token: str | None = None
    timezone: str | None = None
    daily_post_time: str | None = None
    active: bool | None = None

class TopicAutomationOut(BaseModel):
    id: int
    org_id: int
    ig_account_id: int
    name: str
    topic_prompt: str
    style_preset: str
    tone: str = "medium"
    language: str = "english"
    banned_phrases: list[str] = Field(default_factory=list)
    enabled: bool
    post_time_local: str | None = None
    last_run_at: datetime | None = None
    last_error: str | None = None
    class Config:
        from_attributes = True

class TopicAutomationCreate(BaseModel):
    ig_account_id: int
    name: str
    topic_prompt: str
    style_preset: str = "islamic_reminder"
    tone: str = "medium" # short, medium, long
    language: str = "english" # english, arabic_mix
    banned_phrases: list[str] = Field(default_factory=list)
    posting_mode: str = "schedule"
    approval_mode: str = "auto_approve"
    image_mode: str = "reuse_last_upload"
    post_time_local: str | None = None
    timezone: str | None = None
    enabled: bool = False

class TopicAutomationUpdate(BaseModel):
    name: str | None = None
    topic_prompt: str | None = None
    style_preset: str | None = None
    tone: str | None = None
    language: str | None = None
    banned_phrases: list[str] | None = None
    posting_mode: str | None = None
    approval_mode: str | None = None
    image_mode: str | None = None
    post_time_local: str | None = None
    timezone: str | None = None
    enabled: bool | None = None