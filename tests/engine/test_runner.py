"""The runner end to end (A13–A16; FR-13, FR-16, FR-17, FR-28 – FR-31, NFR-02, NFR-03, NFR-05).

Real runner, real records and alerts in a temporary SQLite database, the real mock-shop pages served
offline through the real safe_fetch (tests/conftest.py `fake_web`). This is the demo story:
first run -> no change -> a price change alert -> layout v2 -> BROKEN with nothing stored.
"""

import ast
import copy
import sys
from pathlib import Path

import pytest

from app.db.models import FlowRow
from app.db.runs import RunRepo
from app.db.session import Database, resolve_database_url
from app.engine import api as engine_api
from app.engine.runner import RunOptions, run_flow
from app.flow.cases import load_example
from app.mockshop.state import state
from tests.conftest import mock_shop_pages

SHOP = "https://shop.example.com/shop"


@pytest.fixture
async def db(tmp_path):
    database = Database(resolve_database_url(f"sqlite+aiosqlite:///{(tmp_path / 'runs.db').as_posix()}"))
    await database.create_tables()
    async with database.sessions() as s:  # runs, records and alerts belong to a flow (foreign keys)
        s.add(FlowRow(id="flow_demo", name="Demo", draft_json={}, draft_version=0))
        await s.commit()
    yield database
    await database.dispose()


def list_flow() -> dict:
    flow = load_example("list_tracking")
    next(n for n in flow["nodes"] if n["type"] == "fetch_page")["config"]["url"] = SHOP
    return flow


def rerender(pages: dict) -> None:
    pages.update(mock_shop_pages(reset=False))


async def run(db, flow, trigger="manual", **kw):
    return await run_flow(flow, "flow_demo", db, RunOptions(trigger=trigger, fetch=engine_api.fetch_options(), **kw))


async def alerts(db):
    async with db.sessions() as s:
        return await RunRepo(s).list_alerts("flow_demo")


async def records(db):
    async with db.sessions() as s:
        repo = RunRepo(s)
        ds = (await repo.list_datasets("flow_demo"))[0]
        return {r["key"].rsplit("/", 1)[-1]: r["data"] for r in (await repo.list_records(ds["id"], 100, 0))["records"]}


# --- the demo story --------------------------------------------------------------------------------
@pytest.mark.req("FR-29")
async def test_demo_story(db, fake_web):
    flow = list_flow()

    first = await run(db, flow)
    assert first["verdict"] == "CHANGED" and "starting point" in first["reason"]
    assert first["items_found"] == 12 and first["ai_calls"] == 0            # 2 pages followed
    assert [p["status"] for p in first["http"]] == [200, 200]
    assert await alerts(db) == []                                          # baseline: no "new" alerts
    assert len(await records(db)) == 12

    second = await run(db, flow)
    assert second["verdict"] == "OK" and second["changes"] == {"new": 0, "changed": 0, "removed": 0}

    state.find("blue-kettle").price = state.find("blue-kettle").price.__class__("1099")
    rerender(fake_web)
    third = await run(db, flow)
    assert third["verdict"] == "CHANGED" and third["changes"]["changed"] == 1
    [alert] = await alerts(db)
    assert alert["title"] == "Price changed" and alert["message"] == "Blue Kettle: Rs 1,250 → Rs 1,099 (−12%)"
    assert (await records(db))["blue-kettle"]["price"] == "1099.00"

    state.layout = "v2"
    rerender(fake_web)
    broken = await run(db, flow)
    assert broken["verdict"] == "BROKEN" and broken["reason"] == "price missing on 12 of 12 items"
    site_changed = [a for a in await alerts(db) if a["kind"] == "site_changed"]
    assert len(site_changed) == 1 and "Nothing was stored" in site_changed[0]["message"]
    assert (await records(db))["blue-kettle"]["price"] == "1099.00"        # last good data kept
    assert broken["ai_calls"] == 0

    await run(db, flow)                                                    # still broken
    assert len([a for a in await alerts(db) if a["kind"] == "site_changed"]) == 1  # not repeated


@pytest.mark.req("FR-31")
async def test_same_condition_does_not_alert_twice(db, fake_web):
    flow = list_flow()
    await run(db, flow)
    state.find("tea-set").price = state.find("tea-set").price.__class__("3500")
    rerender(fake_web)
    await run(db, flow)
    await run(db, flow)  # same price again: no new change, no new alert
    assert len(await alerts(db)) == 1


@pytest.mark.req("FR-31")
async def test_blocked_twice(db, fake_web):
    """EC-27: the first BLOCKED run is quiet, the second in a row alerts."""
    flow = list_flow()
    await run(db, flow)
    state.mode = "blocked"
    rerender(fake_web)
    first = await run(db, flow)
    assert first["verdict"] == "BLOCKED" and await alerts(db) == []
    await run(db, flow)
    assert [a["kind"] for a in await alerts(db)] == ["blocked"]


@pytest.mark.req("FR-20")
async def test_js_page_is_unsupported(db, fake_web):
    flow = list_flow()
    next(n for n in flow["nodes"] if n["type"] == "fetch_page")["config"]["url"] = SHOP + "?mode=js"
    report = await run(db, flow)
    assert report["verdict"] == "UNSUPPORTED"


@pytest.mark.req("FR-13")
async def test_dry_run_writes_no_records_or_alerts(db, fake_web):
    flow = list_flow()
    report = await run(db, flow, trigger="dry_run")
    assert report["verdict"] == "CHANGED" and all(i["change"] == "new" for i in report["items"])
    async with db.sessions() as s:
        assert await RunRepo(s).list_datasets("flow_demo") == []
    assert await alerts(db) == []


@pytest.mark.req("FR-17")
async def test_report_has_trace_coverage_and_http_facts(db, fake_web):
    report = await run(db, list_flow())
    traced = {t["node_id"] for t in report["node_trace"]}
    assert {"t1", "f1", "p1", "e1", "k1", "s1", "c1", "c2", "a1", "a2"} <= traced
    assert report["coverage"] == {"title": 1.0, "price": 1.0, "url": 1.0, "stock": 1.0}
    async with db.sessions() as s:
        stored = await RunRepo(s).get_run(report["id"])
    assert stored["verdict"] == report["verdict"] and stored["ai_calls"] == 0


# --- multi-link flow: a loop over a url_list variable -------------------------------------------------
def multi_flow() -> dict:
    flow = load_example("multi_link")
    flow["variables"][0]["value"] = [f"{SHOP}/p/blue-kettle", f"{SHOP}/p/steel-flask", f"{SHOP}/p/tea-set"]
    return flow


@pytest.mark.req("FR-22")
async def test_watch_list_of_product_pages(db, fake_web):
    first = await run(db, multi_flow())
    assert first["verdict"] == "CHANGED" and first["items_found"] == 3
    assert [i["status"] for i in first["iterations"]] == ["ok", "ok", "ok"]
    prices = {i["key"].rsplit("/", 1)[-1]: i["data"]["price"] for i in first["items"]}
    assert prices == {"blue-kettle": "1250.00", "steel-flask": "2400.00", "tea-set": "3999.00"}

    state.find("steel-flask").price = state.find("steel-flask").price.__class__("2150")
    rerender(fake_web)
    second = await run(db, multi_flow())
    assert second["verdict"] == "CHANGED"
    [alert] = await alerts(db)
    assert alert["title"] == "Price dropped" and alert["message"] == "Steel Flask: Rs 2,400 → Rs 2,150 (−10%)"


@pytest.mark.req("FR-22")
async def test_one_failed_page_is_skipped_half_failed_is_broken(db, fake_web):
    flow = multi_flow()
    flow["variables"][0]["value"][1] = f"{SHOP}/p/does-not-exist"
    one_bad = await run(db, flow, trigger="dry_run")
    assert one_bad["verdict"] == "CHANGED" and [i["status"] for i in one_bad["iterations"]] == ["ok", "error", "ok"]
    flow["variables"][0]["value"][2] = f"{SHOP}/p/also-missing"
    assert (await run(db, flow, trigger="dry_run"))["verdict"] == "BROKEN"


@pytest.mark.req("FR-22")
async def test_loop_limit(db, fake_web):
    flow = multi_flow()
    next(n for n in flow["nodes"] if n["type"] == "for_each")["config"]["max_items"] = 2
    report = await run(db, flow, trigger="dry_run")
    assert len(report["iterations"]) == 2 and any("limited to 2 of 3" in e for e in report["evidence"])


# --- determinism, deadline, zero AI ------------------------------------------------------------------------
@pytest.mark.req("NFR-03")
async def test_determinism(db, fake_web):
    """EC-54: the same page gives the same data every time (ids and timestamps aside)."""
    flow = list_flow()
    outputs = []
    for _ in range(20):
        report = await run(db, flow, trigger="dry_run")
        outputs.append([(i["key"], i["data"]) for i in report["items"]])
    assert all(o == outputs[0] for o in outputs) and len(outputs[0]) == 12


@pytest.mark.req("FR-26")
async def test_deadline(db, fake_web):
    """EC-15"""
    report = await run(db, list_flow(), deadline_s=0.0001)
    assert report["verdict"] == "BLOCKED" and "deadline" in report["reason"]


ENGINE_DIRS = ["app/engine", "app/db", "app/flow", "app/mockshop"]


@pytest.mark.req("NFR-02")
def test_engine_imports_no_ai():
    """EC-53, part 1: nothing that runs a flow imports app.ai or an AI SDK."""
    root = Path(__file__).resolve().parents[2]
    banned = ("app.ai", "pydantic_ai", "anthropic", "google.genai", "groq", "openai")
    offenders = []
    for folder in ENGINE_DIRS:
        for path in (root / folder).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                offenders += [f"{path.relative_to(root)}: {n}" for n in names if n.startswith(banned)]
    assert offenders == []


@pytest.mark.req("NFR-02")
async def test_run_works_with_ai_made_impossible(db, fake_web, monkeypatch):
    """EC-53, part 2: with every AI module blocked, a run still works and records ai_calls == 0."""
    for name in [m for m in sys.modules if m.startswith(("app.ai", "pydantic_ai", "anthropic", "groq"))]:
        monkeypatch.setitem(sys.modules, name, None)  # any import of them now raises
    report = await run(db, copy.deepcopy(list_flow()))
    assert report["verdict"] == "CHANGED" and report["ai_calls"] == 0
