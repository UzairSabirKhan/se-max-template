"""Starting runs: one at a time per flow, in the background, with live progress (A13, A17; FR-16, EC-49).

- `runs.start(...)` returns a run id at once; the run continues in the background.
- A flow never runs twice at once: a per-flow lock. "Run now" while a run is going gets AlreadyRunning;
  a scheduled run that finds the flow busy is skipped (the next tick will run it).
- Progress events (node_started, node_finished, iteration, finished) are kept per run, so the browser can
  open GET /api/runs/{id}/stream at any moment and still see everything from the start.
One uvicorn worker (ADR 0004), so in-memory locks and progress are enough.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.db.runs import new_id
from app.db.session import Database
from app.engine.fetcher import FetchOptions
from app.engine.runner import RunOptions, run_flow

log = logging.getLogger("scrapeonce.runs")
KEEP_FINISHED_S = 600


class AlreadyRunning(Exception):
    pass


@dataclass
class _Channel:
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    done: bool = False
    finished_at: float = 0.0


class RunService:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._channels: dict[str, _Channel] = {}
        self._tasks: set[asyncio.Task] = set()

    def busy(self, flow_id: str) -> bool:
        lock = self._locks.get(flow_id)
        return bool(lock and lock.locked())

    def known(self, run_id: str) -> bool:
        """Running now, or finished recently enough that its events are still in memory."""
        return run_id in self._channels

    def running(self, run_id: str) -> bool:
        channel = self._channels.get(run_id)
        return bool(channel and not channel.done)

    async def start(self, db: Database, flow_id: str, flow: dict[str, Any], trigger: str, fetch: FetchOptions,
                    published_hash: str | None = None) -> str:
        """Start a run in the background and return its id. Raises AlreadyRunning."""
        lock = self._locks.setdefault(flow_id, asyncio.Lock())
        if lock.locked():
            raise AlreadyRunning(flow_id)
        await lock.acquire()  # taken now, so a double click can't slip in before the task starts
        self._forget_old()
        run_id = new_id("run")
        channel = self._channels[run_id] = _Channel()

        async def emit(event: str, data: dict[str, Any]) -> None:
            channel.events.append((event, data))
            channel.changed.set()

        async def work() -> None:
            try:
                await run_flow(flow, flow_id, db, RunOptions(trigger=trigger, fetch=fetch, emit=emit,
                                                             published_hash=published_hash, run_id=run_id))
            except Exception:
                log.exception("Run %s of %s crashed", run_id, flow_id)
                await emit("finished", {"id": run_id, "flow_id": flow_id, "verdict": "UNKNOWN",
                                        "reason": "The run stopped unexpectedly"})
            finally:
                channel.done, channel.finished_at = True, time.monotonic()
                channel.changed.set()
                lock.release()

        task = asyncio.create_task(work())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return run_id

    async def run_now_and_wait(self, db: Database, flow_id: str, flow: dict[str, Any], trigger: str,
                               fetch: FetchOptions, published_hash: str | None = None) -> dict[str, Any]:
        """Run in the foreground (dry runs, publish checks, the scheduler). Raises AlreadyRunning."""
        lock = self._locks.setdefault(flow_id, asyncio.Lock())
        if lock.locked():
            raise AlreadyRunning(flow_id)
        async with lock:
            return await run_flow(flow, flow_id, db, RunOptions(trigger=trigger, fetch=fetch,
                                                                published_hash=published_hash))

    async def events(self, run_id: str):
        """Every progress event of a run, from the start, until it finishes."""
        channel = self._channels.get(run_id)
        if channel is None:
            return
        sent = 0
        while True:
            while sent < len(channel.events):
                yield channel.events[sent]
                sent += 1
            if channel.done:
                return
            channel.changed.clear()
            if sent < len(channel.events) or channel.done:
                continue
            await channel.changed.wait()

    def _forget_old(self) -> None:
        now = time.monotonic()
        for run_id in [r for r, c in self._channels.items() if c.done and now - c.finished_at > KEEP_FINISHED_S]:
            del self._channels[run_id]

    async def wait_idle(self) -> None:
        """Tests and shutdown: wait for background runs to finish."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)


runs = RunService()
