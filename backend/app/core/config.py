from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[3]

class Settings(BaseSettings):
    APP_NAME: str
    APP_ENV: str
    DEBUG: bool

    DATABASE_URL: str
    SECRET_KEY: str
    REDIS_URL: str

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        case_sensitive=True,
    )

settings = Settings()