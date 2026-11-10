"""Flow repository (A8): flows stored in the database instead of memory.

Version conflicts are detected ATOMICALLY: the save is a single
    UPDATE flows SET ... WHERE id = :id AND draft_version = :expected
so two saves racing on the same version can't both win (the in-memory store checked, then
wrote, which let one save silently overwrite the other).
"""

from __future__ import annotations

import copy
import hashlib
import json
import secrets
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AlertRow, FlowRow, utcnow

STARTER_DRAFT: dict[str, Any] = {
    "version": 0,
    "variables": [],
    "nodes": [
        {"id": "t1", "type": "trigger", "position": {"x": 0, "y": 0}, "config": {"mode": "manual"}},
        {"id": "k1", "type": "check_page", "position": {"x": 0, "y": 360}, "config": {}},
    ],
    "edges": [],
}


class VersionConflict(Exception):
    pass


class FlowNotFound(Exception):
    pass


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:  # SQLite returns naive datetimes; we only ever store UTC
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def flow_hash(flow: dict[str, Any]) -> str:
    canonical = json.dumps(flow, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _with_version(draft: dict[str, Any], version: int) -> dict[str, Any]:
    out = copy.deepcopy(draft)
    out["version"] = version
    return out


class FlowRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # -- reads ---------------------------------------------------------------
    async def list(self) -> list[dict[str, Any]]:
        unread = (
            select(AlertRow.flow_id, func.count().label("n"))
            .where(AlertRow.read_at.is_(None))
            .group_by(AlertRow.flow_id)
            .subquery()
        )
        rows = await self.session.execute(
            select(FlowRow, func.coalesce(unread.c.n, 0))
            .outerjoin(unread, unread.c.flow_id == FlowRow.id)
            .order_by(FlowRow.updated_at.desc(), FlowRow.id)
        )
        return [self._summary(flow, n) for flow, n in rows.all()]

    async def get(self, flow_id: str) -> dict[str, Any]:
        row = await self.session.get(FlowRow, flow_id)
        if row is None:
            raise FlowNotFound(flow_id)
        return self._detail(row)

    async def get_row(self, flow_id: str) -> FlowRow:
        row = await self.session.get(FlowRow, flow_id)
        if row is None:
            raise FlowNotFound(flow_id)
        return row

    # -- writes --------------------------------------------------------------
    async def create(self, name: str) -> dict[str, Any]:
        now = utcnow()
        row = FlowRow(id="flow_" + secrets.token_hex(6), name=name, status="draft",
                      draft_json=copy.deepcopy(STARTER_DRAFT), draft_version=0, created_at=now, updated_at=now)
        self.session.add(row)
        await self.session.commit()
        return self._detail(row)

    async def save_draft(self, flow_id: str, draft: dict[str, Any] | None, name: str | None) -> dict[str, Any]:
        values: dict[str, Any] = {"updated_at": utcnow()}
        if name is not None:
            values["name"] = name
        stmt = update(FlowRow).where(FlowRow.id == flow_id)
        if draft is not None:
            expected = draft["version"]
            values["draft_json"] = _with_version(draft, expected + 1)
            values["draft_version"] = expected + 1
            stmt = stmt.where(FlowRow.draft_version == expected)
        result = await self.session.execute(stmt.values(**values).execution_options(synchronize_session=False))
        if result.rowcount == 0:
            await self.session.rollback()
            if await self.session.get(FlowRow, flow_id) is None:
                raise FlowNotFound(flow_id)
            raise VersionConflict()
        await self.session.commit()
        self.session.expire_all()
        return await self.get(flow_id)

    async def publish(self, flow_id: str, published: dict[str, Any] | None = None) -> dict[str, Any]:
        """Copy the draft (or the given, already-checked version of it) to the published copy."""
        row = await self.get_row(flow_id)
        row.published_json = copy.deepcopy(published if published is not None else row.draft_json)
        row.published_hash = flow_hash(row.published_json)
        row.published_at = utcnow()
        row.status = "published"
        row.updated_at = utcnow()
        await self.session.commit()
        return self._detail(row)

    async def published_flows(self) -> list[FlowRow]:
        """Every flow whose schedule should be running (the scheduler rebuilds from this at startup)."""
        return list((await self.session.execute(select(FlowRow).where(FlowRow.status == "published"))).scalars())

    async def set_status(self, flow_id: str, status: str) -> dict[str, Any]:
        row = await self.get_row(flow_id)
        row.status = status
        if status == "draft":  # unpublish
            row.published_json = None
            row.published_hash = None
            row.published_at = None
        row.updated_at = utcnow()
        await self.session.commit()
        return self._detail(row)

    async def delete(self, flow_id: str) -> None:
        result = await self.session.execute(delete(FlowRow).where(FlowRow.id == flow_id))
        if result.rowcount == 0:
            await self.session.rollback()
            raise FlowNotFound(flow_id)
        await self.session.commit()

    # -- shapes (contract C3) ------------------------------------------------
    @staticmethod
    def _detail(row: FlowRow) -> dict[str, Any]:
        return {
            "id": row.id, "name": row.name, "status": row.status,
            "draft": _with_version(row.draft_json, row.draft_version),
            "published": copy.deepcopy(row.published_json) if row.published_json is not None else None,
            "published_at": iso(row.published_at), "updated_at": iso(row.updated_at),
        }

    @staticmethod
    def _summary(row: FlowRow, unread: int) -> dict[str, Any]:
        return {"id": row.id, "name": row.name, "status": row.status, "unread_alerts": int(unread),
                "updated_at": iso(row.updated_at), "published_at": iso(row.published_at)}
