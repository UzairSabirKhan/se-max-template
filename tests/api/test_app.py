"""API skeleton: health, error shape, flow CRUD with version checks (FR-01, FR-05, NFR-04)."""

import copy

import pytest
from fastapi.testclient import TestClient

from app.flow.cases import load_example
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    # A fresh SQLite file per test; the context manager runs startup (create tables) and shutdown.
    app = create_app(database_url=f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}")
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.mark.req("NFR-09")
def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "database": "ok"}


@pytest.mark.req("NFR-04")
def test_unknown_api_route_returns_json_error(client):
    r = client.get("/api/nope")
    assert r.status_code == 404
    assert r.json()["error"] == "not_found"


@pytest.mark.req("NFR-04")
def test_frontend_placeholder_or_spa_fallback(client):
    r = client.get("/flows/some-client-route")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


@pytest.mark.req("NFR-04")
def test_path_traversal_does_not_escape_web_dist(client):
    for path in ("/..%2F..%2Fpyproject.toml", "/../pyproject.toml", "/%2e%2e/%2e%2e/pyproject.toml"):
        r = client.get(path)
        assert "[project]" not in r.text, f"{path} leaked a file outside web/dist"


@pytest.mark.req("NFR-04")
def test_oversized_body_is_refused(client):
    r = client.post("/api/flows", content=b"x" * 1_000_001, headers={"content-type": "application/json"})
    assert r.status_code == 413
    assert r.json()["error"] == "too_large"


@pytest.mark.req("NFR-04")
def test_oversized_chunked_body_is_refused(client):
    def chunks():  # no Content-Length header: the limit must count the bytes received
        for _ in range(20):
            yield b"x" * 100_000

    r = client.post("/api/flows", content=chunks(), headers={"content-type": "application/json"})
    assert r.status_code == 413
    assert r.json()["error"] == "too_large"


@pytest.mark.req("NFR-04")
@pytest.mark.parametrize("path", ["/api", "/api/"])
def test_bare_api_path_is_a_json_404(client, path):
    r = client.get(path)
    assert r.status_code == 404
    assert r.json()["error"] == "not_found"


@pytest.mark.req("FR-05")
def test_save_without_version_is_a_clear_422(client):
    flow = client.post("/api/flows", json={"name": "A"}).json()
    draft = dict(flow["draft"])
    draft.pop("version")
    r = client.put(f"/api/flows/{flow['id']}", json={"draft": draft})
    assert r.status_code == 422
    assert "version" in r.json()["message"]


@pytest.mark.req("FR-02")
def test_editor_can_save_a_new_empty_step_then_fill_it_in(client):
    """The exact request the editor sent in the integration test that returned 422."""
    flow = client.post("/api/flows", json={"name": "Untitled flow"}).json()
    draft = copy.deepcopy(flow["draft"])
    draft["nodes"].append({"id": "n_1gsvz9", "type": "fetch_page",
                           "position": {"x": 703.8, "y": 16.0}, "config": {"url": ""}})
    saved = client.put(f"/api/flows/{flow['id']}", json={"name": "Untitled flow", "draft": draft})
    assert saved.status_code == 200, saved.json()

    draft = saved.json()["draft"]
    next(n for n in draft["nodes"] if n["id"] == "n_1gsvz9")["config"]["url"] = "https://example.com/shop"
    filled = client.put(f"/api/flows/{flow['id']}", json={"draft": draft})
    assert filled.status_code == 200
    assert client.post(f"/api/flows/{flow['id']}/publish").status_code == 422  # still incomplete overall


@pytest.mark.req("FR-23")
def test_saved_draft_is_the_normalised_version(client):
    flow = client.post("/api/flows", json={"name": "A"}).json()
    draft = load_example("multi_link")
    draft["version"] = flow["draft"]["version"]
    draft["variables"][0]["value"] = ["  https://a.example/x  ", "https://a.example/x"]
    client.put(f"/api/flows/{flow['id']}", json={"draft": draft})
    stored = client.get(f"/api/flows/{flow['id']}").json()["draft"]
    assert stored["variables"][0]["value"] == ["https://a.example/x"]


@pytest.mark.req("FR-01")
def test_create_list_get_delete_flow(client):
    created = client.post("/api/flows", json={"name": "Shop prices"})
    assert created.status_code == 201
    flow = created.json()
    assert flow["status"] == "draft"
    assert flow["draft"]["nodes"] == [] and flow["draft"]["edges"] == []  # a new flow starts empty
    assert [f["id"] for f in client.get("/api/flows").json()] == [flow["id"]]
    assert client.get(f"/api/flows/{flow['id']}").json()["name"] == "Shop prices"
    assert client.delete(f"/api/flows/{flow['id']}").status_code == 204
    assert client.get(f"/api/flows/{flow['id']}").status_code == 404


@pytest.mark.req("FR-01")
@pytest.mark.parametrize("name", ["", "<b>x</b>", "x" * 81])
def test_bad_flow_name_is_refused(client, name):
    r = client.post("/api/flows", json={"name": name})
    assert r.status_code == 422
    assert r.json()["error"] == "invalid_request"


@pytest.mark.req("FR-05")
def test_save_increments_version_and_detects_conflicts(client):
    flow = client.post("/api/flows", json={"name": "A"}).json()
    draft = load_example("list_tracking")
    draft["version"] = flow["draft"]["version"]
    saved = client.put(f"/api/flows/{flow['id']}", json={"draft": draft})
    assert saved.status_code == 200
    assert saved.json()["draft"]["version"] == draft["version"] + 1

    stale = client.put(f"/api/flows/{flow['id']}", json={"draft": draft})  # old version again
    assert stale.status_code == 409
    assert stale.json()["error"] == "version_conflict"


@pytest.mark.req("FR-03")
def test_save_refuses_unsafe_draft_with_issues(client):
    flow = client.post("/api/flows", json={"name": "A"}).json()
    draft = copy.deepcopy(flow["draft"])
    draft["nodes"].append({"id": "t1", "type": "trigger", "config": {"mode": "manual", "script": "rm -rf /"}})
    r = client.put(f"/api/flows/{flow['id']}", json={"draft": draft})
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "invalid_flow"
    assert body["issues"][0]["node_id"] == "t1"


@pytest.mark.req("FR-14")
def test_publish_refuses_incomplete_flow_then_accepts_complete_one(client, fake_web):
    flow = client.post("/api/flows", json={"name": "A"}).json()
    assert client.post(f"/api/flows/{flow['id']}/publish").status_code == 422  # starter is incomplete

    draft = load_example("list_tracking")
    draft["version"] = flow["draft"]["version"]
    client.put(f"/api/flows/{flow['id']}", json={"draft": draft})
    published = client.post(f"/api/flows/{flow['id']}/publish")
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    assert published.json()["published"]["nodes"] == published.json()["draft"]["nodes"]


@pytest.mark.req("FR-16")
def test_run_requires_published_flow(client):
    flow = client.post("/api/flows", json={"name": "A"}).json()
    r = client.post(f"/api/flows/{flow['id']}/run")
    assert r.status_code == 400
    assert r.json()["error"] == "not_published"


@pytest.mark.req("FR-13")
def test_dry_run_validates_before_running(client):
    flow = client.post("/api/flows", json={"name": "A"}).json()
    bad = client.post(f"/api/flows/{flow['id']}/dry-run", json={"draft": flow["draft"]})
    assert bad.status_code == 422
    ok = client.post(f"/api/flows/{flow['id']}/dry-run", json={"draft": load_example("list_tracking")})
    assert ok.status_code == 200
    assert ok.json()["ai_calls"] == 0


@pytest.mark.req("FR-07")
def test_node_types_catalogue(client):
    types = {t["type"]: t for t in client.get("/api/node-types").json()}
    assert types["click"]["disabled"] is True
    assert types["extract_list"]["disabled"] is False
    assert "properties" in types["extract_list"]["config_schema"]


@pytest.mark.req("FR-02")
def test_a_new_flow_is_empty_and_can_be_built_step_by_step(client):
    flow = client.post("/api/flows", json={"name": "Empty"}).json()
    draft = copy.deepcopy(flow["draft"])
    draft["nodes"].append({"id": "t1", "type": "trigger", "config": {"mode": "manual"}})
    saved = client.put(f"/api/flows/{flow['id']}", json={"draft": draft})
    assert saved.status_code == 200 and len(saved.json()["draft"]["nodes"]) == 1  # half-built drafts save
    issues = client.post(f"/api/flows/{flow['id']}/publish").json()["issues"]
    assert any("exactly one Check Page" in i["message"] for i in issues)        # publish says what's missing
