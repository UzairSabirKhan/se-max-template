"""Database engine and sessions.

DATABASE_URL decides where data lives:
- Neon / any Postgres URL (production): `postgresql://user:pass@host/db?sslmode=require` as copied
  from the Neon dashboard is accepted and converted for asyncpg.
- Not set, locally: a SQLite file `scrapeonce.db` in the repo root (survives restarts; git-ignored).
- Not set, on Render: startup FAILS on purpose. Render's disk is wiped on every deploy and sleep,
  so silently falling back to SQLite there would lose every flow.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Base
from app.settings import ROOT


class DatabaseConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class DbTarget:
    url: str
    connect_args: dict[str, Any]
    is_sqlite: bool


# Postgres URL query parameters that libpq understands but asyncpg does not.
_LIBPQ_ONLY = {"sslmode", "channel_binding", "options", "target_session_attrs", "gssencmode"}


def resolve_database_url(raw: str | None, on_render: bool | None = None) -> DbTarget:
    raw = (raw or "").strip()
    if on_render is None:
        on_render = bool(os.environ.get("RENDER"))
    if not raw:
        if on_render:
            raise DatabaseConfigError(
                "DATABASE_URL is not set. On Render the disk is wiped on every deploy, so a database "
                "is required: create a free Neon Postgres and set DATABASE_URL in the Render dashboard."
            )
        raw = f"sqlite+aiosqlite:///{(ROOT / 'scrapeonce.db').as_posix()}"

    parts = urlsplit(raw)
    scheme = parts.scheme.lower()

    if scheme.startswith("sqlite"):
        if on_render:
            raise DatabaseConfigError("SQLite is not allowed on Render: its disk is not persistent. Use Postgres.")
        url = raw.replace("sqlite://", "sqlite+aiosqlite://", 1) if scheme == "sqlite" else raw
        return DbTarget(url=url, connect_args={}, is_sqlite=True)

    if scheme in ("postgres", "postgresql", "postgresql+asyncpg"):
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        sslmode = query.get("sslmode", "")
        clean = {k: v for k, v in query.items() if k not in _LIBPQ_ONLY}
        connect_args: dict[str, Any] = {
            # Neon's pooled endpoint (PgBouncer, transaction mode) breaks asyncpg's prepared
            # statement cache; turning it off is safe for direct connections too.
            "statement_cache_size": 0,
        }
        if sslmode and sslmode != "disable":
            connect_args["ssl"] = sslmode  # asyncpg accepts libpq's sslmode names (require, verify-full, ...)
        url = urlunsplit(("postgresql+asyncpg", parts.netloc, parts.path, urlencode(clean), ""))
        return DbTarget(url=url, connect_args=connect_args, is_sqlite=False)

    raise DatabaseConfigError(f"Unsupported DATABASE_URL scheme {parts.scheme!r}: use postgresql:// or sqlite://")


class Database:
    def __init__(self, target: DbTarget) -> None:
        self.target = target
        kwargs: dict[str, Any] = {"connect_args": target.connect_args}
        if not target.is_sqlite:
            # Free Postgres tiers drop idle connections: check before use, recycle often.
            kwargs.update(pool_pre_ping=True, pool_recycle=300, pool_size=5, max_overflow=5)
        self.engine: AsyncEngine = create_async_engine(target.url, **kwargs)
        if target.is_sqlite:
            event.listen(self.engine.sync_engine, "connect", _sqlite_pragmas)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def create_tables(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def ping(self, timeout: float = 3.0) -> None:
        """Raise if the database can't answer SELECT 1 within `timeout` seconds."""
        async def _select_one() -> None:
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        await asyncio.wait_for(_select_one(), timeout=timeout)

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.sessions() as session:
            yield session

    async def dispose(self) -> None:
        await self.engine.dispose()


def _sqlite_pragmas(dbapi_conn: Any, _: Any) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")  # ON DELETE CASCADE needs this on SQLite
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()
