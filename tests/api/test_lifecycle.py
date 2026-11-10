"""The real lifecycle routes (A17, A18; FR-13 – FR-17, FR-31, FR-32, EC-49, EC-50) through the HTTP API.

Uses the real app, a temporary database, and the real mock-shop pages served offline (`fake_web`).
"""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

import app.engine.runner as runner_module
from app.flow.cases import load_example
from app.main import create_app
from app.mockshop.state import state
from tests.conftest import mock_shop_pages


@pytest.fixture
def make_client(tmp_path):
    url = f"sqlite+aiosqlite:///{(tmp_path / 'life.db').as_posix()}"
    clients = []

    def make():
        c = TestClient(create_app(database_url=url), raise_server_exceptions=False)
        clients.append(c)
        return c
    yield make
    state.reset()


def save_example(client, name="list_tracking", edit=None) -> dict:
    flow = client.post("/api/flows", json={"name": "Shop prices"}).json()
    draft = load_example(name)
    if edit:
        edit(draft)
    draft["version"] = flow["draft"]["version"]
    saved = client.put(f"/api/flows/{flow['id']}", json={"draft": draft})
    assert saved.status_code == 200, saved.text
    return saved.json()


def run_and_wait(client, flow_id) -> dict:
    started = client.post(f"/api/flows/{flow_id}/run")
    assert started.status_code == 202, started.text
    run_id = started.json()["run_id"]
    stream = client.get(f"/api/runs/{run_id}/stream")  # reads until the run finishes
    assert "event: finished" in stream.text
    report = client.get(f"/api/runs/{run_id}")
    assert report.status_code == 200
    return report.json()


@pytest.mark.req("FR-14")
def test_publish_test_runs_the_flow_and_sets_the_schedule(make_client, fake_web):
    with make_client() as client:
        flow = save_example(client)
        published = client.post(f"/api/flows/{flow['id']}/publish")
        assert published.status_code == 200, published.text
        body = published.json()
        extract = next(n for n in body["published"]["nodes"] if n["type"] == "extract_list")
        assert extract["config"]["expected_count"] == {"min": 10, "max": 40}  # kept from the example
        assert client.app.state.scheduler.job_ids() == [flow["id"]]       # interval trigger -> a job
        client.post(f"/api/flows/{flow['id']}/pause")
        assert client.app.state.scheduler.job_ids() == []


@pytest.mark.req("FR-14")
def test_publish_fills_in_an_expected_count_when_missing(make_client, fake_web):
    def no_range(draft):
        next(n for n in draft["nodes"] if n["type"] == "extract_list")["config"].pop("expected_count")

    with make_client() as client:
        flow = save_example(client, edit=no_range)
        body = client.post(f"/api/flows/{flow['id']}/publish").json()
        extract = next(n for n in body["published"]["nodes"] if n["type"] == "extract_list")
        assert extract["config"]["expected_count"] == {"min": 6, "max": 24}   # 12 items found
        assert "expected_count" not in next(n for n in body["draft"]["nodes"] if n["type"] == "extract_list")["config"]


@pytest.mark.req("FR-14")
def test_publish_refuses_a_flow_whose_test_run_is_broken(make_client, fake_web):
    with make_client() as client:
        flow = save_example(client)
        state.layout = "v2"
        fake_web.update(mock_shop_pages(reset=False))
        refused = client.post(f"/api/flows/{flow['id']}/publish")
        assert refused.status_code == 422 and refused.json()["error"] == "publish_check_failed"
        assert "price missing on 12 of 12 items" in refused.json()["message"]
        assert client.get(f"/api/flows/{flow['id']}").json()["status"] == "draft"


@pytest.mark.req("FR-16")
def test_run_now_streams_progress_and_stores_the_report(make_client, fake_web):
    with make_client() as client:
        flow = save_example(client)
        client.post(f"/api/flows/{flow['id']}/publish")
        report = run_and_wait(client, flow["id"])
        assert report["trigger"] == "manual" and report["verdict"] in ("CHANGED", "OK") and report["ai_calls"] == 0
        runs = client.get(f"/api/flows/{flow['id']}/runs").json()
        assert [r["trigger"] for r in runs][:2] == ["manual", "dry_run"]  # newest first; the publish test run
        stream = client.get(f"/api/runs/{report['id']}/stream").text   # a finished run can be replayed
        events = [line[7:] for line in stream.splitlines() if line.startswith("event: ")]
        assert events[-1] == "finished" and "node_finished" in events


@pytest.mark.req("FR-16")
def test_double_click_gives_one_run(make_client, fake_web, monkeypatch):
    """EC-49: a second Run now while one is running is refused; only one run happens."""
    real = runner_module.safe_fetch

    async def slow(url, options=None):
        await asyncio.sleep(0.3)
        return await real(url, options)

    with make_client() as client:
        flow = save_example(client)
        client.post(f"/api/flows/{flow['id']}/publish")
        monkeypatch.setattr(runner_module, "safe_fetch", slow)
        first = client.post(f"/api/flows/{flow['id']}/run")
        second = client.post(f"/api/flows/{flow['id']}/run")
        assert first.status_code == 202 and second.status_code == 409
        assert second.json()["error"] == "already_running"
        client.get(f"/api/runs/{first.json()['run_id']}/stream")
        assert sum(1 for r in client.get(f"/api/flows/{flow['id']}/runs").json() if r["trigger"] == "manual") == 1


@pytest.mark.req("FR-31")
def test_alerts_data_history_and_csv_through_the_api(make_client, fake_web):
    with make_client() as client:
        flow = save_example(client)
        client.post(f"/api/flows/{flow['id']}/publish")
        run_and_wait(client, flow["id"])
        state.find("blue-kettle").price = state.find("blue-kettle").price.__class__("1099")
        fake_web.update(mock_shop_pages(reset=False))
        assert run_and_wait(client, flow["id"])["verdict"] == "CHANGED"

        [alert] = client.get(f"/api/flows/{flow['id']}/alerts").json()
        assert alert["message"] == "Blue Kettle: Rs 1,250 → Rs 1,099 (−12%)" and alert["read"] is False
        assert client.get("/api/flows").json()[0]["unread_alerts"] == 1
        assert client.post(f"/api/alerts/{alert['id']}/read").status_code == 204
        assert client.get("/api/flows").json()[0]["unread_alerts"] == 0

        [dataset] = client.get(f"/api/flows/{flow['id']}/datasets").json()
        assert dataset["name"] == "shop_prices" and dataset["record_count"] == 12
        records = client.get(f"/api/datasets/{dataset['id']}/records?limit=50").json()
        kettle = next(r for r in records["records"] if r["key"].endswith("blue-kettle"))
        history = client.get(f"/api/records/{kettle['id']}/history").json()
        assert [h["change"] for h in history] == ["new", "changed"]
        assert history[1] == {**history[1], "field": "price", "old_value": "1250.00", "new_value": "1099.00",
                              "pct_change": -12.08}
        csv = client.get(f"/api/datasets/{dataset['id']}/export.csv")
        assert csv.headers["content-type"].startswith("text/csv") and "1099.00" in csv.text


@pytest.mark.req("FR-13")
def test_dry_run_of_a_draft(make_client, fake_web):
    with make_client() as client:
        flow = save_example(client)
        report = client.post(f"/api/flows/{flow['id']}/dry-run", json={"draft": flow["draft"]})
        assert report.status_code == 200 and report.json()["trigger"] == "dry_run"
        assert report.json()["items_found"] == 12
        assert client.get(f"/api/flows/{flow['id']}/datasets").json() == []   # dry runs store no records


@pytest.mark.req("FR-15")
def test_schedules_are_rebuilt_after_a_restart(make_client, fake_web):
    with make_client() as first:
        flow = save_example(first)
        first.post(f"/api/flows/{flow['id']}/publish")
    with make_client() as second:  # a new process on the same database
        assert second.app.state.scheduler.job_ids() == [flow["id"]]


@pytest.mark.req("FR-15")
def test_manual_flows_get_no_job_and_unpublish_removes_it(make_client, fake_web):
    def manual(draft):
        next(n for n in draft["nodes"] if n["type"] == "trigger")["config"] = {"mode": "manual"}

    with make_client() as client:
        flow = save_example(client, edit=manual)
        client.post(f"/api/flows/{flow['id']}/publish")
        assert client.app.state.scheduler.job_ids() == []
        other = save_example(client)
        client.post(f"/api/flows/{other['id']}/publish")
        assert client.app.state.scheduler.job_ids() == [other["id"]]
        client.post(f"/api/flows/{other['id']}/unpublish")
        assert client.app.state.scheduler.job_ids() == []


@pytest.mark.req("NFR-04")
def test_unknown_runs_datasets_and_alerts_are_404(make_client):
    with make_client() as client:
        for path in ["/api/runs/nope", "/api/runs/nope/stream", "/api/datasets/nope/records",
                     "/api/datasets/nope/export.csv"]:
            assert client.get(path).status_code == 404, path
        assert client.post("/api/alerts/nope/read").status_code == 404
        assert client.post("/api/datasets/nope/reset").status_code == 404


def test_report_json_is_serialisable(make_client, fake_web):
    with make_client() as client:
        flow = save_example(client)
        report = client.post(f"/api/flows/{flow['id']}/dry-run", json={"draft": flow["draft"]}).json()
        assert json.loads(json.dumps(report)) == report
