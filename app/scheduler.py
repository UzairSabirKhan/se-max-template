"""The scheduler (A18; FR-15; docs/adr 0004): runs published flows on their Trigger node's schedule.

- Lives inside the one web service (APScheduler, asyncio). ONE uvicorn worker, so it never starts twice.
- The schedule is the PUBLISHED flow's Trigger node: manual (no job), interval (every N minutes) or daily
  (HH:MM in a timezone). Publish / pause / unpublish update the job at once.
- At startup every job is rebuilt from the published flows in the database, so a restart, redeploy or a
  host waking from sleep loses no schedule. An interval counts from the flow's last real run (or its
  publish time), so restarts never push the next run back; Run now restarts the count too.
- A tick that finds the flow already running is skipped (the per-flow lock); the next tick runs it.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import func, select

from app.db.flows import FlowRepo
from app.db.models import RunRow
from app.db.session import Database
from app.engine.fetcher import FetchOptions
from app.engine.service import AlreadyRunning, RunService

log = logging.getLogger("scrapeonce.scheduler")


#: A run that came due while the app was down starts this long after the app is back.
CATCH_UP = timedelta(seconds=10)


def _utc(dt: datetime | None) -> datetime | None:
    # SQLite hands back naive datetimes; they are stored in UTC.
    return dt.replace(tzinfo=UTC) if dt is not None and dt.tzinfo is None else dt


def trigger_for(
    flow: dict[str, Any], last_run: datetime | None = None, now: datetime | None = None
) -> IntervalTrigger | CronTrigger | None:
    """The APScheduler trigger for a flow's Trigger node, or None for manual-only flows.

    An interval counts from `last_run`: the flow's last real run (scheduled or Run now), or its publish
    time if it hasn't run yet. The next run is last_run + interval; if that time already passed (the app
    was restarting), it runs right away instead. Before this, APScheduler counted from the moment the job
    was added, so every redeploy restarted the countdown and a 30-minute flow never ran while deploys
    came more often than every 30 minutes.
    """
    node = next((n for n in flow.get("nodes", []) if n.get("type") == "trigger"), None)
    config = (node or {}).get("config", {})
    mode = config.get("mode", "manual")
    if mode == "interval" and config.get("every_minutes"):
        now = _utc(now) or datetime.now(UTC)
        every = timedelta(minutes=int(config["every_minutes"]))
        last = _utc(last_run) or now
        first = last + every if last + every > now else now + CATCH_UP
        return IntervalTrigger(minutes=int(config["every_minutes"]), start_date=first, timezone=UTC)
    if mode == "daily" and config.get("at_time"):
        hour, minute = (int(x) for x in config["at_time"].split(":"))
        return CronTrigger(hour=hour, minute=minute, timezone=config.get("timezone", "Asia/Karachi"))
    return None


class FlowScheduler:
    def __init__(self, db: Database, runs: RunService, fetch: Callable[[], FetchOptions]) -> None:
        self.db = db
        self.runs = runs
        self.fetch = fetch
        self.scheduler = AsyncIOScheduler(timezone="UTC")

    async def start(self) -> None:
        self.scheduler.start()
        async with self.db.sessions() as session:
            for row in await FlowRepo(session).published_flows():
                last = await session.scalar(
                    select(func.max(RunRow.started_at)).where(RunRow.flow_id == row.id, RunRow.trigger != "dry_run")
                )
                anchors = [t for t in (_utc(last), _utc(row.published_at)) if t is not None]
                self.schedule(row.id, row.published_json or {}, last_run=max(anchors) if anchors else None)
        log.info("Scheduler started with %d job(s)", len(self.scheduler.get_jobs()))

    def schedule(self, flow_id: str, published: dict[str, Any], last_run: datetime | None = None) -> None:
        """Add or replace a flow's job, counting from `last_run` (now, if not given: just published or just run)."""
        trigger = trigger_for(published, last_run)
        if trigger is None:
            self.unschedule(flow_id)
            return
        self.scheduler.add_job(self._tick, trigger, args=[flow_id], id=flow_id, replace_existing=True,
                               max_instances=1, coalesce=True, misfire_grace_time=60)

    def unschedule(self, flow_id: str) -> None:
        if self.scheduler.get_job(flow_id):
            self.scheduler.remove_job(flow_id)

    def next_run_at(self, flow_id: str) -> datetime | None:
        """When the flow's next scheduled run is due, or None (manual, paused or not published)."""
        job = self.scheduler.get_job(flow_id)
        return job.next_run_time if job else None

    def job_ids(self) -> list[str]:
        return sorted(job.id for job in self.scheduler.get_jobs())

    async def _tick(self, flow_id: str) -> None:
        async with self.db.sessions() as session:
            try:
                row = await FlowRepo(session).get_row(flow_id)
            except Exception:
                self.unschedule(flow_id)  # the flow was deleted
                return
            if row.status != "published" or not row.published_json:
                self.unschedule(flow_id)
                return
            published, published_hash = row.published_json, row.published_hash
        try:
            await self.runs.start(self.db, flow_id, published, "schedule", self.fetch(), published_hash)
        except AlreadyRunning:
            log.info("Scheduled run of %s skipped: a run is already in progress", flow_id)

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
