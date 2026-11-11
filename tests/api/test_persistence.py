"""Flows are stored in a database, not in memory (A7, A8; FR-01, FR-05, NFR-09).

The default suite runs on SQLite. test_postgres_round_trip runs the same checks on a real
Postgres when DATABASE_URL points at one (marked live; never in CI).
"""

import asyncio
import os

import pytest
from fastapi.testclient import TestClient

from app.db.flows import FlowRepo, VersionConflict
from app.db.models import AlertRow
from app.db.session import Database, DatabaseConfigError, resolve_database_url, running_on_host
from app.flow.cases import load_example
from app.main import create_app


def sqlite_url(tmp_path) -> str:
    return f"sqlite+aiosqlite:///{(tmp_path / 'flows.db').as_posix()}"


def make_client(url: str) -> TestClient:
    return TestClient(create_app(database_url=url), raise_server_exceptions=False)


def create_and_save(client: TestClient) -> tuple[str, int]:
    flow = client.post("/api/flows", json={"name": "Shop prices"}).json()
    draft = load_example("list_tracking")
    draft["version"] = flow["draft"]["version"]
    saved = client.put(f"/api/flows/{flow['id']}", json={"draft": draft}).json()
    return flow["id"], saved["draft"]["version"]


@pytest.mark.req("FR-01")
def test_flows_survive_a_restart(tmp_path, fake_web):
    url = sqlite_url(tmp_path)
    with make_client(url) as first:
        flow_id, version = create_and_save(first)
        first.post(f"/api/flows/{flow_id}/publish")

    with make_client(url) as second:  # a brand-new app process on the same database
        flow = second.get(f"/api/flows/{flow_id}").json()
        assert flow["name"] == "Shop prices"
        assert flow["status"] == "published"
        assert flow["draft"]["version"] == version
        assert flow["published"]["nodes"] == flow["draft"]["nodes"]
        assert [f["id"] for f in second.get("/api/flows").json()] == [flow_id]


@pytest.mark.req("FR-05")
async def test_two_saves_racing_on_one_version_cannot_both_win(tmp_path):
    db = Database(resolve_database_url(sqlite_url(tmp_path)))
    await db.create_tables()
    try:
        async with db.sessions() as s:
            flow = await FlowRepo(s).create("Race")
        draft = load_example("list_tracking")
        draft["version"] = flow["draft"]["version"]

        async def save(title: str):
            async with db.sessions() as s:
                d = {**draft, "nodes": [{**n, "config": {**n["config"], "title": title}} if n["id"] == "a1" else n
                                        for n in draft["nodes"]]}
                return await FlowRepo(s).save_draft(flow["id"], d, None)

        results = await asyncio.gather(save("First"), save("Second"), return_exceptions=True)
        wins = [r for r in results if isinstance(r, dict)]
        conflicts = [r for r in results if isinstance(r, VersionConflict)]
        assert len(wins) == 1 and len(conflicts) == 1, results

        async with db.sessions() as s:
            stored = await FlowRepo(s).get(flow["id"])
        assert stored["draft"]["version"] == draft["version"] + 1
        winner_title = next(n for n in wins[0]["draft"]["nodes"] if n["id"] == "a1")["config"]["title"]
        assert next(n for n in stored["draft"]["nodes"] if n["id"] == "a1")["config"]["title"] == winner_title
    finally:
        await db.dispose()


@pytest.mark.req("FR-31")
async def test_unread_alert_count_and_cascade_delete(tmp_path):
    db = Database(resolve_database_url(sqlite_url(tmp_path)))
    await db.create_tables()
    try:
        async with db.sessions() as s:
            repo = FlowRepo(s)
            flow = await repo.create("Alerts")
            s.add_all([
                AlertRow(id="al1", flow_id=flow["id"], run_id="r1", kind="condition", level="info",
                         title="t", message="m", items_json=[], dedupe_key="k1"),
                AlertRow(id="al2", flow_id=flow["id"], run_id="r1", kind="condition", level="info",
                         title="t", message="m", items_json=[], dedupe_key="k2"),
            ])
            await s.commit()
            assert (await repo.list())[0]["unread_alerts"] == 2

            await repo.delete(flow["id"])
            assert await s.get(AlertRow, "al1") is None  # ON DELETE CASCADE works on SQLite too
    finally:
        await db.dispose()


@pytest.mark.req("NFR-09")
def test_health_reports_503_when_the_database_is_down(tmp_path, monkeypatch):
    with make_client(sqlite_url(tmp_path)) as client:
        async def broken_ping(*_, **__):
            raise ConnectionError("database is down")
        monkeypatch.setattr(client.app.state.db, "ping", broken_ping)
        r = client.get("/health")
        assert r.status_code == 503
        assert r.json() == {"status": "degraded", "database": "unreachable"}


# --- DATABASE_URL handling ---------------------------------------------------
@pytest.mark.req("NFR-09")
def test_neon_url_is_converted_for_asyncpg():
    target = resolve_database_url(
        "postgresql://user:pw@ep-cool-1234-pooler.eu-central-1.aws.neon.tech/neondb"
        "?sslmode=require&channel_binding=require", host="Render")
    assert target.url == "postgresql+asyncpg://user:pw@ep-cool-1234-pooler.eu-central-1.aws.neon.tech/neondb"
    assert target.connect_args == {"statement_cache_size": 0, "ssl": "require"}
    assert target.is_sqlite is False


@pytest.mark.req("NFR-09")
def test_postgres_scheme_alias_is_accepted():
    assert resolve_database_url("postgres://u:p@h/db", host=None).url == "postgresql+asyncpg://u:p@h/db"


@pytest.mark.req("NFR-09")
def test_missing_database_url_on_render_fails_loudly():
    with pytest.raises(DatabaseConfigError, match="On Render"):
        resolve_database_url("", host="Render")


@pytest.mark.req("NFR-09")
@pytest.mark.parametrize("marker,host", [
    ("RENDER", "Render"), ("RAILWAY_ENVIRONMENT", "Railway"), ("RAILWAY_PROJECT_ID", "Railway"),
    ("REQUIRE_DATABASE_URL", "this host"),
])
def test_every_host_is_detected_and_refuses_to_lose_data(monkeypatch, marker, host):
    for name in ("RENDER", "RAILWAY_ENVIRONMENT", "RAILWAY_PROJECT_ID", "REQUIRE_DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(marker, "1")
    assert running_on_host() == host
    with pytest.raises(DatabaseConfigError, match=f"On {host}"):
        resolve_database_url("")
    with pytest.raises(DatabaseConfigError, match="not persistent"):
        resolve_database_url("sqlite:///x.db")


@pytest.mark.req("NFR-09")
def test_railway_internal_postgres_url_is_accepted():
    target = resolve_database_url("postgresql://postgres:pw@postgres.railway.internal:5432/railway", host="Railway")
    assert target.url == "postgresql+asyncpg://postgres:pw@postgres.railway.internal:5432/railway"
    assert "ssl" not in target.connect_args  # private network, no sslmode in the URL


@pytest.mark.req("NFR-09")
def test_sqlite_on_render_is_refused():
    with pytest.raises(DatabaseConfigError, match="not persistent"):
        resolve_database_url("sqlite:///x.db", host="Render")


@pytest.mark.req("NFR-09")
def test_local_default_is_a_sqlite_file():
    target = resolve_database_url("", host=None)
    assert target.is_sqlite and target.url.endswith("/scrapeonce.db")


@pytest.mark.req("NFR-09")
def test_unknown_scheme_is_refused():
    with pytest.raises(DatabaseConfigError, match="Unsupported"):
        resolve_database_url("mysql://u:p@h/db", host=None)


# --- real Postgres (optional) ------------------------------------------------
@pytest.mark.live
@pytest.mark.req("FR-01")
def test_postgres_round_trip():
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith(("postgres://", "postgresql")):
        pytest.skip("set DATABASE_URL to a Postgres database to run this")
    with make_client(url) as first:
        flow_id, version = create_and_save(first)
    try:
        with make_client(url) as second:
            assert second.get(f"/api/flows/{flow_id}").json()["draft"]["version"] == version
    finally:
        with make_client(url) as cleanup:
            cleanup.delete(f"/api/flows/{flow_id}")


# --- startup against a database that isn't there yet (Railway deploy log, 13:40) ------------------------
def _pg(url="postgresql://admin:s3cret-pw@postgres.railway.internal:5432/railway"):
    return Database(resolve_database_url(url, host=None))


@pytest.mark.req("NFR-09")
def test_describe_never_shows_the_password():
    assert _pg().describe() == "Postgres at postgres.railway.internal:5432/railway"


@pytest.mark.req("NFR-09")
async def test_startup_waits_for_a_slow_private_network(monkeypatch):
    db, calls, slept = _pg(), [], []

    async def ping(timeout=3.0):
        calls.append(1)
        if len(calls) < 3:
            raise OSError("[Errno -2] Name or service not known")

    async def sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(db, "ping", ping)
    await db.wait_until_ready(sleep=sleep)
    assert len(calls) == 3 and slept == [1, 2]
    await db.dispose()


@pytest.mark.req("NFR-09")
async def test_unreachable_database_fails_with_one_clear_line(monkeypatch):
    db = _pg()

    async def ping(timeout=3.0):
        raise OSError("[Errno -2] Name or service not known")

    async def sleep(seconds):
        return None

    monkeypatch.setattr(db, "ping", ping)
    with pytest.raises(DatabaseConfigError) as err:
        await db.wait_until_ready(sleep=sleep)
    message = str(err.value)
    assert "postgres.railway.internal:5432" in message and "Name or service not known" in message
    assert "Postgres.DATABASE_URL" in message and "s3cret-pw" not in message
    await db.dispose()
