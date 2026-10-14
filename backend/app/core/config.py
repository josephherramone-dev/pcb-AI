"""Application settings, loaded from environment variables (see ``.env.example``)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "PCB AI"
    environment: Literal["development", "test", "production"] = "development"

    # --- persistence -------------------------------------------------------
    database_url: str = "sqlite:///./data/pcbai.db"
    auto_create_tables: bool = Field(
        default=True,
        description="Create tables on startup (dev/test). Production uses Alembic migrations.",
    )
    storage_backend: Literal["local"] = "local"
    storage_root: Path = Path("./data/storage")

    # --- background jobs ---------------------------------------------------
    job_backend: Literal["inline", "eager", "celery"] = Field(
        default="inline",
        description=(
            "inline: thread pool inside the API process (local dev). "
            "eager: run synchronously during the request (tests). "
            "celery: dispatch to Celery workers through Redis (Docker / production)."
        ),
    )
    redis_url: str = "redis://localhost:6379/0"
    job_timeout_seconds: int = 300

    # --- KiCad engine -----------------------------------------------------
    kicad_exec_mode: Literal["local", "docker"] = Field(
        default="local",
        description=(
            "local: run kicad-cli / KiCad Python as subprocesses of the worker. "
            "docker: run every EDA step in a fresh, network-less KiCad container."
        ),
    )
    kicad_cli: str = "kicad-cli"
    kicad_python: str = "python3"
    kicad_docker_image: str = "kicad/kicad:9.0"
    kicad_symbol_dir: Path | None = None
    kicad_footprint_dir: Path | None = None
    eda_command_timeout_seconds: int = 120

    # --- AI ---------------------------------------------------------------
    ai_provider: Literal["anthropic", "none"] = "anthropic"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"
    anthropic_enable_fallbacks: bool = True
    ai_max_tool_iterations: int = 12

    # --- HTTP -------------------------------------------------------------
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    def symbol_dir(self) -> Path:
        return self.kicad_symbol_dir or _first_existing(
            [
                Path("/usr/share/kicad/symbols"),
                Path("/usr/local/share/kicad/symbols"),
                Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"),
            ]
        )

    def footprint_dir(self) -> Path:
        return self.kicad_footprint_dir or _first_existing(
            [
                Path("/usr/share/kicad/footprints"),
                Path("/usr/local/share/kicad/footprints"),
                Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"),
            ]
        )


def _first_existing(paths: list[Path]) -> Path:
    for p in paths:
        if p.exists():
            return p
    return paths[0]


@lru_cache
def get_settings() -> Settings:
    return Settings()
