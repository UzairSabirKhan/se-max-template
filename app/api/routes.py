"""REST API (specs/contracts.md C3). Everything here is REAL (no stubs left).

- Flows: create / list / get / save (atomic version check, draft validation) / delete.
- Lifecycle: dry run (a real run of the draft that writes no records or alerts); publish (validates,
  test-runs the draft, refuses a broken result, then starts the schedule); pause; unpublish; Run now
  (in the background, one run per flow at a time, live progress over SSE).
- Data: runs, run reports, results, alerts, datasets, records, record history, CSV export, reset.
The agent route (POST /api/flows/{id}/agent) belongs to Workstream B (app/api/agent.py).
"""

from __future__ import annotations

import copy
import csv
import io
import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, StringConstraints
from sse_starlette.sse import EventSourceResponse

from app.api.errors import ApiError, invalid_flow
from app.db.flows import FlowNotFound, FlowRepo, VersionConflict
from app.db.runs import RunRepo
from app.engine import api as engine
from app.engine.service import AlreadyRunning, runs
from app.flow.selector import data_for_step, samples_from_report

router = APIRouter(prefix="/api")

FlowName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80,
                                            pattern=r"^[^<>{}`]+$")]
FAILED_VERDICTS = ("BLOCKED", "UNSUPPORTED", "BROKEN", "UNKNOWN")


class CreateFlow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: FlowName


class SaveFlow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: FlowName | None = None
    draft: dict[str, Any] | None = None


class DryRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    draft: dict[str, Any]
    until_node: str | None = None


async def get_repo(request: Request) -> AsyncIterator[FlowRepo]:
    async with request.app.state.db.sessions() as session:
        yield FlowRepo(session)


async def get_runs(request: Request) -> AsyncIterator[RunRepo]:
    async with request.app.state.db.sessions() as session:
        yield RunRepo(session)


Repo = Annotated[FlowRepo, Depends(get_repo)]
Runs = Annotated[RunRepo, Depends(get_runs)]
NOT_FOUND = ApiError(404, "not_found", "Flow not found")


async def _load(repo: FlowRepo, flow_id: str) -> dict[str, Any]:
    try:
        return await repo.get(flow_id)
    except FlowNotFound:
        raise NOT_FOUND from None


def _scheduler(request: Request):
    return getattr(request.app.state, "scheduler", None)


# --- catalogue ------------------------------------------------------------
@router.get("/node-types")
def node_types() -> list[dict[str, Any]]:
    return engine.node_type_schemas()


# --- flows ------------------------------------------------------------------
@router.get("/flows")
async def list_flows(repo: Repo) -> list[dict[str, Any]]:
    return await repo.list()


@router.post("/flows", status_code=201)
async def create_flow(body: CreateFlow, repo: Repo) -> dict[str, Any]:
    return await repo.create(body.name)


@router.get("/flows/{flow_id}")
async def get_flow(flow_id: str, repo: Repo) -> dict[str, Any]:
    return await _load(repo, flow_id)


@router.put("/flows/{flow_id}")
async def save_flow(flow_id: str, body: SaveFlow, repo: Repo) -> dict[str, Any]:
    normalised = None
    if body.draft is not None:
        version = body.draft.get("version")
        if not isinstance(version, int) or isinstance(version, bool):
            raise ApiError(422, "invalid_request",
                           "draft.version is required: send back the version you loaded",
                           issues=[{"node_id": None, "path": "draft.version", "message": "Required integer"}])
        normalised, issues = engine.parse_flow(body.draft, draft=True)
        if issues:
            raise invalid_flow(issues)
    try:
        return await repo.save_draft(flow_id, normalised, body.name)
    except FlowNotFound:
        raise NOT_FOUND from None
    except VersionConflict:
        raise ApiError(409, "version_conflict",
                       "This flow was changed somewhere else. Reload to get the latest version.") from None


@router.delete("/flows/{flow_id}", status_code=204)
async def delete_flow(flow_id: str, request: Request, repo: Repo) -> Response:
    try:
        await repo.delete(flow_id)
    except FlowNotFound:
        raise NOT_FOUND from None
    if (scheduler := _scheduler(request)) is not None:
        scheduler.unschedule(flow_id)
    return Response(status_code=204)


# --- lifecycle ----------------------------------------------------------------
@router.post("/flows/{flow_id}/dry-run")
async def dry_run(flow_id: str, body: DryRunRequest, repo: Repo) -> dict[str, Any]:
    await _load(repo, flow_id)
    normalised, issues = engine.parse_flow(body.draft)
    if issues:
        raise invalid_flow(issues)
    return await engine.dry_run(normalised, flow_id, body.until_node)


def _with_expected_count(flow: dict[str, Any], items_found: int) -> dict[str, Any]:
    """Store an expected item range from the publish test run, if the flow didn't set one (FR-14).
    A later run far outside it is BROKEN: the selector probably matches the wrong things."""
    flow = copy.deepcopy(flow)
    for node in flow["nodes"]:
        config = node.get("config", {})
        if node.get("type") == "extract_list" and not config.get("expected_count") and items_found > 0:
            config["expected_count"] = {"min": max(1, items_found // 2),
                                        "max": min(500, max(items_found * 2, items_found + 5))}
    return flow


@router.post("/flows/{flow_id}/publish")
async def publish(flow_id: str, request: Request, repo: Repo) -> dict[str, Any]:
    flow = await _load(repo, flow_id)
    normalised, issues = engine.parse_flow(flow["draft"], for_publish=True)
    if issues:
        raise invalid_flow(issues)
    report = await engine.dry_run(normalised, flow_id)
    if report["verdict"] in FAILED_VERDICTS:
        raise ApiError(422, "publish_check_failed", f"The test run didn't pass, so nothing was published: "
                                                    f"{report['reason']}",
                       issues=[{"node_id": None, "path": "", "message": report["reason"]}], extra={"report": report})
    published = _with_expected_count(normalised, report["items_found"])
    detail = await repo.publish(flow_id, published)
    if (scheduler := _scheduler(request)) is not None:
        scheduler.schedule(flow_id, published)
    return detail


@router.post("/flows/{flow_id}/pause")
async def pause(flow_id: str, request: Request, repo: Repo) -> dict[str, Any]:
    flow = await _load(repo, flow_id)
    if flow["status"] != "published":
        raise ApiError(400, "not_published", "Only a published flow can be paused")
    if (scheduler := _scheduler(request)) is not None:
        scheduler.unschedule(flow_id)
    return await repo.set_status(flow_id, "paused")


@router.post("/flows/{flow_id}/unpublish")
async def unpublish(flow_id: str, request: Request, repo: Repo) -> dict[str, Any]:
    await _load(repo, flow_id)
    if (scheduler := _scheduler(request)) is not None:
        scheduler.unschedule(flow_id)
    return await repo.set_status(flow_id, "draft")


@router.post("/flows/{flow_id}/run", status_code=202)
async def run_now(flow_id: str, request: Request, repo: Repo) -> dict[str, Any]:
    await _load(repo, flow_id)
    row = await repo.get_row(flow_id)
    if row.status != "published" or not row.published_json:
        raise ApiError(400, "not_published", "Publish the flow before running it")
    try:
        run_id = await runs.start(request.app.state.db, flow_id, row.published_json, "manual",
                                  engine.fetch_options(), row.published_hash)
    except AlreadyRunning:
        raise ApiError(409, "already_running", "This flow is already running. Wait for it to finish.") from None
    return {"run_id": run_id}


# --- runs ----------------------------------------------------------------------------
@router.get("/flows/{flow_id}/runs")
async def list_runs(flow_id: str, repo: Repo, store: Runs,
                    limit: int = Query(20, ge=1, le=100)) -> list[dict[str, Any]]:
    await _load(repo, flow_id)
    return await store.list_runs(flow_id, limit)


@router.get("/runs/{run_id}")
async def get_run(run_id: str, store: Runs) -> dict[str, Any]:
    report = await store.get_run(run_id)
    if report is not None:
        return report
    if runs.running(run_id):
        raise ApiError(409, "running", "This run is still in progress. Follow it at /api/runs/{id}/stream.")
    raise ApiError(404, "not_found", "Run not found")


@router.get("/runs/{run_id}/stream")
async def run_stream(run_id: str, store: Runs) -> EventSourceResponse:
    """Progress of a run: every event from the start, then live until it finishes. Works whenever the
    browser connects: during the run, just after it, or later (rebuilt from the stored report)."""
    if runs.known(run_id):
        async def live():
            async for event, data in runs.events(run_id):
                yield {"event": event, "data": json.dumps(data, default=str)}
        return EventSourceResponse(live())

    finished = await store.get_run(run_id)
    if finished is None:
        raise ApiError(404, "not_found", "Run not found")

    async def stored():
        for step in finished.get("node_trace", []):
            yield {"event": "node_finished", "data": json.dumps(step, default=str)}
        summary = {k: finished.get(k) for k in ("id", "flow_id", "trigger", "verdict", "reason", "started_at",
                                                "duration_ms", "items_found", "items_valid", "changes", "ai_calls")}
        yield {"event": "finished", "data": json.dumps(summary, default=str)}

    return EventSourceResponse(stored())


class DataSelectorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    draft: dict[str, Any]
    node_id: Annotated[str, StringConstraints(min_length=1, max_length=32)]


@router.post("/flows/{flow_id}/data-selector")
async def data_selector(flow_id: str, body: DataSelectorRequest, repo: Repo, store: Runs) -> dict[str, Any]:
    """What a step can use from the steps before it: fields grouped by source step, with types, allowed
    condition operators and a sample value from the flow's latest run; plus the variables. Uses the
    editor's current draft (unsaved edits included)."""
    await _load(repo, flow_id)
    normalised, issues = engine.parse_flow(body.draft, draft=True)
    if issues:
        raise invalid_flow(issues)
    latest = await store.list_runs(flow_id, 1)
    report = await store.get_run(latest[0]["id"]) if latest else None
    result = data_for_step(normalised, body.node_id, samples_from_report(report))
    if result.get("error"):
        raise ApiError(404, "not_found", result["error"])
    return result


@router.get("/flows/{flow_id}/results")
async def results(flow_id: str, repo: Repo, store: Runs) -> list[dict[str, Any]]:
    await _load(repo, flow_id)
    return await store.latest_results(flow_id)


# --- alerts ----------------------------------------------------------------------------
@router.get("/flows/{flow_id}/alerts")
async def list_alerts(flow_id: str, repo: Repo, store: Runs) -> list[dict[str, Any]]:
    await _load(repo, flow_id)
    return await store.list_alerts(flow_id)


@router.post("/alerts/{alert_id}/read", status_code=204)
async def mark_alert_read(alert_id: str, store: Runs) -> Response:
    if not await store.mark_alert_read(alert_id):
        raise ApiError(404, "not_found", "Alert not found")
    return Response(status_code=204)


# --- data ------------------------------------------------------------------------------
@router.get("/flows/{flow_id}/datasets")
async def list_datasets(flow_id: str, repo: Repo, store: Runs) -> list[dict[str, Any]]:
    await _load(repo, flow_id)
    return await store.list_datasets(flow_id)


async def _dataset_or_404(store: RunRepo, dataset_id: str) -> str:
    flow_id = await store.dataset_flow(dataset_id)
    if flow_id is None:
        raise ApiError(404, "not_found", "Dataset not found")
    return flow_id


@router.get("/datasets/{dataset_id}/records")
async def list_records(dataset_id: str, store: Runs, limit: int = Query(50, ge=1, le=500),
                       offset: int = Query(0, ge=0)) -> dict[str, Any]:
    await _dataset_or_404(store, dataset_id)
    return await store.list_records(dataset_id, limit, offset)


@router.get("/records/{record_id}/history")
async def record_history(record_id: str, store: Runs) -> list[dict[str, Any]]:
    return await store.record_history(record_id)


@router.get("/datasets/{dataset_id}/export.csv")
async def export_csv(dataset_id: str, store: Runs) -> Response:
    await _dataset_or_404(store, dataset_id)
    rows = (await store.list_records(dataset_id, 10_000, 0))["records"]
    columns = sorted({k for r in rows for k in (r["data"] or {})})
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["key", *columns, "first_seen", "last_changed", "removed_at"])
    for r in rows:
        cells = [r["key"], *[(r["data"] or {}).get(c, "") for c in columns], r["first_seen"], r["last_changed"] or "",
                 r["removed_at"] or ""]
        # A cell starting with = + - @ would run as a formula in Excel: prefix it (CSV injection).
        writer.writerow(["'" + str(c) if str(c)[:1] in "=+-@" else c for c in cells])
    return Response(buffer.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{dataset_id}.csv"'})


@router.post("/datasets/{dataset_id}/reset", status_code=204)
async def reset_dataset(dataset_id: str, store: Runs) -> Response:
    if not await store.reset_dataset(dataset_id):
        raise ApiError(404, "not_found", "Dataset not found")
    return Response(status_code=204)
