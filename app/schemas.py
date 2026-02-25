from pydantic import BaseModel, Field, validator
from datetime import datetime
from typing import Any

class UserCreate(BaseModel):
    name: str
    email: str
    password: str

class OrgOut(BaseModel):
    id: int
    name: str
    created_at: datetime
    class Config:
        from_attributes = True

class IGAccountOut(BaseModel):
    id: int
    org_id: int
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
    media_asset_id: int | None = None
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

class ContentProfileOut(BaseModel):
    id: int
    org_id: int
    name: str
    niche_category: str | None
    focus_description: str | None
    content_goals: str | None
    tone_style: str | None
    language: str
    allowed_topics: list[str] | None
    banned_topics: list[str] | None
    source_mode: str
    source_urls: list[str] | None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class ContentProfileCreate(BaseModel):
    name: str
    niche_category: str | None = None
    focus_description: str | None = None
    content_goals: str | None = None
    tone_style: str | None = None
    language: str = "english"
    allowed_topics: list[str] | None = None
    banned_topics: list[str] | None = None
    source_mode: str = "manual"
    source_urls: list[str] | None = None

class ContentProfileUpdate(BaseModel):
    name: str | None = None
    niche_category: str | None = None
    focus_description: str | None = None
    content_goals: str | None = None
    tone_style: str | None = None
    language: str | None = None
    allowed_topics: list[str] | None = None
    banned_topics: list[str] | None = None
    source_mode: str | None = None
    source_urls: list[str] | None = None

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

    # New Content Focus fields
    content_profile_id: int | None = None
    creativity_level: int = 3
    content_seed: str | None = None
    content_seed_mode: str = "none"
    content_seed_text: str | None = None

    # New Library fields
    use_content_library: bool
    avoid_repeat_days: int
    content_type: str | None
    include_arabic: bool
    image_mode: str
    posting_mode: str
    approval_mode: str

    # Media Library fields
    media_asset_id: int | None = None
    media_tag_query: list[str] | None = None
    media_rotation_mode: str | None = None

    @validator("media_tag_query", pre=True)
    def parse_media_tag_query(cls, v):
        if isinstance(v, str):
            try:
                import json
                return json.loads(v)
            except:
                return []
        return v

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
    
    content_profile_id: int | None = None
    creativity_level: int = 3
    content_seed: str | None = None
    content_seed_mode: str = "none"
    content_seed_text: str | None = None
    
    # New Library fields
    use_content_library: bool = True
    avoid_repeat_days: int = 30
    content_type: str | None = None
    include_arabic: bool = False
    post_time_local: str | None = None
    timezone: str | None = None
    enabled: bool = False

    media_asset_id: int | None = None
    media_tag_query: list[str] | None = None
    media_rotation_mode: str = "random"

    @validator("media_tag_query", pre=True)
    def parse_media_tag_query(cls, v):
        if isinstance(v, str):
            try:
                import json
                return json.loads(v)
            except:
                return []
        return v

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
    
    content_profile_id: int | None = None
    creativity_level: int | None = None
    content_seed: str | None = None
    content_seed_mode: str | None = None
    content_seed_text: str | None = None
    
    use_content_library: bool | None = None
    avoid_repeat_days: int | None = None
    content_type: str | None = None
    include_arabic: bool | None = None
    post_time_local: str | None = None
    timezone: str | None = None
    enabled: bool | None = None

    media_asset_id: int | None = None
    media_tag_query: list[str] | None = None
    media_rotation_mode: str | None = None

    @validator("media_tag_query", pre=True)
    def parse_media_tag_query(cls, v):
        if isinstance(v, str):
            try:
                import json
                return json.loads(v)
            except:
                return []
        return v

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

class MediaAssetOut(BaseModel):
    id: int
    org_id: int
    ig_account_id: int | None = None
    url: str
    storage_path: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime

    @validator("tags", pre=True)
    def parse_tags(cls, v):
        if isinstance(v, str):
            try:
                import json
                return json.loads(v)
            except:
                return []
        return v

    class Config:
        from_attributes = True

class MediaAssetCreate(BaseModel):
    ig_account_id: int | None = None
    url: str
    storage_path: str | None = None
    tags: list[str] = Field(default_factory=list)

    @validator("tags", pre=True)
    def parse_tags(cls, v):
        if isinstance(v, str):
            try:
                import json
                return json.loads(v)
            except:
                return []
        return v

class SourceChunkOut(BaseModel):
    id: int
    org_id: int
    document_id: int
    chunk_index: int
    chunk_text: str
    chunk_metadata: dict | None = None
    created_at: datetime
    class Config:
        from_attributes = True

class SourceDocumentOut(BaseModel):
    id: int
    org_id: int
    title: str
    source_type: str
    original_url: str | None = None
    file_path: str | None = None
    created_at: datetime
    chunks: list[SourceChunkOut] = []
    class Config:
        from_attributes = True

class SourceDocumentCreate(BaseModel):
    title: str
    source_type: str
    original_url: str | None = None
    raw_text: str | None = None

class PostUpdate(BaseModel):
    caption: str | None = None
    hashtags: list[str] | None = None
    alt_text: str | None = None
    scheduled_time: datetime | None = None
    status: str | None = None
    source_text: str | None = None
    media_url: str | None = None
    media_asset_id: int | None = None
    flags: dict[str, Any] | None = None