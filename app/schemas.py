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
    content_item_id: int | None = None

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

    # New Library fields
    use_content_library: bool
    avoid_repeat_days: int
    content_type: str | None
    include_arabic: bool
    image_mode: str
    posting_mode: str
    approval_mode: str

    # Hadith Enrichment fields
    enrich_with_hadith: bool
    hadith_topic: str | None
    hadith_append_style: str
    hadith_max_len: int
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
    
    # New Library fields
    use_content_library: bool = True
    avoid_repeat_days: int = 30
    content_type: str | None = None
    include_arabic: bool = False
    post_time_local: str | None = None
    timezone: str | None = None
    enabled: bool = False

    # Hadith Enrichment fields
    enrich_with_hadith: bool = False
    hadith_topic: str | None = None
    hadith_append_style: str = "short"
    hadith_max_len: int = 450

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
    
    use_content_library: bool | None = None
    avoid_repeat_days: int | None = None
    content_type: str | None = None
    include_arabic: bool | None = None
    post_time_local: str | None = None
    timezone: str | None = None
    enabled: bool | None = None

    # Hadith Enrichment fields
    enrich_with_hadith: bool | None = None
    hadith_topic: str | None = None
    hadith_append_style: str | None = None
    hadith_max_len: int | None = None

class ContentItemOut(BaseModel):
    id: int
    org_id: int
    type: str
    title: str | None
    text_en: str
    text_ar: str | None
    source_name: str | None
    reference: str | None
    url: str | None
    grade: str | None
    topics: list[str]
    language: str
    enabled: bool
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True

class ContentItemCreate(BaseModel):
    type: str = "hadith"
    title: str | None = None
    text_en: str
    text_ar: str | None = None
    source_name: str | None = None
    reference: str | None = None
    url: str | None = None
    grade: str | None = None
    topics: list[str] = Field(default_factory=list)
    language: str = "english"
    enabled: bool = True

class ContentItemUpdate(BaseModel):
    type: str | None = None
    title: str | None = None
    text_en: str | None = None
    text_ar: str | None = None
    source_name: str | None = None
    reference: str | None = None
    url: str | None = None
    grade: str | None = None
    topics: list[str] | None = None
    language: str | None = None
    enabled: bool | None = None