"""Suite-wide test setup.

1. NO NETWORK. Every test runs with the engine's fetch options replaced by an offline version: any real
   DNS lookup or connection fails the fetch immediately. (Found when the agent's page tools stopped being
   stubs and a test quietly tried to resolve shop.example.com.)
2. `fake_web`: a fixture that serves pages from memory through the REAL safe_fetch (all checks on), by
   faking only DNS and the socket. By default it serves the mock shop's own pages, so selector tests run
   against the real demo markup.
"""

from __future__ import annotations

import httpx
import pytest

from app.engine import api as engine_api
from app.engine.fetcher import FetchOptions, HostThrottle

FAKE_PUBLIC_IP = "93.184.216.34"


async def _offline_resolver(host: str, port: int) -> list[str]:
    raise OSError(f"network disabled in tests (tried to resolve {host})")


def _offline_transport(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError(f"network disabled in tests (tried {request.url})")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def offline() -> FetchOptions:
        return FetchOptions(resolver=_offline_resolver, transport=httpx.MockTransport(_offline_transport),
                            throttle=HostThrottle(0), retries=0)

    monkeypatch.setattr(engine_api, "fetch_options", offline)
    engine_api.clear_page_cache()
    yield
    engine_api.clear_page_cache()


def mock_shop_pages() -> dict[str, tuple[int, str]]:
    """path -> (status, html) for the demo shop, rendered by the real mock shop code."""
    from fastapi.testclient import TestClient

    from app.mockshop.routes import router
    from app.mockshop.state import state

    state.reset()
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    pages = {}
    for path in ["/shop", "/shop?page=2", "/shop?layout=v2", "/shop?mode=blocked", "/shop?mode=js",
                 "/shop?mode=dupes", "/shop/p/blue-kettle", "/shop/p/steel-flask", "/shop/p/tea-set"]:
        r = client.get(path)
        pages[path] = (r.status_code, r.text)
    return pages


@pytest.fixture
def fake_web(monkeypatch):
    """Serve pages at https://shop.example.com/<path> through the real safe_fetch. Returns the page dict,
    which a test may change (pages["/x"] = (200, "<html>...")) before fetching."""
    pages = mock_shop_pages()

    async def resolve(host: str, port: int) -> list[str]:
        if host == "shop.example.com":
            return [FAKE_PUBLIC_IP]
        raise OSError(f"unknown host {host} in fake_web")

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.raw_path.decode()
        status, html = pages.get(path, (404, "<h1>Not found</h1>"))
        return httpx.Response(status, headers={"content-type": "text/html; charset=utf-8"},
                              stream=httpx.ByteStream(html.encode()))

    def options() -> FetchOptions:
        return FetchOptions(resolver=resolve, transport=httpx.MockTransport(handler), throttle=HostThrottle(0),
                            retries=0)

    monkeypatch.setattr(engine_api, "fetch_options", options)
    engine_api.clear_page_cache()
    return pages
