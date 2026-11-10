"""Database tables (docs/design.md "Data model"). Portable: Postgres (Neon) in production,
SQLite for local development and tests. JSON columns become JSONB on Postgres.

Tables are created at startup (create_all). There is no migration tool: during the event the
schema only grows, and a new column on an existing table means resetting the database.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

JsonType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class FlowRow(Base):
    __tablename__ = "flows"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft | published | paused
    draft_json: Mapped[dict[str, Any]] = mapped_column(JsonType)
    draft_version: Mapped[int] = mapped_column(Integer, default=0)
    published_json: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    published_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class RunRow(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    flow_id: Mapped[str] = mapped_column(ForeignKey("flows.id", ondelete="CASCADE"), index=True)
    published_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trigger: Mapped[str] = mapped_column(String(16))  # schedule | manual | dry_run
    verdict: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(Text, default="")
    report_json: Mapped[dict[str, Any]] = mapped_column(JsonType)  # full RunReport (contract C3)
    items_found: Mapped[int] = mapped_column(Integer, default=0)
    items_valid: Mapped[int] = mapped_column(Integer, default=0)
    ai_calls: Mapped[int] = mapped_column(Integer, default=0)  # always 0 (NFR-02)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (Index("ix_runs_flow_started", "flow_id", "started_at"),)


class DatasetRow(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    flow_id: Mapped[str] = mapped_column(ForeignKey("flows.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(40))
    identity_key: Mapped[str] = mapped_column(String(40))
    fields_json: Mapped[dict[str, Any]] = mapped_column(JsonType)  # field name -> type
    tracked_fields: Mapped[list[str]] = mapped_column(JsonType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("flow_id", "name", name="uq_dataset_flow_name"),)


class RecordRow(Base):
    __tablename__ = "records"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"))
    identity_key: Mapped[str] = mapped_column(String(2000))
    data_json: Mapped[dict[str, Any]] = mapped_column(JsonType)
    first_seen_run: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_seen_run: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_changed_run: Mapped[str | None] = mapped_column(String(32), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_changed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("dataset_id", "identity_key", name="uq_record_identity"),)


class RecordChangeRow(Base):
    __tablename__ = "record_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_id: Mapped[str] = mapped_column(ForeignKey("records.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str] = mapped_column(String(32))
    change: Mapped[str] = mapped_column(String(16))  # new | changed | removed
    field: Mapped[str | None] = mapped_column(String(40), nullable=True)
    old_value: Mapped[Any] = mapped_column(JsonType, nullable=True)
    new_value: Mapped[Any] = mapped_column(JsonType, nullable=True)
    pct_change: Mapped[str | None] = mapped_column(String(32), nullable=True)  # Decimal as text
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RunResultRow(Base):
    __tablename__ = "run_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    node_id: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(80))
    items_json: Mapped[list[Any]] = mapped_column(JsonType)


class AlertRow(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    flow_id: Mapped[str] = mapped_column(ForeignKey("flows.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str] = mapped_column(String(32))
    node_id: Mapped[str | None] = mapped_column(String(32), nullable=True)  # None = system alert
    kind: Mapped[str] = mapped_column(String(16))  # condition | site_changed | blocked | unsupported | suspect
    level: Mapped[str] = mapped_column(String(8))
    title: Mapped[str] = mapped_column(String(120))
    message: Mapped[str] = mapped_column(Text)
    items_json: Mapped[list[Any]] = mapped_column(JsonType)
    dedupe_key: Mapped[str] = mapped_column(String(300), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
