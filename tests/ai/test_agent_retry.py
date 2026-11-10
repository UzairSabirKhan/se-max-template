"""The assistant retries instead of stopping (FR-10, FR-11): a busy AI provider is retried with waits,
problems retrying can't fix are not, and hitting the step limit keeps the validated work."""

import pytest
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.ai.agent import run_agent
from app.ai.models import MAX_MODEL_REQUESTS
from tests.ai.test_tools import STARTER, Recorder

pytestmark = pytest.mark.contract


def flaky(failures: int, status: int = 503, retry_after: float | None = None):
    calls = {"n": 0}

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls["n"] += 1
        if calls["n"] <= failures:
            raise ModelHTTPError(status, "test-model", {"error": "busy"}, retry_after=retry_after)
        return ModelResponse(parts=[TextPart("Done.")])
    return FunctionModel(fn), calls


async def run(model, waits):
    rec = Recorder()

    async def sleep(seconds):
        waits.append(seconds)

    await run_agent(flow_id="fl_test", message="hi", draft=STARTER, selected_node_ids=[], history=[],
                    emit=rec, model=model, sleep=sleep)
    return rec.events


@pytest.mark.req("FR-10")
async def test_busy_provider_is_retried_then_answers():
    model, calls = flaky(2, status=503)
    waits: list[float] = []
    events = await run(model, waits)
    assert waits == [3.0, 8.0] and calls["n"] == 3
    assert [e for e, _ in events][-1] == "done"
    assert sum("Retrying in" in d.get("delta", "") for e, d in events if e == "text") == 2


@pytest.mark.req("FR-10")
async def test_rate_limit_uses_the_providers_retry_after():
    model, _ = flaky(1, status=429, retry_after=5)
    waits: list[float] = []
    await run(model, waits)
    assert waits == [5]


@pytest.mark.req("FR-10")
async def test_gives_up_with_ai_unavailable_after_the_retries():
    model, calls = flaky(10, status=503)
    waits: list[float] = []
    events = await run(model, waits)
    assert calls["n"] == 3 and events[-1] == ("error", {"code": "ai_unavailable", "message": events[-1][1]["message"]})


@pytest.mark.req("FR-10")
async def test_a_wrong_key_is_not_retried():
    model, calls = flaky(10, status=401)
    waits: list[float] = []
    events = await run(model, waits)
    assert waits == [] and calls["n"] == 1 and events[-1][0] == "error"


@pytest.mark.req("FR-11")
async def test_step_limit_keeps_the_validated_edits():
    """Adds a valid wait step, then goes round in circles until the loop guard: the edit is proposed, not lost."""
    turn = {"n": 0}

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        turn["n"] += 1
        call = (ToolCallPart("add_node", {"type": "wait", "config": {"seconds": 2}}, tool_call_id="c1")
                if turn["n"] == 1 else ToolCallPart("get_flow", {}, tool_call_id=f"c{turn['n']}"))
        return ModelResponse(parts=[call])

    waits: list[float] = []
    events = await run(FunctionModel(fn), waits)
    names = [e for e, _ in events]
    assert names[-2:] == ["flow_ops", "done"] and "error" not in names
    ops = dict(events)["flow_ops"]["ops"]
    assert turn["n"] == MAX_MODEL_REQUESTS and len(ops) == 1 and all(op["op"] == "add_node" for op in ops)
    assert any("continue" in d.get("delta", "") for e, d in events if e == "text")
