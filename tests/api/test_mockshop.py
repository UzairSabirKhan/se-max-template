"""The mock shop (A11; FR-36) and the agent's real page functions on it (A20 part: fetch_outline, test_selector).

The key check: the selectors in contracts/examples/*.json really work on the demo shop, and the shop's
"broken" pages really are broken in the way each run verdict expects.
"""

import pytest
from fastapi.testclient import TestClient

from app.engine import api as engine
from app.flow.cases import load_example
from app.main import create_app
from app.mockshop.state import state

SHOP = "https://shop.example.com"


@pytest.fixture
def client(tmp_path):
    state.reset()
    app = create_app(database_url=f"sqlite+aiosqlite:///{(tmp_path / 'shop.db').as_posix()}")
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    state.reset()


# --- pages and admin ---------------------------------------------------------------------------------
@pytest.mark.req("FR-36")
def test_shop_pages_exist_and_paginate(client):
    first, second = client.get("/shop"), client.get("/shop?page=2")
    assert first.status_code == second.status_code == 200
    assert first.text.count('class="product"') == 6 and second.text.count('class="product"') == 6
    assert 'class="next"' in first.text and 'class="next"' not in second.text
    assert client.get("/shop?page=3").status_code == 404
    assert "application/ld+json" in first.text  # structured data, like real stores


@pytest.mark.req("FR-36")
def test_admin_changes_the_same_url_a_flow_watches(client):
    client.post("/shop/admin/price", data={"slug": "blue-kettle", "price": "1099"})
    assert "Rs 1,099" in client.get("/shop").text
    client.post("/shop/admin/layout", data={"layout": "v2"})
    assert 'class="price"' not in client.get("/shop").text and 'class="amount"' in client.get("/shop").text
    client.post("/shop/admin/remove", data={"slug": "steel-flask"})
    assert "Steel Flask" not in client.get("/shop").text + client.get("/shop?page=2").text
    assert client.get("/shop/p/steel-flask").status_code == 404
    client.post("/shop/admin/reset")
    assert 'class="price"' in client.get("/shop").text and "Rs 1,250" in client.get("/shop").text


@pytest.mark.req("FR-36")
@pytest.mark.parametrize("bad", ["abc", "-5", "0", "99999999999"])
def test_admin_ignores_bad_prices(client, bad):
    client.post("/shop/admin/price", data={"slug": "blue-kettle", "price": bad})
    assert "Rs 1,250" in client.get("/shop").text


@pytest.mark.req("FR-36")
def test_failure_pages(client):
    blocked = client.get("/shop?mode=blocked")
    assert blocked.status_code == 200 and "Verify you are human" in blocked.text  # 200 on purpose
    shell = client.get("/shop?mode=js")
    assert '<div id="root"></div>' in shell.text and 'class="product"' not in shell.text
    assert client.get("/shop?mode=dupes").text.count('data-sku="KT-100"') == 2
    assert client.get("/shop/file.pdf").headers["content-type"] == "application/pdf"
    redirect = client.get("/shop/redirect-internal", follow_redirects=False)
    assert redirect.status_code == 302 and redirect.headers["location"].startswith("http://169.254.169.254")


@pytest.mark.req("FR-36")
def test_huge_page_is_over_two_megabytes(client):
    assert len(client.get("/shop/huge").content) > 2_000_000


@pytest.mark.req("FR-36")
def test_text_is_escaped_in_shop_pages(client):
    client.post("/shop/admin/price", data={"slug": "blue-kettle", "price": "1099"})
    state.find("blue-kettle").title = '<script>alert(1)</script>Kettle'
    html = client.get("/shop").text
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
    assert "\\u003cscript>" in html  # JSON-LD can't close its own <script> tag either


# --- the example flows' selectors work on the shop ---------------------------------------------------
def _selectors(example: str) -> list[str]:
    flow = load_example(example)
    out = []
    for node in flow["nodes"]:
        config = node.get("config", {})
        for key in ("base_selector", "page_anchor", "next_selector"):
            if config.get(key):
                out.append(config[key])
        out += [f["selector"] for f in config.get("fields", [])]
    return out


@pytest.mark.req("FR-36")
@pytest.mark.parametrize("selector", _selectors("list_tracking"))
async def test_list_tracking_selectors_match_the_shop(fake_web, selector):
    result = await engine.test_selector(f"{SHOP}/shop", selector)
    assert result["count"] >= 1, f"{selector} matches nothing on /shop"


@pytest.mark.req("FR-36")
@pytest.mark.parametrize("selector", _selectors("multi_link"))
async def test_multi_link_selectors_match_product_pages(fake_web, selector):
    result = await engine.test_selector(f"{SHOP}/shop/p/blue-kettle", selector)
    assert result["count"] == 1, f"{selector} should match exactly once on a product page"


# --- the real agent page functions ---------------------------------------------------------------------
@pytest.mark.req("FR-12")
async def test_test_selector_counts_and_samples(fake_web):
    prices = await engine.test_selector(f"{SHOP}/shop", ".price")
    assert prices == {"count": 6, "samples": ["Rs 1,250", "Rs 2,400", "Rs 3,999", "Rs 850", "Rs 6,499"]}
    links = await engine.test_selector(f"{SHOP}/shop", "div.product a", attr="href")
    assert links["samples"][0] == "/shop/p/blue-kettle"
    assert (await engine.test_selector(f"{SHOP}/shop?layout=v2", ".price"))["count"] == 0  # layout change
    assert (await engine.test_selector(f"{SHOP}/shop", "div["))["error"] == "Selector does not parse"


@pytest.mark.req("FR-12")
async def test_fetch_outline_keeps_structure_and_drops_scripts(fake_web):
    fake_web["/x"] = (200, "<html><head><style>.a{}</style></head><body><div class='product'><h2>A</h2>"
                           "<script>steal()</script><span class='price'>Rs 1</span></div></body></html>")
    outline = await engine.fetch_outline(f"{SHOP}/x")
    assert "steal()" not in outline and ".a{}" not in outline
    assert 'class="product"' in outline and 'class="price"' in outline


@pytest.mark.req("FR-18")
async def test_agent_page_functions_go_through_safe_fetch(fake_web):
    with pytest.raises(engine.FetchRefused, match="private or internal"):
        await engine.fetch_outline("http://169.254.169.254/latest/meta-data/")
    with pytest.raises(engine.FetchRefused, match="HTTP 404"):
        await engine.fetch_outline(f"{SHOP}/missing")


async def test_tests_never_touch_the_real_network():
    """Without fake_web, the suite-wide guard makes every lookup fail (tests/conftest.py)."""
    with pytest.raises(engine.FetchRefused, match="Couldn't find the site"):
        await engine.fetch_outline("https://example.com/")


@pytest.mark.req("FR-36")
@pytest.mark.parametrize("path", ["/shop/nope", "/shop/p/not-a-product", "/shop/admin/nothing"])
def test_unknown_shop_paths_are_404_not_the_react_app(client, path):
    r = client.get(path)
    assert r.status_code == 404 and "Page not found" in r.text
