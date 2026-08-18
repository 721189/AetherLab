import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[3]

ENV_FILES = {
    "development": ".env",
    "testing": ".env.testing",
    "production": ".env.production",
}


class Settings(BaseSettings):
    APP_NAME: str = "AetherLab API"
    APP_ENV: str = "development"
    DEBUG: bool = False

    DATABASE_URL: str
    SECRET_KEY: str
    REDIS_URL: str = "redis://localhost:6379/0"

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Optional CORS / server configuration.
    CORS_ORIGINS: list[str] = []

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        case_sensitive=True,
        extra="ignore",
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._validate_secret_key()
        self._validate_required_settings()

    def _validate_secret_key(self) -> None:
        if len(self.SECRET_KEY) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters long for security"
            )
        if self.SECRET_KEY == "change_this_to_a_long_random_secret":
            raise ValueError(
                "SECRET_KEY must be changed from the default value"
            )

    def _validate_required_settings(self) -> None:
        if not self.DATABASE_URL:
            raise ValueError("DATABASE_URL is required and cannot be empty")


def _env_file_for(app_env: str) -> Path:
    """Resolve the correct env file for a given environment."""
    filename = ENV_FILES.get(app_env, ".env")
    candidate = BASE_DIR / filename
    return candidate if candidate.exists() else BASE_DIR / ".env"


def get_settings() -> Settings:
    """Build settings, honouring an explicit APP_ENV environment variable so
    that tests and deployment can select their configuration."""

    base_env = BASE_DIR / ".env"

    # Determine the environment, preferring an explicit env var but otherwise
    # reading APP_ENV from the base .env file.
    app_env = os.getenv("APP_ENV")
    if not app_env and base_env.exists():
        for line in base_env.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("APP_ENV="):
                app_env = stripped.split("=", 1)[1].strip().strip('"').strip("'")
                break
    app_env = app_env or "development"

    env_file = _env_file_for(app_env)

    kwargs: dict = {}
    if env_file.exists():
        kwargs["_env_file"] = env_file

    # Allow direct environment overrides to take precedence (pydantic does this
    # automatically for values already in os.environ).
    return Settings(**kwargs)


settings = get_settings()
