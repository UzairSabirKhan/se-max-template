"""B15 / EC-52: when AI is unavailable the sidebar says so, and published flows still publish and run.

Runs never use AI (NFR-02); these tests prove the flow lifecycle doesn't even need the AI to be
configured, while the agent route reports `ai_unavailable` instead of failing.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.ai.models as ai_models
from app.api import agent as agent_route
from app.flow.cases import load_example
from app.main import create_app
from tests.ai.test_agent import sse_events

pytestmark = pytest.mark.contract


@pytest.fixture
def client(tmp_path, fake_web):  # publish test-runs the flow
    agent_route.limiter.reset()
    agent_route._model_for.cache_clear()
    app = create_app(database_url=f"sqlite+aiosqlite:///{(tmp_path / 'noai.db').as_posix()}")
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    agent_route._model_for.cache_clear()


def published_flow(client) -> dict:
    flow = client.post("/api/flows", json={"name": "No AI"}).json()
    draft = load_example("list_tracking")
    draft["version"] = flow["draft"]["version"]
    saved = client.put(f"/api/flows/{flow['id']}", json={"draft": draft})
    assert saved.status_code == 200, saved.text
    published = client.post(f"/api/flows/{flow['id']}/publish")
    assert published.status_code == 200, published.text
    return published.json()


@pytest.mark.req("FR-10")
@pytest.mark.req("NFR-02")
def test_published_flows_publish_and_run_with_no_ai_configured(client):
    flow = published_flow(client)
    assert flow["status"] == "published"
    assert client.post(f"/api/flows/{flow['id']}/run").status_code == 202


@pytest.mark.req("FR-10")
def test_published_flows_still_run_when_the_ai_client_raises(client, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("AI provider exploded")

    monkeypatch.setattr(ai_models, "get_model", broken)
    monkeypatch.setattr(agent_route, "get_model", broken)
    flow = published_flow(client)
    assert client.post(f"/api/flows/{flow['id']}/run").status_code == 202


@pytest.mark.req("FR-10")
def test_sidebar_gets_ai_unavailable_when_no_key_is_set(client, monkeypatch):
    monkeypatch.setenv("AI_MODEL", "anthropic:some-claude-model")  # configured, but no ANTHROPIC_API_KEY
    flow = published_flow(client)
    r = client.post(f"/api/flows/{flow['id']}/agent", json={"message": "hi", "draft": flow["draft"]})
    assert r.status_code == 200
    events = sse_events(r.text)
    assert [e for e, _ in events] == ["error"] and events[0][1]["code"] == "ai_unavailable"
    # The flow is untouched and still runs.
    assert client.get(f"/api/flows/{flow['id']}").json()["status"] == "published"
    assert client.post(f"/api/flows/{flow['id']}/run").status_code == 202


@pytest.mark.req("FR-10")
def test_an_unknown_provider_is_offline_not_a_crash(client, monkeypatch):
    monkeypatch.setenv("AI_MODEL", "nosuchprovider:model-x")
    flow = client.post("/api/flows", json={"name": "x"}).json()
    r = client.post(f"/api/flows/{flow['id']}/agent", json={"message": "hi", "draft": flow["draft"]})
    assert r.status_code == 200 and sse_events(r.text)[0][1]["code"] == "ai_unavailable"
