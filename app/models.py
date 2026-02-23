from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, ForeignKey, Boolean, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()

class Org(Base):
    __tablename__ = "orgs"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    members = relationship("OrgMember", back_populates="org")
    api_keys = relationship("ApiKey", back_populates="org")
    ig_accounts = relationship("IGAccount", back_populates="org")
    posts = relationship("Post", back_populates="org")
    content_items = relationship("ContentItem", back_populates="org")
    content_usages = relationship("ContentUsage", back_populates="org")
    media_assets = relationship("MediaAsset", back_populates="org")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=True)
    name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    is_superadmin = Column(Boolean, default=False)
    onboarding_complete = Column(Boolean, default=False)
    google_id = Column(String, unique=True, index=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    memberships = relationship("OrgMember", back_populates="user")

class OrgMember(Base):
    __tablename__ = "org_members"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String, default="member") # owner, admin, member
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    org = relationship("Org", back_populates="members")
    user = relationship("User", back_populates="memberships")

    __table_args__ = (UniqueConstraint("org_id", "user_id", name="uq_org_user"),)

class ApiKey(Base):
    __tablename__ = "api_keys"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False)
    name = Column(String, nullable=False)
    key_hash = Column(String, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    org = relationship("Org", back_populates="api_keys")

class IGAccount(Base):
    __tablename__ = "ig_accounts"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False)
    name = Column(String, nullable=False)
    
    ig_user_id = Column(String, nullable=False)
    access_token = Column(Text, nullable=False)
    active = Column(Boolean, default=True)
    
    timezone = Column(String, default="America/Detroit")
    daily_post_time = Column(String, default="09:00") 

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    org = relationship("Org", back_populates="ig_accounts")
    posts = relationship("Post", back_populates="ig_account")
    content_usages = relationship("ContentUsage", back_populates="ig_account")
    media_assets = relationship("MediaAsset", back_populates="ig_account")

class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    ig_account_id = Column(Integer, ForeignKey("ig_accounts.id"), nullable=False, index=True)

    # NEW: Link to automation source
    is_auto_generated = Column(Boolean, default=False)
    automation_id = Column(Integer, ForeignKey("topic_automations.id"), nullable=True)

    status = Column(String, nullable=False, default="submitted", index=True)
    source_type = Column(String, nullable=False, default="form")
    source_text = Column(Text, nullable=True)

    # NEW: Link to Content Library
    content_item_id = Column(Integer, ForeignKey("content_items.id"), nullable=True)
    media_asset_id = Column(Integer, ForeignKey("media_assets.id"), nullable=True)

    # MUST be a public https URL for Instagram publishing
    media_url = Column(Text, nullable=True)

    caption = Column(Text, nullable=True)
    hashtags = Column(JSON, nullable=True)
    alt_text = Column(Text, nullable=True)

    flags = Column(JSON, nullable=False, default=dict)

    scheduled_time = Column(DateTime(timezone=True), nullable=True)
    published_time = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    org = relationship("Org", back_populates="posts")
    ig_account = relationship("IGAccount", back_populates="posts")
    automation = relationship("TopicAutomation", back_populates="generated_posts")
    content_item = relationship("ContentItem", back_populates="posts")
    media_asset = relationship("MediaAsset", back_populates="posts")
    content_usage = relationship("ContentUsage", back_populates="post", uselist=False)

class ContentProfile(Base):
    __tablename__ = "content_profiles"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    
    name = Column(String, nullable=False) # e.g. "Fitness Brand"
    niche_category = Column(String, nullable=True) # e.g. "fitness"
    focus_description = Column(Text, nullable=True)
    content_goals = Column(Text, nullable=True)
    tone_style = Column(String, nullable=True)
    language = Column(String, default="english")
    
    allowed_topics = Column(JSON, nullable=True) # list
    banned_topics = Column(JSON, nullable=True) # list
    
    source_mode = Column(String, default="manual")
    source_urls = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    org = relationship("Org")
    automations = relationship("TopicAutomation", back_populates="content_profile")

class TopicAutomation(Base):
    __tablename__ = "topic_automations"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    ig_account_id = Column(Integer, ForeignKey("ig_accounts.id"), nullable=False, index=True)
    
    name = Column(String, nullable=False)
    topic_prompt = Column(Text, nullable=False)
    style_preset = Column(String, nullable=False, default="islamic_reminder")
    custom_style_instructions = Column(Text, nullable=True)
    
    tone = Column(String, default="medium") # short, medium, long
    language = Column(String, default="english") # english, arabic_mix
    banned_phrases = Column(JSON, nullable=True) # JSON array of strings
    
    include_hashtags = Column(Boolean, default=True)
    hashtag_set = Column(JSON, nullable=True) # JSON array of strings
    include_arabic_phrase = Column(Boolean, default=True)
    
    posting_mode = Column(String, default="schedule") # "publish_now" | "schedule"
    approval_mode = Column(String, default="auto_approve") # "auto_approve" | "needs_manual_approve"
    image_mode = Column(String, default="reuse_last_upload") # "reuse_last_upload" | "none_placeholder" | "quote_card"
    
    # NEW: Content Focus Engine
    content_profile_id = Column(Integer, ForeignKey("content_profiles.id"), nullable=True)
    creativity_level = Column(Integer, default=3) # 1-5
    
    # NEW: Content Library Settings
    use_content_library = Column(Boolean, default=True)
    avoid_repeat_days = Column(Integer, default=30)
    content_type = Column(String, nullable=True) # "hadith", "quote", etc.
    include_arabic = Column(Boolean, default=False)
    
    post_time_local = Column(String, nullable=True) # "HH:MM"
    timezone = Column(String, nullable=True) 
    
    enabled = Column(Boolean, default=False)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    last_post_id = Column(Integer, nullable=True)
    last_error = Column(Text, nullable=True)
    
    enrich_with_hadith = Column(Boolean, default=False)
    hadith_topic = Column(String, nullable=True)
    hadith_source_id = Column(Integer, ForeignKey("content_sources.id"), nullable=True)
    hadith_append_style = Column(String, default="short") # "short" | "medium"
    hadith_max_len = Column(Integer, default=450)

    # NEW: Media Library Fields
    media_asset_id = Column(Integer, ForeignKey("media_assets.id"), nullable=True)
    media_tag_query = Column(JSON, nullable=True) # e.g. ["ramadan","masjid"]
    media_rotation_mode = Column(String, default="random") # "random" | "round_robin"

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    org = relationship("Org")
    ig_account = relationship("IGAccount")
    generated_posts = relationship("Post", back_populates="automation")
    content_usages = relationship("ContentUsage", back_populates="automation")
    media_asset = relationship("MediaAsset")
    content_profile = relationship("ContentProfile", back_populates="automations")

class ContentItem(Base):
    __tablename__ = "content_items"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False)
    
    type = Column(String, default="hadith") # hadith, quote, verse, reminder
    title = Column(String, nullable=True)
    text_en = Column(Text, nullable=False)
    text_ar = Column(Text, nullable=True)
    source_name = Column(String, nullable=True)
    reference = Column(String, nullable=True)
    url = Column(Text, nullable=True)
    grade = Column(String, nullable=True)
    
    topics = Column(JSON, nullable=False, default=list) # List of normalized strings
    language = Column(String, default="english")
    enabled = Column(Boolean, default=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    org = relationship("Org", back_populates="content_items")
    posts = relationship("Post", back_populates="content_item")
    usages = relationship("ContentUsage", back_populates="content_item")

class ContentUsage(Base):
    __tablename__ = "content_usages"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False)
    ig_account_id = Column(Integer, ForeignKey("ig_accounts.id"), nullable=False)
    automation_id = Column(Integer, ForeignKey("topic_automations.id"), nullable=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=True)
    content_item_id = Column(Integer, ForeignKey("content_items.id"), nullable=False)
    
    used_at = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(String) # selected, published, failed

    org = relationship("Org", back_populates="content_usages")
    ig_account = relationship("IGAccount", back_populates="content_usages")
    automation = relationship("TopicAutomation", back_populates="content_usages")
    post = relationship("Post", back_populates="content_usage")
    content_item = relationship("ContentItem", back_populates="usages")

class ContentSource(Base):
    __tablename__ = "content_sources"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False) # e.g. "Sunnah.com"
    type = Column(String, default="sunnah")
    base_url = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class SourceItem(Base):
    __tablename__ = "source_items"
    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("content_sources.id"), nullable=False)
    topic = Column(String, index=True, nullable=False)
    content_text = Column(Text, nullable=False)
    reference = Column(String, nullable=True)
    url = Column(Text, nullable=True)
    hash = Column(String, unique=True, index=True) # For deduping
    
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class MediaAsset(Base):
    __tablename__ = "media_assets"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False)
    ig_account_id = Column(Integer, ForeignKey("ig_accounts.id"), nullable=True)
    
    url = Column(Text, nullable=False) # Public path
    storage_path = Column(Text, nullable=True) # Internal path
    tags = Column(JSON, nullable=False, default=list) # e.g. ["nature", "islamic"]
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    org = relationship("Org", back_populates="media_assets")
    ig_account = relationship("IGAccount", back_populates="media_assets")
    posts = relationship("Post", back_populates="media_asset")