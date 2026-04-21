# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    database_url: str = Field(default="sqlite:///./saas.db", env="DATABASE_URL")
    timezone: str = Field(default="America/Detroit", env="TIMEZONE")
    uploads_dir: str = Field(default="uploads", env="UPLOADS_DIR")

    @classmethod
    def resolve_abs_path(cls, v: str) -> str:
        import os
        if os.path.isabs(v):
            return v
        # Resolve relative to project root (where app/ is)
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, v)

    # In Pydantic v2 Settings, we can use a validator or a computed field.
    # To keep it simple and compatible, we'll override the init or use a Pydantic Hook.
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.uploads_dir = self.resolve_abs_path(self.uploads_dir)

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

    # Auth & security
    secret_key: str = Field(default="change-me-in-production-for-jwt", env="SECRET_KEY")
    superadmin_email: str | None = Field(default=None, env="SUPERADMIN_EMAIL")
    superadmin_password: str | None = Field(default=None, env="SUPERADMIN_PASSWORD")

    # Google OAuth
    google_client_id: str | None = Field(default=None, env="GOOGLE_CLIENT_ID")
    google_client_secret: str | None = Field(default=None, env="GOOGLE_CLIENT_SECRET")
    google_redirect_uri: str | None = Field(default=None, env="GOOGLE_REDIRECT_URI")

    # Meta (Facebook) OAuth
    fb_app_id: str | None = Field(default=None, env="META_APP_ID")
    fb_app_secret: str | None = Field(default=None, env="META_APP_SECRET")
    fb_redirect_uri: str | None = Field(default=None, env="META_REDIRECT_URI")

    # Backups & Reliability
    backup_storage_type: str = Field(default="local", env="BACKUP_STORAGE_TYPE")
    s3_access_key: str | None = Field(default=None, env="S3_ACCESS_KEY")
    s3_secret_key: str | None = Field(default=None, env="S3_SECRET_KEY")
    s3_bucket_name: str | None = Field(default=None, env="S3_BUCKET_NAME")
    s3_region: str | None = Field(default=None, env="S3_REGION")
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

    # Email Service (Resend)
    resend_api_key: str | None = Field(default=None, env="RESEND_API_KEY")
    resend_from_email: str | None = Field(default="onboarding@resend.dev", env="RESEND_FROM_EMAIL")
    support_autoreply_enabled: bool = Field(default=True, env="SUPPORT_AUTOREPLY_ENABLED")

settings = Settings()

def build_public_media_url(filename: str) -> str:
    """
    Constructs a fully qualified public HTTPS URL for Instagram publishing.
    Ensures safe fallback formatting to prevent localhost rejections.
    """
    import os
    base = (settings.public_base_url or "").rstrip("/")
    
    # If running locally without ngrok, fallback to production domain to avoid instant 400 errors from Meta
    # Meta will still fail the download gracefully if the file isn't pushed to production, but the API payload will be valid
    if not base or "localhost" in base or "127.0.0.1" in base:
        railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "app.sabeelstudio.com")
        base = f"https://{railway_domain}"
        
    # Strip any leading slashes from filename
    filename = filename.lstrip("/")
    
    # If filename is already a full URL, return it
    if filename.startswith("http"):
        return filename
        
    return f"{base}/uploads/{filename}"