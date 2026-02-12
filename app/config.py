from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./app.db"
    timezone: str = "America/Detroit"
    uploads_dir: str = "uploads"

    # MUST be set in production so image URLs are public for Instagram
    public_base_url: str = "http://localhost:8000"

    ig_access_token: str | None = None
    ig_user_id: str | None = None
    fb_page_id: str | None = None

settings = Settings()