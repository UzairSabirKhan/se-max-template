"""Routes for the extra demo sites at /demo (property listings, scholarships, jobs) and their controls.

Same rules as the mock shop: invented data, our own app, a 404 for unknown paths (never the React app).
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.mockshop.demo_sites import PER_PAGE, crore, demo_state, pkr

router = APIRouter(prefix="/demo", include_in_schema=False)

_env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"), autoescape=select_autoescape(["html"]))
_env.globals.update(pkr=pkr, crore=crore)

SITES = {
    "index": ("ScrapeOnce demo sites", "#3b2f63"),
    "property": ("Ghar Listings", "#0b6b3a"),
    "scholarships": ("Scholar Board", "#1d4ed8"),
    "jobs": ("Kaam Jobs", "#9a3412"),
    "admin": ("Demo controls", "#3b2f63"),
}


def _page(kind: str, site_key: str, status: int = 200, **ctx) -> HTMLResponse:
    site, color = SITES[site_key]
    html = _env.get_template("demo_pages.html").render(page_kind=kind, site=site, color=color, **ctx)
    return HTMLResponse(html, status_code=status)


def _not_found() -> HTMLResponse:
    return HTMLResponse("<!doctype html><title>Not found</title><h1>Page not found</h1>", status_code=404)


@router.get("")
async def index() -> Response:
    return _page("index", "index")


@router.get("/property")
async def property_list(page: int = 1) -> Response:
    items = demo_state.listings
    pages = max(1, -(-len(items) // PER_PAGE))
    if page < 1 or page > pages:
        return _not_found()
    return _page("property", "property", items=items[(page - 1) * PER_PAGE: page * PER_PAGE], page=page, pages=pages)


@router.get("/property/{slug}")
async def property_detail(slug: str) -> Response:
    x = next((x for x in demo_state.listings if x.slug == slug), None)
    return _page("property_detail", "property", x=x) if x else _not_found()


@router.get("/scholarships")
async def scholarships() -> Response:
    return _page("scholarships", "scholarships", items=demo_state.scholarships)


@router.get("/scholarships/{slug}")
async def scholarship_detail(slug: str) -> Response:
    s = next((s for s in demo_state.scholarships if s.slug == slug), None)
    return _page("scholarship_detail", "scholarships", s=s) if s else _not_found()


@router.get("/jobs")
async def jobs() -> Response:
    return _page("jobs", "jobs", items=demo_state.jobs)


@router.get("/jobs/{slug}")
async def job_detail(slug: str) -> Response:
    j = next((j for j in demo_state.jobs if j.slug == slug), None)
    return _page("job_detail", "jobs", j=j) if j else _not_found()


# --- demo controls --------------------------------------------------------------------------------------
@router.get("/admin")
async def admin() -> Response:
    return _page("admin", "admin", state=demo_state)


async def _form(request: Request) -> dict[str, str]:
    body = (await request.body())[:10_000].decode("utf-8", errors="replace")
    return {k: v[0] for k, v in parse_qs(body).items()}


def _back() -> RedirectResponse:
    return RedirectResponse("/demo/admin", status_code=303)


@router.post("/admin/property-drop")
async def property_drop(request: Request) -> Response:
    demo_state.drop_price((await _form(request)).get("slug", ""))
    return _back()


@router.post("/admin/scholarship-add")
async def scholarship_add() -> Response:
    demo_state.add_scholarship()
    return _back()


@router.post("/admin/job-add")
async def job_add() -> Response:
    demo_state.add_job()
    return _back()


@router.post("/admin/reset")
async def reset() -> Response:
    demo_state.reset()
    return _back()


@router.api_route("/{rest:path}", methods=["GET", "POST"])
async def demo_not_found(rest: str) -> Response:  # must stay last
    return _not_found()
