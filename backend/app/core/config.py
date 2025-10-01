"""Application-wide configuration and settings."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    """Define high-level configuration knobs for the monolith."""

    data_dir: Path = Field(default=Path("data"), description="Root directory for stored artefacts.")
    enable_cloud_llm: bool = Field(default=True, description="Allow outbound LLM requests after sanitisation.")
    llm_provider: str = Field(default="openai", description="Default LLM provider identifier.")
    openai_model: str = Field(default="gpt-4o-mini", description="Baseline model for simplification tasks.")

    class Config:
        env_prefix = "PROSTE_PRAWO_"
        case_sensitive = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings instance."""

    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings
