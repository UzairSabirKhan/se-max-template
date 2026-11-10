"""POST /api/flows/{id}/agent: chat with the sidebar agent about the open flow (C3, C5). Workstream B.

The request carries the browser's draft (which may hold unsaved edits); the reply is an SSE stream of
C5 events. The agent works on a copy: this route never saves the flow. Rate limited to 10 messages
per minute per client IP (FR-35).
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict, deque
from functools import lru_cache
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from pydantic_ai.models import Model
from sse_starlette.sse import EventSourceResponse

from app.ai.agent import run_agent
from app.ai.models import AIConfig, AIUnavailable, get_model
from app.api.errors import ApiError, invalid_flow
from app.api.routes import Repo, _load
from app.engine import api as engine

router = APIRouter(prefix="/api")

RATE_LIMIT = 10
RATE_WINDOW_S = 60.0


class ChatTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: Annotated[str, StringConstraints(max_length=4_000)]


class AgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000)]
    draft: dict[str, Any]
    selected_node_ids: list[Annotated[str, StringConstraints(max_length=32)]] = Field(
        default_factory=list, max_length=30
    )
    history: list[ChatTurn] = Field(default_factory=list, max_length=40)


class RateLimiter:
    """Sliding window per key, in memory. One uvicorn worker (ADR 0004), so one process holds it all."""

    def __init__(self, limit: int = RATE_LIMIT, window_s: float = RATE_WINDOW_S) -> None:
        self.limit = limit
        self.window_s = window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] >= self.window_s:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True

    def reset(self) -> None:
        self._hits.clear()


limiter = RateLimiter()


@lru_cache(maxsize=4)
def _model_for(config: AIConfig) -> Model:
    return get_model(config)


def agent_model() -> Model | None:
    """The configured model, or None when AI is unavailable (the stream then says so). Overridden in tests."""
    try:
        return _model_for(AIConfig.from_env())
    except AIUnavailable:
        return None


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/flows/{flow_id}/agent")
async def agent_chat(
    flow_id: str,
    body: AgentRequest,
    request: Request,
    repo: Repo,
    model: Annotated[Model | None, Depends(agent_model)],
) -> EventSourceResponse:
    if not limiter.allow(_client_key(request)):
        raise ApiError(429, "rate_limited", "You've sent 10 messages this minute. Wait a moment and try again.")
    await _load(repo, flow_id)
    draft, issues = engine.parse_flow(body.draft, draft=True)
    if issues or draft is None:
        raise invalid_flow(issues)

    queue: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()

    async def emit(event: str, data: dict[str, Any]) -> None:
        await queue.put((event, data))

    async def work() -> None:
        try:
            await run_agent(
                flow_id=flow_id,
                message=body.message,
                draft=draft,
                selected_node_ids=body.selected_node_ids,
                history=[t.model_dump() for t in body.history],
                emit=emit,
                model=model,
            )
        finally:
            await queue.put(None)

    async def events():
        task = asyncio.create_task(work())
        try:
            while (item := await queue.get()) is not None:
                event, data = item
                yield {"event": event, "data": json.dumps(data, ensure_ascii=False, default=str)}
        finally:
            if not task.done():
                task.cancel()  # the browser went away or pressed Stop

    return EventSourceResponse(events())
