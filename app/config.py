# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"
        hide_input_in_errors = True

    database_url: str = Field(default="", repr=False, env="DATABASE_URL")
    run_startup_migrations: bool = False
    scheduler_enabled: bool = True
    timezone: str = Field(default="America/Detroit", env="TIMEZONE")
    uploads_dir: str = Field(default="uploads", env="UPLOADS_DIR")

    @classmethod
    def resolve_abs_path(cls, v: str) -> str:
        import os
        if os.path.isabs(v):
            return v
        
        # PRODUCTION SHIELD: If running in Railway/App Docker root
        if os.path.exists("/app"):
            return os.path.join("/app", v)

        # Resolve relative to project root (where app/ is)
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, v)

    # In Pydantic v2 Settings, we can use a validator or a computed field.
    # To keep it simple and compatible, we'll override the init or use a Pydantic Hook.
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        import os
        self.uploads_dir = self.resolve_abs_path(self.uploads_dir)
        print("\n" + "!"*64)
        print(f"🚀 [INIT] ABSOLUTE MEDIA SHIELD ACTIVE")
        print(f"!!! [RESOLVED UPLOADS DIR]: {self.uploads_dir}")
        print(f"!!! [CURRENT WORKING DIR ]: {os.getcwd()}")
        print("!"*64 + "\n")
        # Hadith API startup log (never print key value)
        if self.hadith_api_key:
            print("[HADITH] sunnah.now configured (key loaded)")
        else:
            print("[HADITH] sunnah.now unavailable (key missing; no provider fallback)")
        
        if self.hadith_in_automations_enabled:
            print("[HADITH_AUTOMATION] feature_flag_enabled=true")

    # Centralized Public Base URL (Production Custom Domain)
    public_base_url: str = Field(
        default="https://app.sabeelstudio.com", 
        env="PUBLIC_APP_URL"
    )
    
    # Feature Flags
    coming_soon_mode: bool = Field(default=True, env="COMING_SOON_MODE")

    ig_access_token: str | None = Field(default=None, env="IG_ACCESS_TOKEN")
    ig_user_id: str | None = Field(default=None, env="IG_USER_ID")
    fb_page_id: str | None = Field(default=None, env="FB_PAGE_ID")

    admin_api_key: str | None = Field(default=None, env="ADMIN_API_KEY")
    openai_api_key: str | None = Field(default=None, env="OPENAI_API_KEY")
    gemini_api_key: str | None = Field(default=None)

    # Writing quality and small utility tasks have independent, replaceable models.
    openai_text_model: str = "gpt-6-astra"
    openai_utility_model: str = "gpt-6-luna"
    openai_text_reasoning_effort: str = "low"
    openai_utility_reasoning_effort: str = "none"
    text_generation_timeout_seconds: int = Field(default=45, ge=5, le=120)

    @field_validator("openai_text_model", "openai_utility_model")
    @classmethod
    def validate_text_model(cls, value: str) -> str:
        value = value.strip()
        if not value or any(c.isspace() for c in value):
            raise ValueError("Text model must be a nonempty model ID")
        return value

    @field_validator("openai_text_reasoning_effort", "openai_utility_reasoning_effort")
    @classmethod
    def validate_text_reasoning_effort(cls, value: str) -> str:
        if value not in {"none", "low", "medium", "high"}:
            raise ValueError("Text reasoning effort must be none, low, medium or high")
        return value

    @model_validator(mode="after")
    def validate_text_model_effort(self):
        for model, effort in ((self.openai_text_model, self.openai_text_reasoning_effort),
                              (self.openai_utility_model, self.openai_utility_reasoning_effort)):
            if model.startswith(("gpt-6-astra", "gpt-6.1-sol")) and effort == "none":
                raise ValueError("GPT-6 Astra and GPT-6.1 Sol require at least low reasoning effort")
        return self

    # Sabeel Vision: explicit, replaceable models; legacy engine labels are aliases.
    openai_image_model: str = "gpt-image-2.5-sunburst"
    openai_image_fallback_model: str = "gpt-image-2.5-flare"
    openai_image_quality: str = "medium"
    image_generation_timeout_seconds: int = Field(default=120, ge=10, le=180)

    @field_validator("openai_image_model", "openai_image_fallback_model")
    @classmethod
    def validate_image_model(cls, value: str) -> str:
        value = value.strip()
        if value and not value.startswith("gpt-image-"):
            raise ValueError("Image models must use the supported GPT Image API")
        return value

    @field_validator("openai_image_quality")
    @classmethod
    def validate_image_quality(cls, value: str) -> str:
        if value not in {"low", "medium", "high"}:
            raise ValueError("OPENAI_IMAGE_QUALITY must be low, medium or high")
        return value

    @field_validator("openai_image_model")
    @classmethod
    def require_primary_image_model(cls, value: str) -> str:
        if not value:
            raise ValueError("OPENAI_IMAGE_MODEL is required")
        return value

    # Auth & security
    # One explicitly configured key signs both login tokens and OAuth sessions.
    secret_key: str = Field(
        validation_alias=AliasChoices("SECRET_KEY", "JWT_SECRET", "secret_key"),
        repr=False,
    )
    bootstrap_superadmin: bool = False
    superadmin_email: str | None = Field(default=None, env="SUPERADMIN_EMAIL")
    superadmin_password: str | None = Field(default=None, env="SUPERADMIN_PASSWORD", repr=False)

    @field_validator("secret_key")
    @classmethod
    def validate_signing_key(cls, value: str) -> str:
        if len(value.strip()) < 32:
            raise ValueError("SECRET_KEY (or JWT_SECRET) must contain at least 32 characters")
        return value

    @model_validator(mode="after")
    def validate_bootstrap_credentials(self):
        if self.bootstrap_superadmin:
            if not self.superadmin_email or not self.superadmin_email.strip():
                raise ValueError("SUPERADMIN_EMAIL is required when BOOTSTRAP_SUPERADMIN is enabled")
            if not self.superadmin_password or len(self.superadmin_password.strip()) < 12:
                raise ValueError("SUPERADMIN_PASSWORD must contain at least 12 characters when bootstrap is enabled")
        return self

    # Google OAuth
    google_client_id: str | None = Field(default=None, env="GOOGLE_CLIENT_ID")
    google_client_secret: str | None = Field(default=None, env="GOOGLE_CLIENT_SECRET")
    google_redirect_uri: str | None = Field(default=None, env="GOOGLE_REDIRECT_URI")

    # Meta (Facebook) OAuth
    fb_app_id: str | None = Field(default=None, validation_alias="META_APP_ID")
    fb_app_secret: str | None = Field(default=None, validation_alias="META_APP_SECRET")
    fb_redirect_uri: str | None = Field(default=None, validation_alias="META_REDIRECT_URI")

    # Backups & Reliability
    backup_storage_type: str = Field(default="local", env="BACKUP_STORAGE_TYPE")
    s3_access_key: str | None = Field(default=None, repr=False, env="S3_ACCESS_KEY")
    s3_secret_key: str | None = Field(default=None, repr=False, env="S3_SECRET_KEY")
    s3_bucket_name: str | None = Field(default=None, env="S3_BUCKET_NAME")
    s3_region: str | None = Field(default=None, env="S3_REGION")
    s3_endpoint_url: str | None = None
    s3_addressing_style: str = "auto"

    @field_validator("s3_addressing_style")
    @classmethod
    def validate_s3_addressing_style(cls, value: str) -> str:
        if value not in {"auto", "virtual", "path"}:
            raise ValueError("S3_ADDRESSING_STYLE must be auto, virtual or path")
        return value
    env_backup_key: str | None = Field(default=None, env="ENV_BACKUP_KEY")
    primary_region: str | None = Field(default=None, env="PRIMARY_REGION")
    secondary_database_url: str | None = Field(default=None, env="SECONDARY_DATABASE_URL")

    # Observability (Axiom)
    axiom_token: str | None = Field(default=None, env="AXIOM_TOKEN")
    axiom_dataset: str | None = Field(default="social-media-llm", env="AXIOM_DATASET")
    axiom_org_id: str | None = Field(default=None, env="AXIOM_ORG_ID")
    axiom_url: str = Field(default="https://api.axiom.co", env="AXIOM_URL")

    # Quran Foundation API
    qf_client_id: str | None = Field(default=None, env="QF_CLIENT_ID")
    qf_client_secret: str | None = Field(default=None, env="QF_CLIENT_SECRET")
    qf_env: str = Field(default="prod", env="QF_ENV")

    # Hadith API
    # Canonical provider: sunnah.now. Missing configuration must not change providers.
    hadith_api_key: str | None = Field(default=None, env="HADITH_API_KEY")
    hadith_api_base_url: str = Field(
        default="https://api.sunnah.now",
        env="HADITH_API_BASE_URL"
    )
    # Phase 2 gate: Hadith in automations (enabled)
    hadith_in_automations_enabled: bool = Field(default=True, env="HADITH_IN_AUTOMATIONS_ENABLED")

    # Email Service (Resend)
    resend_api_key: str | None = Field(default=None, env="RESEND_API_KEY")
    resend_from_email: str | None = Field(default="onboarding@resend.dev", env="RESEND_FROM_EMAIL")
    support_autoreply_enabled: bool = Field(default=True, env="SUPPORT_AUTOREPLY_ENABLED")

settings = Settings()

def build_public_media_url(filename: str, local_path: str | None = None) -> str:
    """
    Standardized way to generate production-ready URLs for Instagram/Meta.

    If Cloudinary is configured and local_path is provided, the file is uploaded
    to Cloudinary and its CDN URL is returned. This guarantees Instagram's crawler
    can always reach the image.

    If Cloudinary is not configured, falls back to the existing Railway public URL.
    """
    import os

    # 1. Try Cloudinary first (preferred for Instagram compatibility)
    if local_path and os.path.exists(local_path):
        try:
            from app.services.cloudinary_service import upload_to_cloudinary
            cdn_url = upload_to_cloudinary(local_path)
            if cdn_url:
                return cdn_url
        except Exception as e:
            print(f"⚠️ [CONFIG] Cloudinary upload failed, falling back to local URL: {e}")

    # 2. Fallback: Railway / public domain URL
    base = settings.public_base_url.rstrip("/")

    if not base or "localhost" in base or "127.0.0.1" in base:
        print(f"⚠️ [CONFIG] Building media URL with local/missing base: {base}")
        railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "app.sabeelstudio.com")
        base = f"https://{railway_domain}"

    # Strip any leading slashes from filename
    filename = filename.lstrip("/")

    # If filename is already a full URL, return it
    if filename.startswith("http"):
        return filename

    return f"{base}/uploads/{filename}"
