"""safe_fetch: the ONLY way ScrapeOnce reads a web page (FR-18, FR-19, FR-26; design.md "Threat model").

Every request, from a run or from the assistant, goes through here:

1. http / https only; no user:password in the URL. Any public website may be fetched.
2. The host is resolved and EVERY address must be public. IP literals in any spelling (127.1, 0x7f.1,
   2130706433, octal, IPv4-mapped IPv6) are decoded first, so tricks don't pass as hostnames.
3. The connection goes to the exact IP that was checked (TLS still verifies the real hostname via SNI),
   so the name can't be re-pointed at an internal address between check and connect (DNS rebinding).
4. Redirects are followed by hand, at most 3, and each new URL is checked again from step 1.
5. Limits: 5 s to connect, 15 s for the whole request; 2 MB of body AFTER decompression (we decompress
   ourselves, chunk by chunk, so a gzip bomb stops at 2 MB); HTML content types only.
6. Polite: honest User-Agent, at least 2 s between requests to the same host, 2 retries with backoff on
   429 / 5xx / timeouts (Retry-After honoured up to 10 s).

HTTP error statuses (404, 500, ...) are RETURNED, not raised: the run classifier decides what they mean.
Anything that makes the URL unusable raises FetchError with a plain-language reason.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
import zlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

USER_AGENT = "ScrapeOnceBot/0.1 (+https://github.com/muhammadusamahoyrr/ScrapeOne)"
MAX_BYTES = 2_000_000
CONNECT_TIMEOUT_S = 5.0
TOTAL_TIMEOUT_S = 15.0
MAX_REDIRECTS = 3
RETRIES = 2
BACKOFF_S = (2.0, 4.0)
MAX_RETRY_AFTER_S = 10.0
MIN_INTERVAL_S = 2.0
HTML_TYPES = ("text/html", "application/xhtml+xml")
RETRY_STATUSES = {429, 500, 502, 503, 504}

ErrorKind = Literal["refused", "internal", "not_html", "too_large", "timeout", "network",
                    "redirects"]


class FetchError(Exception):
    """The URL can't be used. `reason` is shown to the user (and to the assistant)."""

    def __init__(self, reason: str, kind: ErrorKind = "refused") -> None:
        super().__init__(reason)
        self.reason = reason
        self.kind = kind


@dataclass(frozen=True)
class FetchResult:
    url: str                # what was asked for
    final_url: str          # after redirects
    status: int
    content_type: str
    text: str
    body_size: int          # decompressed bytes
    elapsed_ms: int
    redirects: list[str] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)


Resolver = Callable[[str, int], Awaitable[list[str]]]
Sleep = Callable[[float], Awaitable[None]]


async def system_resolver(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({info[4][0] for info in infos})


# ---------------------------------------------------------------------------
# Address checks
# ---------------------------------------------------------------------------
def literal_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """The IP a host string stands for, in ANY spelling, or None if it's a name."""
    host = host.strip("[]")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        try:  # legacy IPv4 forms: 127.1, 0x7f.1, 2130706433, 017700000001
            ip = ipaddress.IPv4Address(socket.inet_aton(host))
        except (OSError, ValueError):
            return None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip


def is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


@dataclass(frozen=True)
class _Target:
    url: str
    scheme: str
    host: str
    port: int
    ip: str


async def check_url(url: str, resolver: Resolver) -> _Target:
    """Validate a URL and pick the checked IP to connect to. Raises FetchError."""
    if not isinstance(url, str) or any(ch.isspace() or ord(ch) < 32 for ch in url):
        raise FetchError("That isn't a valid URL", "refused")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise FetchError("That isn't a valid URL", "refused") from None
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise FetchError("Only http and https URLs are allowed", "refused")
    if parts.username or parts.password:
        raise FetchError("URLs with a username or password are not allowed", "refused")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise FetchError("The URL has no host", "refused")
    port = port or (443 if scheme == "https" else 80)

    ip = literal_ip(host)
    if ip is not None:
        addresses = [str(ip)]
    else:
        if host == "localhost" or host.endswith((".localhost", ".internal", ".local")):
            raise FetchError(f"{host} is an internal address", "internal")
        try:
            addresses = await resolver(host, port)
        except OSError:
            raise FetchError(f"Couldn't find the site {host}", "network") from None
        if not addresses:
            raise FetchError(f"Couldn't find the site {host}", "network")

    for address in addresses:
        resolved = literal_ip(address)
        if resolved is None or not is_public(resolved):
            raise FetchError(f"{host} points to a private or internal address", "internal")
    return _Target(url=url, scheme=scheme, host=host, port=port, ip=addresses[0])


def _pinned_request(target: _Target, client: httpx.AsyncClient) -> httpx.Request:
    """A request to the checked IP, with the real Host header and TLS name."""
    parts = urlsplit(target.url)
    ip = target.ip if ":" not in target.ip else f"[{target.ip}]"
    default = 443 if target.scheme == "https" else 80
    netloc = ip if target.port == default else f"{ip}:{target.port}"
    pinned = urlunsplit((target.scheme, netloc, parts.path or "/", parts.query, ""))
    host_header = target.host if target.port == default else f"{target.host}:{target.port}"
    extensions = {"sni_hostname": target.host} if target.scheme == "https" else {}
    return client.build_request(
        "GET", pinned,
        headers={"Host": host_header, "User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml",
                 "Accept-Encoding": "gzip, deflate"},
        extensions=extensions,
    )


# ---------------------------------------------------------------------------
# Body reading with a decompressed-size cap
# ---------------------------------------------------------------------------
class _Decoder:
    def __init__(self, encoding: str) -> None:
        encoding = encoding.strip().lower()
        if encoding in ("", "identity"):
            self._z = None
        elif encoding in ("gzip", "x-gzip"):
            self._z = zlib.decompressobj(16 + zlib.MAX_WBITS)
        elif encoding == "deflate":
            self._z = zlib.decompressobj()
        else:
            raise FetchError(f"The page uses an unsupported compression ({encoding})", "refused")

    def feed(self, chunk: bytes, room: int) -> bytes:
        """Decompress at most `room + 1` bytes: one more than allowed is enough to know it's too big."""
        if self._z is None:
            return chunk[: room + 1]
        out = self._z.decompress(chunk, room + 1)
        return out


async def _read_capped(response: httpx.Response, max_bytes: int) -> bytes:
    decoder = _Decoder(response.headers.get("content-encoding", ""))
    body = bytearray()
    raw_total = 0
    async for chunk in response.aiter_raw():
        raw_total += len(chunk)
        if raw_total > max_bytes:
            raise FetchError("The page is larger than 2 MB", "too_large")
        try:
            body += decoder.feed(chunk, max_bytes - len(body))
        except zlib.error:
            raise FetchError("The page's compressed data is broken", "refused") from None
        if len(body) > max_bytes:
            raise FetchError("The page is larger than 2 MB", "too_large")
    return bytes(body)


def _charset(content_type: str) -> str:
    for part in content_type.split(";")[1:]:
        key, _, value = part.strip().partition("=")
        if key.lower() == "charset" and value:
            return value.strip("\"' ")
    return "utf-8"


def _decode(body: bytes, content_type: str) -> str:
    try:
        return body.decode(_charset(content_type), errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Politeness: at most one request per host every MIN_INTERVAL_S
# ---------------------------------------------------------------------------
class HostThrottle:
    def __init__(self, min_interval: float = MIN_INTERVAL_S, sleep: Sleep = asyncio.sleep,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.min_interval = min_interval
        self._sleep = sleep
        self._clock = clock
        self._last: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def wait(self, host: str) -> None:
        if self.min_interval <= 0:
            return
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            last = self._last.get(host)
            if last is not None:
                delay = self.min_interval - (self._clock() - last)
                if delay > 0:
                    await self._sleep(delay)
            self._last[host] = self._clock()


default_throttle = HostThrottle()


# ---------------------------------------------------------------------------
# safe_fetch
# ---------------------------------------------------------------------------
@dataclass
class FetchOptions:
    resolver: Resolver = system_resolver
    transport: httpx.AsyncBaseTransport | None = None  # tests pass httpx.MockTransport
    throttle: HostThrottle = field(default_factory=lambda: default_throttle)
    sleep: Sleep = asyncio.sleep
    max_bytes: int = MAX_BYTES
    total_timeout: float = TOTAL_TIMEOUT_S
    retries: int = RETRIES


def _backoff(attempt: int) -> float:
    return BACKOFF_S[min(attempt, len(BACKOFF_S) - 1)]


def _retry_after(headers: dict[str, str], attempt: int) -> float:
    """Seconds to wait before retrying: the server's Retry-After (capped at 10 s), else our backoff."""
    header = headers.get("retry-after", "").strip()
    if header.isdigit():
        return min(float(header), MAX_RETRY_AFTER_S)
    return _backoff(attempt)


async def _fetch_once(url: str, opts: FetchOptions, client: httpx.AsyncClient) -> FetchResult:
    started = time.monotonic()
    redirects: list[str] = []
    current = url
    while True:
        target = await check_url(current, opts.resolver)
        await opts.throttle.wait(target.host)
        request = _pinned_request(target, client)
        response = await client.send(request, stream=True)
        try:
            if response.is_redirect:
                location = response.headers.get("location", "")
                if len(redirects) >= MAX_REDIRECTS:
                    raise FetchError(f"Too many redirects (more than {MAX_REDIRECTS})", "redirects")
                if not location:
                    raise FetchError("The page redirects without saying where", "redirects")
                current = urljoin(current, location)
                redirects.append(current)
                continue
            content_type = response.headers.get("content-type", "").lower()
            mime = content_type.split(";")[0].strip()
            if response.status_code < 400 and mime not in HTML_TYPES:
                raise FetchError(f"Not an HTML page ({mime or 'unknown type'})", "not_html")
            length = response.headers.get("content-length", "")
            if length.isdigit() and int(length) > opts.max_bytes:
                raise FetchError("The page is larger than 2 MB", "too_large")
            body = await _read_capped(response, opts.max_bytes)
            return FetchResult(
                url=url, final_url=current, status=response.status_code, content_type=content_type,
                text=_decode(body, content_type), body_size=len(body),
                elapsed_ms=int((time.monotonic() - started) * 1000), redirects=redirects,
                headers={k.lower(): v for k, v in response.headers.items()},
            )
        finally:
            await response.aclose()


async def safe_fetch(url: str, options: FetchOptions | None = None) -> FetchResult:
    """Fetch one page safely. Returns any HTTP status; raises FetchError when the URL can't be used."""
    opts = options or FetchOptions()
    timeout = httpx.Timeout(opts.total_timeout, connect=CONNECT_TIMEOUT_S)
    async with httpx.AsyncClient(transport=opts.transport, timeout=timeout, follow_redirects=False,
                                 trust_env=False) as client:
        attempt = 0
        while True:
            # FetchError (refused URL, too large, not HTML...) is NOT retried: it propagates at once.
            try:
                result = await asyncio.wait_for(_fetch_once(url, opts, client), timeout=opts.total_timeout)
            except (TimeoutError, httpx.TimeoutException):
                if attempt >= opts.retries:
                    raise FetchError(f"The site took longer than {int(opts.total_timeout)} s to answer",
                                     "timeout") from None
                retry_in = _backoff(attempt)
            except httpx.HTTPError:
                if attempt >= opts.retries:
                    raise FetchError("Couldn't connect to the site", "network") from None
                retry_in = _backoff(attempt)
            else:
                if result.status not in RETRY_STATUSES or attempt >= opts.retries:
                    return result  # error statuses are returned; the classifier decides what they mean
                retry_in = _retry_after(result.headers, attempt)
            attempt += 1
            await opts.sleep(retry_in)


def settings_options() -> FetchOptions:
    """FetchOptions for real fetches. Any public website can be tracked; there is no allowlist.

    What keeps the server safe applies to every URL: private / internal / metadata addresses refused
    (after DNS and on every redirect), http(s) only, 2 MB, timeouts, HTML only.
    """
    return FetchOptions()
