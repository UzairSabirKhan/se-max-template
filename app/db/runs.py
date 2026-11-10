"""Storage for runs, datasets, records, record history and alerts (A15, A16, A17).

`save_run` writes everything one run produces in ONE transaction: the run, the records it changed,
their history rows, removed marks, result tables and alerts. A failure leaves nothing half-written.
Alerts are de-duplicated by `dedupe_key` (unique column): an alert that already exists is skipped.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.flows import iso
from app.db.models import AlertRow, DatasetRow, RecordChangeRow, RecordRow, RunResultRow, RunRow, utcnow
from app.engine.classify import LastGood
from app.engine.records import Diff

GOOD_VERDICTS = ("OK", "CHANGED")


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


@dataclass
class DatasetWrite:
    name: str
    identity_key: str
    fields: dict[str, str]
    tracked: list[str]
    diff: Diff


@dataclass
class RunWrite:
    run_id: str
    flow_id: str
    trigger: str
    published_hash: str | None
    report: dict[str, Any]
    datasets: list[DatasetWrite] = field(default_factory=list)
    results: list[dict[str, Any]] = field(default_factory=list)
    alerts: list[dict[str, Any]] = field(default_factory=list)


class RunRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # -- reads used by the runner -------------------------------------------------------------------
    async def last_good(self, flow_id: str) -> LastGood | None:
        row = (await self.session.execute(
            select(RunRow).where(RunRow.flow_id == flow_id, RunRow.trigger != "dry_run",
                                 RunRow.verdict.in_(GOOD_VERDICTS))
            .order_by(RunRow.started_at.desc()).limit(1))).scalar_one_or_none()
        if row is None:
            return None
        report = row.report_json or {}
        return LastGood(items_found=row.items_found, coverage=report.get("coverage", {}),
                        body_size=sum(p.get("body_size", 0) for p in report.get("http", [])))

    async def last_verdict(self, flow_id: str) -> str | None:
        return (await self.session.execute(
            select(RunRow.verdict).where(RunRow.flow_id == flow_id, RunRow.trigger != "dry_run")
            .order_by(RunRow.started_at.desc()).limit(1))).scalar_one_or_none()

    async def stored_records(self, flow_id: str, dataset: str) -> dict[str, dict[str, Any]]:
        ds = await self._dataset(flow_id, dataset)
        if ds is None:
            return {}
        rows = (await self.session.execute(
            select(RecordRow).where(RecordRow.dataset_id == ds.id, RecordRow.removed_at.is_(None)))).scalars()
        return {r.identity_key: dict(r.data_json) for r in rows}

    async def _dataset(self, flow_id: str, name: str) -> DatasetRow | None:
        return (await self.session.execute(
            select(DatasetRow).where(DatasetRow.flow_id == flow_id, DatasetRow.name == name))).scalar_one_or_none()

    # -- the one write ------------------------------------------------------------------------------
    async def save_run(self, w: RunWrite) -> None:
        now = utcnow()
        r = w.report
        self.session.add(RunRow(
            id=w.run_id, flow_id=w.flow_id, published_hash=w.published_hash, trigger=w.trigger,
            verdict=r["verdict"], reason=r["reason"], report_json=r, items_found=r["items_found"],
            items_valid=r["items_valid"], ai_calls=0, duration_ms=r["duration_ms"], started_at=now))
        await self.session.flush()

        for d in w.datasets:
            ds = await self._dataset(w.flow_id, d.name)
            if ds is None:
                ds = DatasetRow(id=new_id("ds"), flow_id=w.flow_id, name=d.name, identity_key=d.identity_key,
                                fields_json=d.fields, tracked_fields=d.tracked)
                self.session.add(ds)
                await self.session.flush()
            else:
                ds.fields_json = {**ds.fields_json, **d.fields}
                ds.tracked_fields = d.tracked
            await self._write_records(ds.id, w.run_id, d.diff, now)

        for res in w.results:
            self.session.add(RunResultRow(run_id=w.run_id, node_id=res["node_id"], name=res["name"],
                                          items_json=res["items"]))

        written: set[str] = set()  # two alerts in ONE run with the same key would break the unique index
        for alert in w.alerts:
            key = alert["dedupe_key"][:300]
            if key in written:
                continue
            exists = (await self.session.execute(
                select(AlertRow.id).where(AlertRow.dedupe_key == key))).scalar_one_or_none()
            written.add(key)
            if exists is None:
                self.session.add(AlertRow(id=new_id("al"), flow_id=w.flow_id, run_id=w.run_id, created_at=now,
                                          node_id=alert["node_id"], kind=alert["kind"], level=alert["level"],
                                          title=alert["title"][:120], message=alert["message"],
                                          items_json=alert["items"], dedupe_key=key))
        await self.session.commit()

    async def _write_records(self, dataset_id: str, run_id: str, diff: Diff, now) -> None:
        existing = {r.identity_key: r for r in (await self.session.execute(
            select(RecordRow).where(RecordRow.dataset_id == dataset_id))).scalars()}
        for x in diff.labelled:
            key = x.item.key
            if key is None or x.item.error or x.change == "suspect":
                continue  # suspect values are held, not stored; failed pages keep the last good data
            row = existing.get(key)
            if row is None:
                row = RecordRow(id=new_id("rec"), dataset_id=dataset_id, identity_key=key, data_json=dict(x.item.data),
                                first_seen_run=run_id, last_seen_run=run_id, first_seen=now)
                self.session.add(row)
                await self.session.flush()
                self.session.add(RecordChangeRow(record_id=row.id, run_id=run_id, change="new", at=now))
                continue
            row.last_seen_run = run_id
            if row.removed_at is not None:  # it came back
                row.removed_at = None
            if x.change == "changed":
                for f in x.changed_fields:
                    pct = x.pct_change.get(f)
                    self.session.add(RecordChangeRow(
                        record_id=row.id, run_id=run_id, change="changed", field=f, old_value=x.previous.get(f),
                        new_value=x.item.data.get(f), pct_change=None if pct is None else str(pct), at=now))
                row.data_json = dict(x.item.data)
                row.last_changed_run = run_id
                row.last_changed = now
        for key in diff.removed:
            row = existing.get(key)
            if row is not None and row.removed_at is None:
                row.removed_at = now
                self.session.add(RecordChangeRow(record_id=row.id, run_id=run_id, change="removed", at=now))

    # -- reads used by the API ----------------------------------------------------------------------
    async def list_runs(self, flow_id: str, limit: int) -> list[dict[str, Any]]:
        rows = (await self.session.execute(
            select(RunRow).where(RunRow.flow_id == flow_id).order_by(RunRow.started_at.desc()).limit(limit))).scalars()
        return [self._summary(r) for r in rows]

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = await self.session.get(RunRow, run_id)
        if row is None:
            return None
        return {**row.report_json, **self._summary(row)}

    @staticmethod
    def _summary(r: RunRow) -> dict[str, Any]:
        report = r.report_json or {}
        return {"id": r.id, "flow_id": r.flow_id, "trigger": r.trigger, "verdict": r.verdict, "reason": r.reason,
                "started_at": iso(r.started_at), "duration_ms": r.duration_ms, "items_found": r.items_found,
                "items_valid": r.items_valid, "changes": report.get("changes", {"new": 0, "changed": 0, "removed": 0}),
                "ai_calls": r.ai_calls}

    async def latest_results(self, flow_id: str) -> list[dict[str, Any]]:
        run_id = (await self.session.execute(
            select(RunRow.id).where(RunRow.flow_id == flow_id).order_by(RunRow.started_at.desc()).limit(1)
        )).scalar_one_or_none()
        if run_id is None:
            return []
        rows = (await self.session.execute(select(RunResultRow).where(RunResultRow.run_id == run_id))).scalars()
        return [{"node_id": r.node_id, "name": r.name, "items": r.items_json} for r in rows]

    async def list_alerts(self, flow_id: str, limit: int = 200) -> list[dict[str, Any]]:
        rows = (await self.session.execute(
            select(AlertRow).where(AlertRow.flow_id == flow_id).order_by(AlertRow.created_at.desc(), AlertRow.id)
            .limit(limit))).scalars()
        return [{"id": a.id, "flow_id": a.flow_id, "run_id": a.run_id, "node_id": a.node_id, "kind": a.kind,
                 "level": a.level, "title": a.title, "message": a.message, "items": a.items_json,
                 "created_at": iso(a.created_at), "read": a.read_at is not None} for a in rows]

    async def mark_alert_read(self, alert_id: str) -> bool:
        result = await self.session.execute(
            update(AlertRow).where(AlertRow.id == alert_id, AlertRow.read_at.is_(None)).values(read_at=utcnow()))
        await self.session.commit()
        return result.rowcount > 0 or await self.session.get(AlertRow, alert_id) is not None

    async def list_datasets(self, flow_id: str) -> list[dict[str, Any]]:
        counts = (select(RecordRow.dataset_id, func.count().label("n")).where(RecordRow.removed_at.is_(None))
                  .group_by(RecordRow.dataset_id).subquery())
        rows = await self.session.execute(
            select(DatasetRow, func.coalesce(counts.c.n, 0)).outerjoin(counts, counts.c.dataset_id == DatasetRow.id)
            .where(DatasetRow.flow_id == flow_id).order_by(DatasetRow.name))
        return [{"id": d.id, "name": d.name, "identity_key": d.identity_key, "fields": d.fields_json,
                 "record_count": int(n)} for d, n in rows.all()]

    async def list_records(self, dataset_id: str, limit: int, offset: int) -> dict[str, Any]:
        base = select(RecordRow).where(RecordRow.dataset_id == dataset_id)
        total = (await self.session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
        rows = (await self.session.execute(
            base.order_by(RecordRow.removed_at.is_not(None), RecordRow.first_seen, RecordRow.identity_key)
            .limit(limit).offset(offset))).scalars()
        return {"total": total, "records": [
            {"id": r.id, "key": r.identity_key, "data": r.data_json, "first_seen": iso(r.first_seen),
             "last_changed": iso(r.last_changed), "removed_at": iso(r.removed_at)} for r in rows]}

    async def record_history(self, record_id: str) -> list[dict[str, Any]]:
        rows = (await self.session.execute(
            select(RecordChangeRow).where(RecordChangeRow.record_id == record_id).order_by(RecordChangeRow.at,
                                                                                          RecordChangeRow.id))).scalars()
        return [{"run_id": c.run_id, "at": iso(c.at), "change": c.change, "field": c.field,
                 "old_value": c.old_value, "new_value": c.new_value,
                 "pct_change": None if c.pct_change is None else float(c.pct_change)} for c in rows]

    async def dataset_flow(self, dataset_id: str) -> str | None:
        ds = await self.session.get(DatasetRow, dataset_id)
        return ds.flow_id if ds else None

    async def reset_dataset(self, dataset_id: str) -> bool:
        ds = await self.session.get(DatasetRow, dataset_id)
        if ds is None:
            return False
        await self.session.execute(delete(RecordRow).where(RecordRow.dataset_id == dataset_id))
        await self.session.commit()
        return True
