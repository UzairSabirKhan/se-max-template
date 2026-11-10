"""ScrapeOnce: one FastAPI service (docs/adr 0004).

Serves /health, the JSON API under /api, the mock shop under /shop (A11), and the React
build from web/dist with a fallback to index.html for client-side routes. Run with ONE
worker so the in-process scheduler never fires twice:

    uv run uvicorn app.main:app --workers 1
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from app.api.agent import router as agent_router
from app.api.errors import ApiError, install_error_handlers
from app.api.limits import BodySizeLimit
from app.api.routes import router as api_router
from app.db.session import Database, resolve_database_url
from app.engine import api as engine_api
from app.engine.service import runs
from app.mockshop.routes import router as shop_router
from app.scheduler import FlowScheduler
from app.settings import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("scrapeonce")

PLACEHOLDER = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>ScrapeOnce</title></head>
<body style="font-family:system-ui;margin:3rem"><h1>ScrapeOnce</h1>
<p>The API is running. The editor appears here once <code>web/dist</code> is built.</p>
<p><a href="/health">/health</a> · <a href="/api/node-types">/api/node-types</a></p></body></html>"""


def create_app(database_url: str | None = None) -> FastAPI:
    """database_url overrides DATABASE_URL (tests pass a temporary SQLite file)."""
    target = resolve_database_url(database_url if database_url is not None else settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = Database(target)
        log.info("Connecting to the database (%s)", db.describe())
        await db.wait_until_ready()
        await db.create_tables()
        app.state.db = db
        engine_api.use_database(db)
        log.info("Database ready (%s)", "SQLite" if target.is_sqlite else "Postgres")
        scheduler = FlowScheduler(db, runs, engine_api.fetch_options)
        await scheduler.start()  # rebuilds every published flow's schedule from the database
        app.state.scheduler = scheduler
        try:
            yield
        finally:
            scheduler.shutdown()
            await runs.wait_idle()
            engine_api.use_database(None)
            await db.dispose()

    app = FastAPI(title="ScrapeOnce", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json",
                  lifespan=lifespan)
    install_error_handlers(app)
    app.add_middleware(BodySizeLimit, max_bytes=settings.max_request_bytes)

    @app.get("/health")
    async def health() -> JSONResponse:
        # Also touches the database: the keep-alive ping then keeps Neon awake too, and a broken
        # database shows up as 503 instead of as failing saves.
        try:
            await app.state.db.ping()
        except Exception:
            log.exception("Health check: database unreachable")
            return JSONResponse({"status": "degraded", "database": "unreachable"}, status_code=503)
        return JSONResponse({"status": "ok", "database": "ok"})

    app.include_router(api_router)
    app.include_router(agent_router)  # Workstream B: POST /api/flows/{id}/agent
    app.include_router(shop_router)  # /shop: the demo shop (the only site scraped during the event)

    @app.api_route("/api", methods=["GET", "POST", "PUT", "DELETE", "PATCH"], include_in_schema=False)
    @app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
                   include_in_schema=False)
    def api_not_found(rest: str = "") -> None:
        raise ApiError(404, "not_found", f"No API route /api/{rest}")

    # ORDER MATTERS: register every other route (e.g. the /shop mock shop, A11) ABOVE this line.
    # The frontend catch-all answers any remaining GET with the React app.
    _mount_frontend(app, settings.web_dist)
    return app


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    dist = dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        index = dist / "index.html"
        if path:
            candidate = (dist / path).resolve()
            if candidate.is_file() and candidate.is_relative_to(dist):
                return FileResponse(candidate)
        if index.is_file():
            return FileResponse(index)  # client-side route: let React handle it
        return HTMLResponse(PLACEHOLDER)


app = create_app()
