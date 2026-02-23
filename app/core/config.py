from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "KPIAYA"
    environment: str = "dev"
    api_prefix: str = "/api/v1"
    secret_key: str = Field(..., min_length=32)
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30
    jwt_algorithm: str = "HS256"

    database_url: str = Field(..., description="postgresql+asyncpg://user:pass@db:5432/kpiaya")

    telegram_bot_token: str = Field(...)
    telegram_webapp_secret: str = Field(..., description="Bot token for initData HMAC verification")

    super_admin_username: str = "Joshua_Eng1"
    super_admin_telegram_id: int = 6707954035

    scheduler_timezone: str = "UTC"
    scheduler_admin_include_optional: bool = True

    working_hours_per_month: float = 160.0
    overtime_multiplier_x1: float = 1.0
    overtime_multiplier_x2: float = 2.0


settings = Settings()
