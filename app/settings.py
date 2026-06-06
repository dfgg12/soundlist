"""Application settings loaded from environment variables."""

from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration values sourced from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    twitch_client_id: str = ""
    twitch_client_secret: str = ""
    twitch_redirect_uri: str = "http://localhost:8000/auth/callback"

    session_secret_key: str = "insecure-dev-key-change-in-production"

    # Comma-separated Twitch logins seeded as admins on startup
    admin_logins: str = ""

    database_url: str = "sqlite:///./soundlist.db"

    @field_validator("database_url")
    @classmethod
    def _sqlite_only(cls, v: str) -> str:
        """Reject non-SQLite database URLs at startup."""
        if not v.startswith("sqlite"):
            raise ValueError(
                "only SQLite is supported; got non-sqlite database_url"
            )
        return v

    app_env: str = "development"

    lists_dir: str = "lists"

    csrf_enabled: bool = True

    # Allow any logged-in user to self-register a channel matching their login
    allow_self_register: bool = True

    @property
    def is_production(self) -> bool:
        """Return True when running in production mode."""
        return self.app_env.lower() == "production"

    @property
    def admin_login_list(self) -> list[str]:
        """Return parsed list of admin Twitch logins (lowercase)."""
        return [
            login.strip().lower()
            for login in self.admin_logins.split(",")
            if login.strip()
        ]


settings = Settings()
