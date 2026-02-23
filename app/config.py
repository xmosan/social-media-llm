from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    database_url: str = Field(default="sqlite:///./saas.db", alias="DATABASE_URL")
    timezone: str = Field(default="America/Detroit", alias="TIMEZONE")
    uploads_dir: str = Field(default="uploads", alias="UPLOADS_DIR")

    # In production (Railway), BASE_URL env var will override this
    public_base_url: str = Field(default="http://localhost:8000", alias="BASE_URL")

    ig_access_token: str | None = Field(default=None, alias="IG_ACCESS_TOKEN")
    ig_user_id: str | None = Field(default=None, alias="IG_USER_ID")
    fb_page_id: str | None = Field(default=None, alias="FB_PAGE_ID")

    admin_api_key: str | None = Field(default=None, alias="ADMIN_API_KEY")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")

    # Auth & security
    secret_key: str = Field(default="change-me-in-production-for-jwt", alias="SECRET_KEY")
    superadmin_email: str | None = Field(default=None, alias="SUPERADMIN_EMAIL")
    superadmin_email: str | None = Field(default=None, alias="SUPERADMIN_EMAIL")
    superadmin_password: str | None = Field(default=None, alias="SUPERADMIN_PASSWORD")

    # Google OAuth
    google_client_id: str | None = Field(default=None, alias="GOOGLE_CLIENT_ID")
    google_client_secret: str | None = Field(default=None, alias="GOOGLE_CLIENT_SECRET")

    # Backups & Reliability
    backup_storage_type: str = Field(default="local", alias="BACKUP_STORAGE_TYPE")
    s3_access_key: str | None = Field(default=None, alias="S3_ACCESS_KEY")
    s3_secret_key: str | None = Field(default=None, alias="S3_SECRET_KEY")
    s3_bucket_name: str | None = Field(default=None, alias="S3_BUCKET_NAME")
    s3_region: str | None = Field(default=None, alias="S3_REGION")
    env_backup_key: str | None = Field(default=None, alias="ENV_BACKUP_KEY")
    primary_region: str | None = Field(default=None, alias="PRIMARY_REGION")
    secondary_database_url: str | None = Field(default=None, alias="SECONDARY_DATABASE_URL")

    # Observability (Axiom)
    axiom_token: str | None = Field(default=None, alias="AXIOM_TOKEN")
    axiom_dataset: str | None = Field(default="social-media-llm", alias="AXIOM_DATASET")
    axiom_org_id: str | None = Field(default=None, alias="AXIOM_ORG_ID")
    axiom_url: str = Field(default="https://api.axiom.co", alias="AXIOM_URL")

settings = Settings()