"""B12: the agent run and the POST /api/flows/{id}/agent route. Scripted models only, no network."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.ai.agent import history_messages, run_agent, tool_summary
from app.ai.models import MAX_TOOL_CALLS
from app.api import agent as agent_route
from app.engine import api as engine
from app.main import create_app
from tests.ai.test_tools import LIST_FLOW_LINKS, LIST_FLOW_STEPS, STARTER, UNLINK_STARTER, Recorder

pytestmark = pytest.mark.contract

ADD_STEPS_ARGS = {
    "steps": [s.model_dump(exclude_none=True) for s in LIST_FLOW_STEPS],
    "links": [lk.model_dump(exclude_none=True) for lk in LIST_FLOW_LINKS],
    "unlink": [lk.model_dump(exclude_none=True) for lk in UNLINK_STARTER],
}


def tool_calls_so_far(messages: list[ModelMessage]) -> int:
    return sum(1 for m in messages if isinstance(m, ModelResponse) for p in m.parts if isinstance(p, ToolCallPart))


def scripted(*steps):
    """A FunctionModel that answers with `steps[i]` on its i-th turn (each a list of parts or a callable)."""
    state = {"turn": 0}

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        step = steps[min(state["turn"], len(steps) - 1)]
        state["turn"] += 1
        parts = step(messages, info) if callable(step) else step
        return ModelResponse(parts=parts)

    return FunctionModel(fn)


def build_flow_model() -> FunctionModel:
    return scripted(
        [
            TextPart("I'll look at the page first."),
            ToolCallPart("fetch_page", {"url": "https://shop.example.com/list"}),
        ],
        [ToolCallPart("test_selector", {"url": "https://shop.example.com/list", "selector": ".price"})],
        [ToolCallPart("add_steps", ADD_STEPS_ARGS)],
        [ToolCallPart("dry_run", {})],
        [TextPart("Your flow is ready. Review the highlighted steps, press Accept, then Publish.")],
    )


async def run(model, draft=None, message="Track prices on https://shop.example.com/list", history=None):
    rec = Recorder()
    await run_agent(
        flow_id="fl_test",
        message=message,
        draft=draft or STARTER,
        selected_node_ids=[],
        history=history or [],
        emit=rec,
        model=model,
    )
    return rec.events


# ---------------------------------------------------------------------------
# run_agent
# ---------------------------------------------------------------------------
@pytest.mark.req("FR-06")
async def test_agent_builds_the_list_tracking_flow_from_one_sentence(fake_web, monkeypatch):
    fake_web["/list"] = fake_web["/shop"]  # the real mock shop page, served offline (tests/conftest.py)

    async def ok_report(flow, flow_id, until_node=None):  # the real dry run is tested in tests/engine/test_runner.py
        return {"verdict": "OK", "reason": "No changes since the last run", "items_found": 12, "items_valid": 12,
                "changes": {"new": 0, "changed": 0, "removed": 0}, "coverage": {}, "evidence": [], "items": []}

    monkeypatch.setattr(engine, "dry_run", ok_report)
    events = await run(build_flow_model())
    names = [e for e, _ in events]

    assert names[0] == "text" and names[-2:] == ["flow_ops", "done"]
    assert names.count("flow_ops") == 1  # one proposal, sent at the end
    assert "dry_run_result" in names
    chips = [d for e, d in events if e == "tool_call"]
    assert [c["name"] for c in chips] == ["fetch_page", "test_selector", "add_steps", "dry_run"]
    assert all(c["ok"] for c in chips)
    assert chips[1]["args"]["selector"] == ".price" and chips[1]["summary"].endswith("matches")
    assert chips[2]["summary"] == "6 steps, 7 links" and chips[2]["args"] == {"steps": 6}
    assert events[-1] == ("done", {"tool_calls": 4})

    # Accepting the proposal in the browser gives a flow the engine would dry-run and publish.
    from app.ai.tools import apply_op

    accepted = STARTER
    for op in events[-2][1]["ops"]:
        accepted = apply_op(accepted, op)
    assert engine.validate_flow(accepted) == []


@pytest.mark.req("FR-11")
async def test_a_refused_edit_shows_as_a_failed_chip_and_only_the_fix_is_proposed():
    model = scripted(
        [ToolCallPart("add_node", {"type": "fetch_page", "config": {"url": "file:///etc/passwd"}})],
        [ToolCallPart("add_node", {"type": "fetch_page", "config": {"url": "https://shop.example.com"}})],
        [TextPart("Added it.")],
    )
    events = await run(model)
    chips = [d for e, d in events if e == "tool_call"]
    assert [c["ok"] for c in chips] == [False, True]
    assert chips[0]["summary"].startswith("refused:") and "http" in chips[0]["summary"]
    ops = next(d["ops"] for e, d in events if e == "flow_ops")
    assert [op["node"]["config"]["url"] for op in ops] == ["https://shop.example.com"]


@pytest.mark.req("FR-11")
async def test_a_model_that_keeps_breaking_the_rules_ends_with_invalid_ai_reply_and_no_proposal():
    model = scripted([ToolCallPart("add_node", {"type": "fetch_page", "config": {"url": "ftp://x"}})])
    events = await run(model)
    assert events[-1] == ("error", {"code": "invalid_ai_reply", "message": events[-1][1]["message"]})
    assert "flow_ops" not in [e for e, _ in events] and "done" not in [e for e, _ in events]


@pytest.mark.req("FR-11")
async def test_an_unknown_tool_is_an_invalid_reply():
    events = await run(scripted([ToolCallPart("publish_flow", {})]))
    assert events[-1][1]["code"] == "invalid_ai_reply"


@pytest.mark.req("FR-10")
async def test_model_errors_mean_ai_unavailable_and_nothing_is_proposed():
    def boom(messages, info):
        raise ModelHTTPError(status_code=503, model_name="m", body="overloaded")

    model = scripted(
        [ToolCallPart("add_node", {"type": "fetch_page", "config": {"url": "https://shop.example.com"}})], boom
    )
    events = await run(model)
    assert events[-1][0] == "error" and events[-1][1]["code"] == "ai_unavailable"
    assert "flow_ops" not in [e for e, _ in events]


@pytest.mark.req("FR-10")
async def test_no_model_configured_means_ai_unavailable():
    events = await run(None)
    assert events == [("error", {"code": "ai_unavailable", "message": events[0][1]["message"]})]


@pytest.mark.req("FR-07")
async def test_more_than_the_tool_call_cap_stops_the_run():
    events = await run(scripted([ToolCallPart("get_flow", {})]))
    assert events[-1][1]["code"] == "tool_failed"
    assert sum(1 for e, _ in events if e == "tool_call") == MAX_TOOL_CALLS


async def test_instructions_carry_the_rules_the_draft_and_the_selection():
    seen = {}

    def look(messages, info):
        seen["instructions"] = next(m.instructions for m in messages if isinstance(m, ModelRequest) and m.instructions)
        return [TextPart("ok")]

    rec = Recorder()
    await run_agent(
        flow_id="fl_test",
        message="what does this step do?",
        draft=STARTER,
        selected_node_ids=["n_chk001"],
        history=[],
        emit=rec,
        model=scripted(look),
    )
    text = seen["instructions"]
    assert "untrusted data" in text and "cannot save, publish" in text
    assert '"id":"n_trig01"' in text and "selected: n_chk001" in text
    assert rec.events == [("text", {"delta": "ok\n\n"}), ("done", {"tool_calls": 0})]


async def test_chat_history_reaches_the_model():
    seen = {}

    def look(messages, info):
        seen["user"] = [p.content for m in messages for p in m.parts if isinstance(p, UserPromptPart)]
        return [TextPart("ok")]

    history = [{"role": "user", "content": "watch the kettle"}, {"role": "assistant", "content": "Which URL?"}]
    await run(scripted(look), message="https://shop.example.com/p/kettle", history=history)
    assert seen["user"] == ["watch the kettle", "https://shop.example.com/p/kettle"]


def test_history_is_trimmed_and_starts_with_a_user_turn():
    turns = [{"role": "assistant", "content": "hi"}] + [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"t{i}"} for i in range(30)
    ]
    msgs = history_messages(turns)
    assert isinstance(msgs[0], ModelRequest) and isinstance(msgs[-1], ModelResponse)
    assert len(msgs) <= 12


def test_tool_summaries():
    assert tool_summary("dry_run", {"runnable": True, "verdict": "OK", "items_found": 12}, True) == "OK · 12 items"
    assert tool_summary("dry_run", {"runnable": False}, True) == "not runnable yet"
    assert tool_summary("fetch_page", "Refused: internal address. Tell the user", True).startswith("refused")
    assert tool_summary("add_node", "That edit was not applied, because\n- n_x config.url: bad", False) == (
        "refused: n_x config.url: bad"
    )


# ---------------------------------------------------------------------------
# The HTTP route
# ---------------------------------------------------------------------------
@pytest.fixture
def app_client(tmp_path):
    agent_route.limiter.reset()
    app = create_app(database_url=f"sqlite+aiosqlite:///{(tmp_path / 'agent.db').as_posix()}")
    with TestClient(app, raise_server_exceptions=False) as client:
        yield app, client
    agent_route.limiter.reset()


def sse_events(text: str) -> list[tuple[str, dict]]:
    out = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        event = next((ln[7:].strip() for ln in block.splitlines() if ln.startswith("event: ")), None)
        data = "\n".join(ln[6:] for ln in block.splitlines() if ln.startswith("data: "))
        if event:
            out.append((event, json.loads(data) if data else {}))
    return out


def new_flow(client) -> dict:
    r = client.post("/api/flows", json={"name": "Agent test"})
    assert r.status_code in (200, 201), r.text
    return r.json()


@pytest.mark.req("FR-06")
def test_route_streams_c5_events_and_never_saves(app_client):
    app, client = app_client
    flow = new_flow(client)
    app.dependency_overrides[agent_route.agent_model] = lambda: scripted([TextPart("Hello! Which page?")])
    r = client.post(f"/api/flows/{flow['id']}/agent", json={"message": "hi", "draft": flow["draft"]})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    assert sse_events(r.text) == [("text", {"delta": "Hello! Which page?\n\n"}), ("done", {"tool_calls": 0})]
    assert client.get(f"/api/flows/{flow['id']}").json()["draft"] == flow["draft"]


@pytest.mark.req("FR-10")
def test_route_without_ai_config_streams_ai_unavailable(app_client, monkeypatch):
    _, client = app_client
    agent_route._model_for.cache_clear()
    flow = new_flow(client)
    r = client.post(f"/api/flows/{flow['id']}/agent", json={"message": "hi", "draft": flow["draft"]})
    assert [e for e, _ in sse_events(r.text)] == ["error"]
    assert sse_events(r.text)[0][1]["code"] == "ai_unavailable"


def test_route_rejects_unknown_flows_bad_drafts_and_extra_keys(app_client):
    app, client = app_client
    app.dependency_overrides[agent_route.agent_model] = lambda: scripted([TextPart("x")])
    flow = new_flow(client)
    assert client.post("/api/flows/nope/agent", json={"message": "hi", "draft": flow["draft"]}).status_code == 404
    bad = {
        **flow["draft"],
        "nodes": [*flow["draft"]["nodes"], {"id": "n_bad", "type": "fetch_page", "config": {"url": "file:///x"}}],
    }
    r = client.post(f"/api/flows/{flow['id']}/agent", json={"message": "hi", "draft": bad})
    assert r.status_code == 422 and r.json()["error"] == "invalid_flow"
    r = client.post(f"/api/flows/{flow['id']}/agent", json={"message": "hi", "draft": flow["draft"], "publish": True})
    assert r.status_code == 422
    r = client.post(f"/api/flows/{flow['id']}/agent", json={"message": "   ", "draft": flow["draft"]})
    assert r.status_code == 422


@pytest.mark.req("FR-35")
def test_route_allows_ten_messages_a_minute(app_client):
    app, client = app_client
    app.dependency_overrides[agent_route.agent_model] = lambda: scripted([TextPart("ok")])
    flow = new_flow(client)
    body = {"message": "hi", "draft": flow["draft"]}
    codes = [client.post(f"/api/flows/{flow['id']}/agent", json=body).status_code for _ in range(11)]
    assert codes == [200] * 10 + [429]
    assert client.post(f"/api/flows/{flow['id']}/agent", json=body).json()["error"] == "rate_limited"


# D-22: the review showed 15/15 messages accepted on real uvicorn when each claimed a different
# X-Forwarded-For. These replay that attack.
def _not_on_a_host(monkeypatch):
    for name in ("RENDER", "RAILWAY_ENVIRONMENT", "RAILWAY_PROJECT_ID", "REQUIRE_DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.req("FR-35")
def test_fake_forwarded_for_cannot_dodge_the_limit_on_a_host(app_client, monkeypatch):
    app, client = app_client
    _not_on_a_host(monkeypatch)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    app.dependency_overrides[agent_route.agent_model] = lambda: scripted([TextPart("ok")])
    flow = new_flow(client)
    body = {"message": "hi", "draft": flow["draft"]}
    codes = [
        client.post(f"/api/flows/{flow['id']}/agent", json=body,
                    # the client fakes the first entry; the platform proxy appends the real address
                    headers={"X-Forwarded-For": f"203.0.113.{i}, 198.51.100.7"}).status_code
        for i in range(11)
    ]
    assert codes == [200] * 10 + [429]


@pytest.mark.req("FR-35")
def test_forwarded_for_is_ignored_when_not_behind_a_host_proxy(app_client, monkeypatch):
    app, client = app_client
    _not_on_a_host(monkeypatch)
    app.dependency_overrides[agent_route.agent_model] = lambda: scripted([TextPart("ok")])
    flow = new_flow(client)
    body = {"message": "hi", "draft": flow["draft"]}
    codes = [client.post(f"/api/flows/{flow['id']}/agent", json=body,
                         headers={"X-Forwarded-For": f"203.0.113.{i}"}).status_code for i in range(11)]
    assert codes == [200] * 10 + [429]


@pytest.mark.req("FR-35")
def test_global_ceiling_holds_even_with_a_new_address_every_time(app_client, monkeypatch):
    app, client = app_client
    _not_on_a_host(monkeypatch)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.setattr(agent_route, "limiter", agent_route.RateLimiter(limit=10, global_limit=15))
    app.dependency_overrides[agent_route.agent_model] = lambda: scripted([TextPart("ok")])
    flow = new_flow(client)
    body = {"message": "hi", "draft": flow["draft"]}
    codes = [client.post(f"/api/flows/{flow['id']}/agent", json=body,
                         headers={"X-Forwarded-For": f"198.51.100.{i}"}).status_code for i in range(16)]
    assert codes == [200] * 15 + [429]  # 16 different "clients", still capped


@pytest.mark.req("FR-35")
def test_rate_limiter_forgets_idle_clients(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(agent_route.time, "monotonic", lambda: clock[0])
    limiter = agent_route.RateLimiter(limit=10, window_s=60, global_limit=10_000)
    for i in range(1_200):
        assert limiter.allow(f"fake-{i}")
    clock[0] = 120.0  # a window later, every one of them is idle
    assert limiter.allow("real-user")
    assert limiter.tracked_clients < 10
