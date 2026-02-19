from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

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

settings = Settings()