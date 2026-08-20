from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AQ Backend"
    environment: str = "development"
    database_url: str = "sqlite:///./aq.db"

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 720

    admin_username: str = "admin"
    admin_password: str = "change-me"

    sports_api_key: str = ""
    sports_api_base_url: str = "https://v3.football.api-sports.io"
    sports_cache_fixtures_seconds: int = 120
    sports_cache_team_form_seconds: int = 1800
    sports_cache_statistics_seconds: int = 86400
    sports_cache_stale_seconds: int = 21600
    openai_api_key: str = ""

    sync_mode: str = "off"
    sync_interval_seconds: int = 900
    internal_cron_token: str = "change-me"

    cors_origins: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
