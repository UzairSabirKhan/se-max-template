"""Engine functions the sidebar agent may call (specs/contracts.md C4).

This module is the ONLY door from app/ai into the engine. Nothing in app/engine imports
app/ai (tests/engine/test_zero_ai.py checks this).

Everything here is REAL. dry_run, list_datasets and sample_records need the app's database, which
main.py hands over at startup with `use_database(db)`.
"""

from __future__ import annotations

import time
from typing import Any

from selectolax.lexbor import LexborHTMLParser

from app.db.runs import RunRepo
from app.db.session import Database
from app.engine.fetcher import FetchError, FetchOptions, safe_fetch, settings_options
from app.engine.runner import RunOptions, run_flow
from app.flow.schema import node_type_schemas as _node_type_schemas
from app.flow.validate import parse_flow as _parse_flow
from app.flow.validate import validate_flow as _validate_flow

#: The URL can't be used (internal address, not HTML, too big, unreachable, HTTP error...). `.reason`
#: is a plain-language sentence. Same class as the fetcher's error, under the name the agent tools use.
FetchRefused = FetchError

MAX_OUTLINE_CHARS = 30_000
PAGE_CACHE_S = 60.0
_NOISE = "script, style, noscript, svg, iframe, template, link, meta, object, embed, canvas"

# The assistant often fetches a page and then tests several selectors on it. A short cache means one
# request to the site instead of one per selector (each would also wait for the 2 s politeness gap).
# Runs never use this cache: they always fetch fresh.
_page_cache: dict[str, tuple[float, str]] = {}
_database: Database | None = None


def use_database(db: Database | None) -> None:
    global _database
    _database = db


def _db() -> Database:
    if _database is None:
        raise RuntimeError("engine.api has no database: call use_database(db) at startup")
    return _database


def validate_flow(flow: dict, for_publish: bool = False, draft: bool = False) -> list[dict]:
    """[] if the flow is valid, else contract C2 issues. REAL.

    The agent checks each edit with draft=True (half-built flows are fine, unsafe ones are not)
    and checks the finished flow with draft=False before saying "ready to publish".
    """
    return _validate_flow(flow, for_publish=for_publish, draft=draft)


def parse_flow(flow: dict, for_publish: bool = False, draft: bool = False) -> tuple[dict | None, list[dict]]:
    """(normalised flow, []) if valid, else (None, issues). REAL.

    Store and apply the normalised flow, never the raw input: it is exactly what was validated
    (trimmed, de-duplicated, defaults filled in).
    """
    return _parse_flow(flow, for_publish=for_publish, draft=draft)


def node_type_schemas() -> list[dict]:
    """Same payload as GET /api/node-types. REAL."""
    return _node_type_schemas()


def fetch_options() -> FetchOptions:
    """The allowlist from settings. Tests replace this (fake DNS + MockTransport)."""
    return settings_options()


async def _page_html(url: str) -> str:
    cached = _page_cache.get(url)
    if cached and time.monotonic() - cached[0] < PAGE_CACHE_S:
        return cached[1]
    result = await safe_fetch(url, fetch_options())
    if result.status >= 400:
        raise FetchRefused(f"The page answered with HTTP {result.status}", "refused")
    if len(_page_cache) > 50:
        _page_cache.clear()
    _page_cache[url] = (time.monotonic(), result.text)
    return result.text


def clear_page_cache() -> None:
    _page_cache.clear()


async def fetch_outline(url: str) -> str:
    """The page's HTML through safe_fetch, with scripts, styles and other noise removed, about 30 KB.

    Tags, classes, ids and links are kept: they are what selectors are built from. REAL.
    Raises FetchRefused with a plain-language reason.
    """
    tree = LexborHTMLParser(await _page_html(url))
    for node in tree.css(_NOISE):
        node.decompose()
    root = tree.body or tree.root
    html = root.html if root is not None else ""
    lines = (line.strip() for line in (html or "").splitlines())
    return "\n".join(line for line in lines if line)[:MAX_OUTLINE_CHARS]


async def test_selector(url: str, selector: str, attr: str | None = None) -> dict[str, Any]:
    """How many elements match a CSS selector, and up to 5 sample values (text, or `attr`). REAL."""
    tree = LexborHTMLParser(await _page_html(url))
    try:
        nodes = tree.css(selector)
    except Exception:  # selectolax raises on a selector it can't parse
        return {"count": 0, "samples": [], "error": "Selector does not parse"}
    samples: list[str] = []
    for node in nodes[:5]:
        value = node.attributes.get(attr) if attr else node.text(deep=True, separator=" ", strip=True)
        samples.append(" ".join(str(value or "").split()))
    return {"count": len(nodes), "samples": samples}


async def dry_run(flow: dict, flow_id: str | None, until_node: str | None = None) -> dict[str, Any]:
    """Run the draft for real (fresh fetches) and return its RunReport. Writes no records and no alerts,
    only a run row marked `dry_run`. REAL. (`until_node` is accepted; the whole draft is run.)"""
    if not flow_id:
        raise ValueError("dry_run needs the flow id")
    return await run_flow(flow, flow_id, _db(), RunOptions(trigger="dry_run", fetch=fetch_options()))


async def list_datasets(flow_id: str) -> list[dict[str, Any]]:
    """The flow's datasets: name, identity field, fields, record count. REAL."""
    async with _db().sessions() as session:
        return await RunRepo(session).list_datasets(flow_id)


async def sample_records(dataset_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Read-only sample of stored records (at most 20). REAL."""
    async with _db().sessions() as session:
        return (await RunRepo(session).list_records(dataset_id, max(1, min(limit, 20)), 0))["records"]
