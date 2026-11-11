"""Settings from environment variables (names listed in .env.example; values never committed)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: os.environ.get("DATABASE_URL", ""))
    public_base_url: str = field(default_factory=lambda: os.environ.get("PUBLIC_BASE_URL", ""))
    web_dist: Path = field(default_factory=lambda: Path(os.environ.get("WEB_DIST", ROOT / "web" / "dist")))
    max_request_bytes: int = 1_000_000


settings = Settings()
