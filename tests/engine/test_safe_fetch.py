"""safe_fetch (A9; FR-18, FR-19, FR-26, NFR-01). Edge cases EC-01 – EC-14 in docs/testing.md.

No real network: DNS is a fake resolver and HTTP is httpx.MockTransport. We never probe real
internal addresses.
"""

import asyncio
import gzip

import httpx
import pytest

from app.engine.fetcher import FetchError, FetchOptions, HostThrottle, safe_fetch

PUBLIC_IP = "93.184.216.34"
HTML = "text/html; charset=utf-8"


def resp(status: int, headers: dict | None = None, body: bytes = b"") -> httpx.Response:
    """A response the way the network delivers it: as a stream, not pre-read (like a real server)."""
    return httpx.Response(status, headers=headers or {}, stream=httpx.ByteStream(body))


def fake_dns(table: dict[str, list[str]] | None = None):
    table = table or {}

    async def resolve(host: str, port: int) -> list[str]:
        if host in table:
            return table[host]
        return [PUBLIC_IP]
    return resolve


def options(handler, dns=None, **kw) -> tuple[FetchOptions, list[float]]:
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    opts = FetchOptions(resolver=fake_dns(dns), transport=httpx.MockTransport(handler),
                        throttle=HostThrottle(0), sleep=sleep, **kw)
    return opts, slept


def page(body: str = "<html><body><h1>Shop</h1></body></html>", status: int = 200, **headers):
    def handler(request: httpx.Request) -> httpx.Response:
        return resp(status, {"content-type": HTML, **headers}, body.encode())
    return handler


def never_called(request):  # the request must be refused before any connection
    raise AssertionError(f"connected to {request.url}")


# --- EC-01 – EC-04, EC-08: internal addresses and schemes are refused before connecting -------------
@pytest.mark.req("FR-18")
@pytest.mark.parametrize("url", [
    "http://127.0.0.1/", "http://127.1/", "http://2130706433/", "http://0x7f.1/", "http://017700000001/",
    "http://0.0.0.0/", "http://10.0.0.1/", "http://172.16.0.1/", "http://192.168.1.1/", "http://100.64.0.1/",
    "http://169.254.169.254/latest/meta-data/", "http://[::1]/", "http://[::ffff:127.0.0.1]/",
    "http://[fc00::1]/", "http://[fe80::1]/", "http://localhost:8000/", "http://metadata.google.internal/",
    "http://printer.local/", "http://shop.localhost/",
])
async def test_refuses_internal(url):
    opts, _ = options(never_called)
    with pytest.raises(FetchError) as err:
        await safe_fetch(url, opts)
    assert err.value.kind == "internal"


@pytest.mark.req("FR-18")
@pytest.mark.parametrize("url", ["file:///etc/passwd", "gopher://example.com/", "ftp://example.com/",
                                 "javascript:alert(1)", "data:text/html,hi", "//example.com/x", "not a url",
                                 "http://user:pw@example.com/"])
async def test_scheme(url):
    opts, _ = options(never_called)
    with pytest.raises(FetchError) as err:
        await safe_fetch(url, opts)
    assert err.value.kind == "refused"


# --- EC-05, EC-06: DNS and redirects are checked too --------------------------------------------------
@pytest.mark.req("FR-18")
@pytest.mark.parametrize("answers", [["10.0.0.5"], [PUBLIC_IP, "127.0.0.1"], ["::1"], ["169.254.169.254"]])
async def test_dns_to_private(answers):
    opts, _ = options(never_called, dns={"evil.example.com": answers})
    with pytest.raises(FetchError, match="private or internal") as err:
        await safe_fetch("https://evil.example.com/", opts)
    assert err.value.kind == "internal"


@pytest.mark.req("FR-18")
async def test_redirect_to_internal():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})

    opts, _ = options(handler)
    with pytest.raises(FetchError) as err:
        await safe_fetch("https://shop.example.com/", opts)
    assert err.value.kind == "internal"
    assert len(seen) == 1  # the internal address itself was never requested


@pytest.mark.req("FR-18")
async def test_redirect_limit():
    def handler(request):
        return httpx.Response(302, headers={"location": "/again"})

    opts, _ = options(handler)
    with pytest.raises(FetchError, match="Too many redirects"):
        await safe_fetch("https://shop.example.com/", opts)


@pytest.mark.req("FR-18")
async def test_redirect_within_limit_is_followed_and_recorded():
    def handler(request):
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "/new"})
        return resp(200, {"content-type": HTML}, b"<p>new</p>")

    opts, _ = options(handler)
    result = await safe_fetch("https://shop.example.com/old", opts)
    assert result.status == 200 and result.final_url == "https://shop.example.com/new"
    assert result.redirects == ["https://shop.example.com/new"]


# --- Connection is pinned to the IP that was checked (DNS rebinding) ------------------------------
@pytest.mark.req("FR-18")
async def test_connects_to_the_checked_ip_with_the_real_host_name():
    seen = {}

    def handler(request):
        seen.update(url=str(request.url), host=request.headers["host"], sni=request.extensions.get("sni_hostname"),
                    ua=request.headers["user-agent"])
        return resp(200, {"content-type": HTML}, b"ok")

    opts, _ = options(handler, dns={"shop.example.com": ["93.184.216.99"]})
    await safe_fetch("https://shop.example.com/products?page=2", opts)
    assert seen["url"] == "https://93.184.216.99/products?page=2"
    assert seen["host"] == "shop.example.com" and seen["sni"] == "shop.example.com"
    assert seen["ua"].startswith("ScrapeOnceBot/")




# --- EC-10 – EC-14: size, compression, slowness, content type, statuses ------------------------------
@pytest.mark.req("FR-18")
async def test_size_cap():
    opts, _ = options(page("<p>" + "x" * 2_100_000 + "</p>"))
    with pytest.raises(FetchError, match="larger than 2 MB"):
        await safe_fetch("https://shop.example.com/huge", opts)


@pytest.mark.req("FR-18")
async def test_gzip_bomb():
    bomb = gzip.compress(b"\0" * 50_000_000)  # about 50 KB on the wire, 50 MB unpacked

    def handler(request):
        return resp(200, {"content-type": HTML, "content-encoding": "gzip"}, bomb)

    opts, _ = options(handler)
    with pytest.raises(FetchError) as err:
        await safe_fetch("https://shop.example.com/bomb", opts)
    assert err.value.kind == "too_large"


@pytest.mark.req("FR-18")
async def test_gzip_page_is_decompressed():
    def handler(request):
        return resp(200, {"content-type": HTML, "content-encoding": "gzip"},
                    gzip.compress("<h1>Kettle ₨ 1,250</h1>".encode()))

    opts, _ = options(handler)
    assert (await safe_fetch("https://shop.example.com/", opts)).text == "<h1>Kettle ₨ 1,250</h1>"


@pytest.mark.req("FR-18")
async def test_broken_compression_is_a_clear_error():
    def handler(request):
        return resp(200, {"content-type": HTML, "content-encoding": "gzip"}, b"not gzip")

    opts, _ = options(handler)
    with pytest.raises(FetchError, match="compressed data is broken"):
        await safe_fetch("https://shop.example.com/", opts)


class SlowDrip(httpx.AsyncByteStream):
    async def __aiter__(self):
        for _ in range(100):
            await asyncio.sleep(0.05)
            yield b"x"


@pytest.mark.req("FR-26")
async def test_slow_drip():
    def handler(request):
        return httpx.Response(200, headers={"content-type": HTML}, stream=SlowDrip())

    opts, slept = options(handler, total_timeout=0.3, retries=1)
    with pytest.raises(FetchError) as err:
        await safe_fetch("https://shop.example.com/slow", opts)
    assert err.value.kind == "timeout" and slept == [2.0]  # one retry after the 2 s backoff


@pytest.mark.req("FR-18")
@pytest.mark.parametrize("ctype", ["application/pdf", "application/json", "image/png", ""])
async def test_content_type(ctype):
    def handler(request):
        return resp(200, {"content-type": ctype} if ctype else {}, b"%PDF")

    opts, _ = options(handler)
    with pytest.raises(FetchError) as err:
        await safe_fetch("https://shop.example.com/file", opts)
    assert err.value.kind == "not_html"


@pytest.mark.req("FR-26")
async def test_status_handling():
    opts, slept = options(page("<h1>Not found</h1>", status=404))
    result = await safe_fetch("https://shop.example.com/missing", opts)
    assert result.status == 404 and slept == []  # returned, not retried, not raised

    calls = []

    def flaky(request):
        calls.append(1)
        if len(calls) < 3:
            return resp(503, {"content-type": HTML}, b"busy")
        return resp(200, {"content-type": HTML}, b"<p>ok</p>")

    opts, slept = options(flaky)
    assert (await safe_fetch("https://shop.example.com/", opts)).status == 200
    assert slept == [2.0, 4.0]

    opts, slept = options(page("slow down", status=429, **{"retry-after": "30"}))
    assert (await safe_fetch("https://shop.example.com/", opts)).status == 429  # after 2 retries
    assert slept == [10.0, 10.0]  # Retry-After honoured, capped at 10 s


@pytest.mark.req("FR-26")
async def test_same_host_is_throttled():
    now = [100.0]
    waits: list[float] = []

    async def sleep(seconds):
        waits.append(seconds)
        now[0] += seconds

    throttle = HostThrottle(2.0, sleep=sleep, clock=lambda: now[0])
    await throttle.wait("shop.example.com")
    now[0] += 0.5
    await throttle.wait("shop.example.com")
    await throttle.wait("other.example.com")
    assert waits == [1.5]


@pytest.mark.req("FR-18")
async def test_charset_from_header_is_used():
    def handler(request):
        return resp(200, {"content-type": "text/html; charset=windows-1252"}, "Café".encode("windows-1252"))

    opts, _ = options(handler)
    assert (await safe_fetch("https://shop.example.com/", opts)).text == "Café"


@pytest.mark.req("FR-18")
async def test_internal_addresses_are_refused_even_without_an_allowlist():
    opts, _ = options(never_called)
    with pytest.raises(FetchError) as err:
        await safe_fetch("http://169.254.169.254/latest/meta-data/", opts)
    assert err.value.kind == "internal"


@pytest.mark.req("FR-19")
async def test_any_public_website_can_be_fetched_and_allowed_domains_is_ignored(monkeypatch):
    """There is no allowlist: a leftover ALLOWED_DOMAINS on a host (Railway) must not block any site."""
    from app.engine.fetcher import settings_options

    monkeypatch.setenv("ALLOWED_DOMAINS", "your-app.up.railway.app")
    assert not hasattr(settings_options(), "allowed_domains")
    opts, _ = options(page())
    for url in ("https://scrapeonce-production-839d.up.railway.app/shop", "https://any-store.example.org/products"):
        assert (await safe_fetch(url, opts)).status == 200
