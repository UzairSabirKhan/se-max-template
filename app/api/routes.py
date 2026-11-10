"""REST API (specs/contracts.md C3).

Status:
- REAL: node types; flow create / list / get / save / delete, stored in the database (A8) with an
  atomic version check; validation on save, dry run and publish; publish / pause / unpublish.
- STUB: run reports, runs, alerts, datasets, records, results, run stream. They return fixed
  example data from app/engine/stub_data.py until the engine lands (A13–A17).
The agent route (POST /api/flows/{id}/agent) belongs to Workstream B (app/api/agent.py).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, StringConstraints
from sse_starlette.sse import EventSourceResponse

from app.api.errors import ApiError, invalid_flow
from app.db.flows import FlowNotFound, FlowRepo, VersionConflict
from app.engine import api as engine
from app.engine import stub_data

router = APIRouter(prefix="/api")

FlowName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80,
                                            pattern=r"^[^<>{}`]+$")]


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


Repo = Annotated[FlowRepo, Depends(get_repo)]
NOT_FOUND = ApiError(404, "not_found", "Flow not found")


async def _load(repo: FlowRepo, flow_id: str) -> dict[str, Any]:
    try:
        return await repo.get(flow_id)
    except FlowNotFound:
        raise NOT_FOUND from None


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
async def delete_flow(flow_id: str, repo: Repo) -> Response:
    try:
        await repo.delete(flow_id)
    except FlowNotFound:
        raise NOT_FOUND from None
    return Response(status_code=204)


# --- lifecycle: validation real, execution stubbed -------------------------
@router.post("/flows/{flow_id}/dry-run")
async def dry_run(flow_id: str, body: DryRunRequest, repo: Repo) -> dict[str, Any]:
    await _load(repo, flow_id)
    normalised, issues = engine.parse_flow(body.draft)
    if issues:
        raise invalid_flow(issues)
    return await engine.dry_run(normalised, flow_id, body.until_node)


@router.post("/flows/{flow_id}/publish")
async def publish(flow_id: str, repo: Repo) -> dict[str, Any]:
    flow = await _load(repo, flow_id)
    issues = engine.validate_flow(flow["draft"], for_publish=True)
    if issues:
        raise invalid_flow(issues)
    return await repo.publish(flow_id)


@router.post("/flows/{flow_id}/pause")
async def pause(flow_id: str, repo: Repo) -> dict[str, Any]:
    flow = await _load(repo, flow_id)
    if flow["status"] != "published":
        raise ApiError(400, "not_published", "Only a published flow can be paused")
    return await repo.set_status(flow_id, "paused")


@router.post("/flows/{flow_id}/unpublish")
async def unpublish(flow_id: str, repo: Repo) -> dict[str, Any]:
    await _load(repo, flow_id)
    return await repo.set_status(flow_id, "draft")


@router.post("/flows/{flow_id}/run", status_code=202)
async def run_now(flow_id: str, repo: Repo) -> dict[str, Any]:
    flow = await _load(repo, flow_id)
    if flow["status"] != "published":
        raise ApiError(400, "not_published", "Publish the flow before running it")
    return {"run_id": "run_stub1"}  # STUB until the runner (A13)


# --- runs, results, alerts, data: STUBS ------------------------------------
@router.get("/flows/{flow_id}/runs")
async def list_runs(flow_id: str, repo: Repo, limit: int = Query(20, ge=1, le=100)) -> list[dict[str, Any]]:
    await _load(repo, flow_id)
    return [stub_data.run_summary(flow_id=flow_id, trigger="manual")][:limit]


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    return stub_data.run_report(run_id=run_id, trigger="manual")


@router.get("/runs/{run_id}/stream")
async def run_stream(run_id: str) -> EventSourceResponse:
    report = stub_data.run_report(run_id=run_id, trigger="manual")

    async def events():
        for step in report["node_trace"]:
            yield {"event": "node_started", "data": json.dumps({"node_id": step["node_id"]})}
            await asyncio.sleep(0.05)
            yield {"event": "node_finished", "data": json.dumps(step)}
        summary = {k: report[k] for k in stub_data.run_summary()}
        yield {"event": "finished", "data": json.dumps(summary)}

    return EventSourceResponse(events())


@router.get("/flows/{flow_id}/results")
async def results(flow_id: str, repo: Repo) -> list[dict[str, Any]]:
    await _load(repo, flow_id)
    return [{"node_id": "r1", "name": "Price changes", "items": stub_data.run_report()["items"][:1]}]


@router.get("/flows/{flow_id}/alerts")
async def list_alerts(flow_id: str, repo: Repo) -> list[dict[str, Any]]:
    await _load(repo, flow_id)
    return stub_data.alerts(flow_id)


@router.post("/alerts/{alert_id}/read", status_code=204)
def mark_alert_read(alert_id: str) -> Response:
    return Response(status_code=204)


@router.get("/flows/{flow_id}/datasets")
async def list_datasets(flow_id: str, repo: Repo) -> list[dict[str, Any]]:
    await _load(repo, flow_id)
    return stub_data.datasets(flow_id)


@router.get("/datasets/{dataset_id}/records")
def list_records(dataset_id: str, limit: int = Query(50, ge=1, le=500),
                 offset: int = Query(0, ge=0)) -> dict[str, Any]:
    rows = stub_data.records()
    return {"total": len(rows), "records": rows[offset: offset + limit]}


@router.get("/records/{record_id}/history")
def record_history(record_id: str) -> list[dict[str, Any]]:
    return stub_data.record_history()


@router.post("/datasets/{dataset_id}/reset", status_code=204)
def reset_dataset(dataset_id: str) -> Response:
    return Response(status_code=204)
