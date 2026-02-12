from pydantic_settings import BaseSettings, SettingsConfigDict

import os

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./app.db"
    timezone: str = "America/Detroit"
    uploads_dir: str = "uploads"

    # MUST be set in production so image URLs are public for Instagram
    public_base_url: str = os.getenv("BASE_URL", "http://localhost:8000")

    ig_access_token: str | None = os.getenv("IG_ACCESS_TOKEN")
    ig_user_id: str | None = os.getenv("IG_USER_ID")
    fb_page_id: str | None = os.getenv("FB_PAGE_ID")

    admin_api_key: str | None = os.getenv("ADMIN_API_KEY")

settings = Settings()