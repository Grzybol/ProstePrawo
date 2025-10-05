"""Application-wide configuration and settings."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict

try:  # pragma: no cover - compatibility with Pydantic v1
    from pydantic import AliasChoices, BaseModel, Field
except ImportError:  # pragma: no cover - fallback for older versions
    AliasChoices = None  # type: ignore[assignment]
    from pydantic import BaseModel, Field
try:  # pragma: no cover - compatibility with pydantic-settings v1
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError:  # pragma: no cover - fallback when SettingsConfigDict is unavailable
    from pydantic_settings import BaseSettings  # type: ignore[no-redef]

    SettingsConfigDict = None  # type: ignore[assignment]


class Settings(BaseSettings):
    """Define high-level configuration knobs for the monolith."""

    if SettingsConfigDict is not None:
        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            env_prefix="PROSTE_PRAWO_",
            env_nested_delimiter="__",
            case_sensitive=False,
        )
    else:
        class Config:  # pragma: no cover - maintained for Pydantic v1
            env_prefix = "PROSTE_PRAWO_"
            case_sensitive = False
            env_file = ".env"
            env_file_encoding = "utf-8"
            env_nested_delimiter = "__"
            fields = {
                "openai_api_key": {
                    "env": ["PROSTE_PRAWO_OPENAI_API_KEY", "OPENAI_API_KEY"],
                },
                "openai_project": {
                    "env": ["PROSTE_PRAWO_OPENAI_PROJECT", "OPENAI_PROJECT"],
                },
            }

    app_name: str = Field(default="ProstePrawo", description="Application name used for defaults.")
    environment: str = Field(default="development", description="Current deployment environment name.")
    data_dir: Path = Field(default=Path("data"), description="Root directory for stored artefacts.")
    enable_cloud_llm: bool = Field(default=True, description="Allow outbound LLM requests after sanitisation.")
    llm_provider: str = Field(default="openai", description="Default LLM provider identifier.")
    openai_model: str = Field(default="gpt-4o-mini", description="Baseline model for simplification tasks.")
    openai_api_key: str | None = Field(
        default=None,
        description="API key used for authenticating OpenAI requests.",
        **(
            {"validation_alias": AliasChoices("OPENAI_API_KEY", "PROSTE_PRAWO_OPENAI_API_KEY")}
            if AliasChoices is not None
            else {}
        ),
    )
    openai_project: str | None = Field(
        default=None,
        description="Optional OpenAI project identifier used for requests.",
        **(
            {"validation_alias": AliasChoices("OPENAI_PROJECT", "PROSTE_PRAWO_OPENAI_PROJECT")}
            if AliasChoices is not None
            else {}
        ),
    )
    openai_pricing: Dict[str, Dict[str, float]] = Field(
        default_factory=lambda: {
            "gpt-4o-mini": {"prompt": 0.00015, "completion": 0.0006},
            "default": {"prompt": 0.0004, "completion": 0.0008},
        },
        description="Per-model pricing (USD) per 1K prompt/completion tokens.",
    )
    session_secret_key: str | None = Field(default=None, description="Secret used to sign session cookies.")
    smtp: "SMTPSettings" = Field(default_factory=lambda: SMTPSettings())
    verification: "VerificationSettings" = Field(default_factory=lambda: VerificationSettings())
    password_reset: "PasswordResetSettings" = Field(default_factory=lambda: PasswordResetSettings())
    turnstile_site_key: str | None = Field(default=None, description="Cloudflare Turnstile site key.")
    turnstile_secret_key: str | None = Field(default=None, description="Cloudflare Turnstile secret key.")
    disable_cloudflare_turnstile: bool = Field(
        default=True,
        description="Disable Turnstile verification (useful for development environments).",
    )


class SMTPSettings(BaseModel):
    """Configuration options for the transactional mailer."""

    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    sender: str | None = None
    use_tls: bool = True

    def is_configured(self) -> bool:
        return bool(self.host and self.sender)


class VerificationSettings(BaseModel):
    """Configuration related to verification tokens."""

    base_url: str | None = None
    token_ttl_hours: int = 24


class PasswordResetSettings(BaseModel):
    """Configuration related to password reset tokens."""

    base_url: str | None = None
    token_ttl_hours: int = 24


def _resolve_env_path() -> Path | None:
    """Return the most relevant ``.env`` file path if available."""

    cwd_env = Path.cwd() / ".env"
    if cwd_env.exists():
        return cwd_env
    for parent in Path(__file__).resolve().parents:
        candidate = parent / ".env"
        if candidate.exists():
            return candidate
    return None


def _load_from_env_file(*env_vars: str) -> str | None:
    """Return the first available value found in the project's ``.env`` file."""

    env_path = _resolve_env_path()
    if env_path is None or not env_path.exists():
        return None

    file_values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        candidate = raw_value.strip().strip('"').strip("'")
        if candidate:
            file_values[key.strip()] = candidate
    for env_var in env_vars:
        if env_var in file_values:
            return file_values[env_var]
    return None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings instance."""

    settings = Settings()

    value = _load_from_env_file("PROSTE_PRAWO_OPENAI_API_KEY", "OPENAI_API_KEY")
    settings.openai_api_key = value

    value = _load_from_env_file("PROSTE_PRAWO_OPENAI_PROJECT", "OPENAI_PROJECT")
    settings.openai_project = value
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings
