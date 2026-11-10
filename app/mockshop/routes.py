"""The mock shop at /shop (A11; FR-36): the ONLY site ScrapeOnce scrapes during the event.

Pages for each run verdict (design.md "Mock shop pages"), product pages for the link-list flow, an admin
page to change things live during the demo, and robustness pages for the judges' checks.

Query overrides (?layout=v2, ?mode=blocked|js|dupes) give each case its own fixed URL; the admin page
changes the shop's state, so the SAME URL a published flow watches starts showing the change.
"""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.mockshop.state import LAYOUTS, MODES, PER_PAGE, format_price, state

router = APIRouter(prefix="/shop", include_in_schema=False)

_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html"]),
)
_env.globals["price"] = format_price

METADATA_URL = "http://169.254.169.254/latest/meta-data/"
HUGE_BYTES = 2_500_000
SLOW_SECONDS = 60


def _render(name: str, status: int = 200, **ctx) -> HTMLResponse:
    return HTMLResponse(_env.get_template(name).render(**ctx), status_code=status)


def _not_found() -> HTMLResponse:
    return HTMLResponse("<!doctype html><title>Not found</title><h1>Page not found</h1>", status_code=404)


def _choice(value: str | None, allowed: tuple[str, ...], current: str) -> str:
    return value if value in allowed else current


def _jsonld(products, base: str) -> str:
    data = {
        "@context": "https://schema.org", "@type": "ItemList",
        "itemListElement": [
            {"@type": "Product", "name": p.title, "sku": p.sku, "url": f"{base}/shop/p/{p.slug}",
             "offers": {"@type": "Offer", "price": str(p.price), "priceCurrency": "PKR",
                        "availability": "https://schema.org/OutOfStock" if p.stock == "Sold out"
                        else "https://schema.org/InStock"}}
            for p in products
        ],
    }
    # Inside <script>: escape "<" so no value can close the tag early.
    return json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")


@router.get("")
async def shop(request: Request, page: int = 1, layout: str | None = None, mode: str | None = None) -> Response:
    mode = _choice(mode, MODES, state.mode)
    layout = _choice(layout, LAYOUTS, state.layout)
    if mode == "blocked":
        return _render("blocked.html")        # status 200 on purpose: must be BLOCKED, not "all items removed"
    if mode == "js":
        return _render("js_shell.html")       # must be UNSUPPORTED
    products = state.visible()
    if mode == "dupes" and products:
        products = [products[0], *products]   # same SKU and link twice: must be BROKEN (duplicate keys)
    pages = max(1, -(-len(products) // PER_PAGE))
    if page < 1 or page > pages:
        return _not_found()
    shown = products[(page - 1) * PER_PAGE: page * PER_PAGE]
    base = str(request.base_url).rstrip("/")
    return _render("list.html", products=shown, page=page, pages=pages, layout=layout,
                   jsonld=_jsonld(shown, base))


@router.get("/p/{slug}")
async def product(slug: str, layout: str | None = None) -> Response:
    if state.mode == "blocked":
        return _render("blocked.html")
    p = state.find(slug)
    if p is None or slug in state.removed:
        return _not_found()
    return _render("product.html", p=p, layout=_choice(layout, LAYOUTS, state.layout))


# --- admin (demo controls) ---------------------------------------------------------------------------
@router.get("/admin")
async def admin() -> Response:
    return _render("admin.html", state=state, modes=MODES)


async def _form(request: Request) -> dict[str, str]:
    """application/x-www-form-urlencoded without extra dependencies."""
    body = (await request.body())[:10_000].decode("utf-8", errors="replace")
    return {k: v[0] for k, v in parse_qs(body).items()}


def _back() -> RedirectResponse:
    return RedirectResponse("/shop/admin", status_code=303)


@router.post("/admin/price")
async def set_price(request: Request) -> Response:
    form = await _form(request)
    p = state.find(form.get("slug", ""))
    try:
        price = Decimal(form.get("price", "").replace(",", "").strip())
    except InvalidOperation:
        price = Decimal(-1)
    if p is not None and Decimal(0) < price < Decimal(10_000_000):
        p.price = price.quantize(Decimal("0.01")) if price != int(price) else Decimal(int(price))
    return _back()


@router.post("/admin/remove")
async def remove(request: Request) -> Response:
    slug = (await _form(request)).get("slug", "")
    if state.find(slug):
        state.removed.add(slug)
    return _back()


@router.post("/admin/restore")
async def restore(request: Request) -> Response:
    state.removed.discard((await _form(request)).get("slug", ""))
    return _back()


@router.post("/admin/layout")
async def set_layout(request: Request) -> Response:
    state.layout = _choice((await _form(request)).get("layout"), LAYOUTS, state.layout)
    return _back()


@router.post("/admin/mode")
async def set_mode(request: Request) -> Response:
    state.mode = _choice((await _form(request)).get("mode"), MODES, state.mode)
    return _back()


@router.post("/admin/reset")
async def reset() -> Response:
    state.reset()
    return _back()


# --- robustness pages for the judges' check 5 --------------------------------------------------------
@router.get("/huge")
async def huge() -> Response:
    row = "<div class=\"product\"><h2>Filler</h2><span class=\"price\">Rs 1</span></div>\n"

    def body():
        yield b"<!doctype html><html><body><div id=\"product-grid\">"
        sent = 0
        while sent < HUGE_BYTES:
            chunk = (row * 200).encode()
            sent += len(chunk)
            yield chunk
        yield b"</div></body></html>"

    return StreamingResponse(body(), media_type="text/html")


@router.get("/slow")
async def slow() -> Response:
    async def drip():
        yield b"<!doctype html><html><body>"
        for _ in range(SLOW_SECONDS):
            await asyncio.sleep(1)
            yield b"."
        yield b"</body></html>"

    return StreamingResponse(drip(), media_type="text/html")


@router.get("/file.pdf")
async def pdf() -> Response:
    return Response(b"%PDF-1.4\n% ScrapeOnce demo file, not a web page\n%%EOF\n", media_type="application/pdf")


@router.get("/redirect-internal")
async def redirect_internal() -> Response:
    return RedirectResponse(METADATA_URL, status_code=302)
