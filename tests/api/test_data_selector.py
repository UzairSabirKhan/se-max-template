"""Data selector (FR-02, FR-24): each step lists the fields it can use, from the steps BEFORE it."""

import pytest
from fastapi.testclient import TestClient

from app.flow.cases import load_example
from app.flow.selector import data_for_step, samples_from_report
from app.main import create_app


def names(result):
    return {g["label"]: [f["name"] for f in g["fields"]] for g in result["groups"]}


@pytest.mark.req("FR-24")
def test_condition_after_save_records_sees_fields_and_changes():
    result = data_for_step(load_example("list_tracking"), "c2", {"price": "1250.00"})
    assert names(result) == {"Extract List": ["title", "price", "url", "stock"],
                             "Save records (changes since the last run)": ["change"]}
    price = next(f for g in result["groups"] for f in g["fields"] if f["name"] == "price")
    assert price["sample"] == "1250.00" and price["type"] == "price"
    assert "lt" in price["ops"] and "drop_pct_gt" in price["ops"]  # change operators only after Save records


@pytest.mark.req("FR-24")
def test_without_save_records_there_are_no_change_fields():
    flow = load_example("list_tracking")
    result = data_for_step(flow, "s1")  # Save records itself: nothing saved BEFORE it
    assert "Save records (changes since the last run)" not in names(result)
    price = next(f for g in result["groups"] for f in g["fields"] if f["name"] == "price")
    assert "drop_pct_gt" not in price["ops"]


@pytest.mark.req("FR-22")
def test_loop_body_sees_only_the_link_and_after_the_loop_sees_what_it_read():
    flow = load_example("multi_link")
    assert names(data_for_step(flow, "b1")) == {"For Each": ["url"]}
    after = names(data_for_step(flow, "c1"))
    assert after["For Each"] == ["url", "title", "price"]


@pytest.mark.req("FR-02")
def test_a_step_never_sees_fields_from_later_steps():
    flow = load_example("list_tracking")
    assert names(data_for_step(flow, "e1")) == {}  # Extract list is where the fields are made
    assert names(data_for_step(flow, "t1")) == {}


@pytest.mark.req("FR-23")
def test_variables_are_listed_with_samples():
    variables = data_for_step(load_example("multi_link"), "c1")["variables"]
    assert [v["name"] for v in variables] == ["watch_urls", "min_drop_pct"]


@pytest.mark.req("FR-02")
def test_half_built_steps_are_skipped_not_a_crash():
    flow = {"version": 0, "variables": [], "edges": [{"id": "e", "source": "x1", "target": "c1"}],
            "nodes": [{"id": "x1", "type": "extract_list", "config": {"base_selector": "", "fields": []}},
                      {"id": "c1", "type": "condition", "config": {"match": "all", "rules": []}}]}
    assert data_for_step(flow, "c1")["groups"] == []
    assert data_for_step(flow, "nope")["error"]


def test_samples_come_from_a_run_report():
    report = {"items": [{"data": {"title": "Blue Kettle", "price": None}, "change": "new"},
                        {"data": {"price": "2400.00"}}]}
    assert samples_from_report(report) == {"title": "Blue Kettle", "price": "2400.00", "change": "new"}


@pytest.mark.req("FR-02")
def test_api_uses_the_unsaved_draft_and_the_latest_run(tmp_path, fake_web):
    with TestClient(create_app(database_url=f"sqlite+aiosqlite:///{(tmp_path / 'sel.db').as_posix()}"),
                    raise_server_exceptions=False) as client:
        flow = client.post("/api/flows", json={"name": "Shop"}).json()
        draft = load_example("list_tracking")
        client.post(f"/api/flows/{flow['id']}/dry-run", json={"draft": draft})  # gives sample values
        r = client.post(f"/api/flows/{flow['id']}/data-selector", json={"draft": draft, "node_id": "c2"})
        assert r.status_code == 200
        price = next(f for g in r.json()["groups"] for f in g["fields"] if f["name"] == "price")
        assert price["sample"] == "1250.00"
        assert client.post(f"/api/flows/{flow['id']}/data-selector",
                           json={"draft": draft, "node_id": "nope"}).status_code == 404
        assert client.post("/api/flows/nope/data-selector", json={"draft": draft, "node_id": "c2"}).status_code == 404
