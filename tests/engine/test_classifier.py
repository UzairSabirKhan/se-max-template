"""Extraction (A12), page health (A14) and record labels (A15, A24) on the REAL mock shop pages.

Edge cases EC-25 – EC-39 in docs/testing.md. Pure functions: no network, no database.
"""

from types import SimpleNamespace

import pytest

from app.engine.classify import FieldInfo, LastGood, PageFact, check_page
from app.engine.extract import Item, block_marker, extract_list, has_anchor, is_app_shell
from app.engine.records import diff_records
from app.flow.cases import load_example
from app.flow.schema import ExtractListConfig
from tests.conftest import mock_shop_pages

PAGES = mock_shop_pages()
BASE = "https://shop.example.com/shop"
CONFIG = ExtractListConfig.model_validate(
    next(n for n in load_example("list_tracking")["nodes"] if n["type"] == "extract_list")["config"])
FIELDS = {f.name: FieldInfo(f.type, f.required) for f in CONFIG.fields}


def run_page(path: str, last_good: LastGood | None = None, expected=None):
    status, html = PAGES[path]
    items = extract_list(html, BASE, CONFIG)
    fact = PageFact(url=BASE + path, status=status, body_size=len(html), marker=block_marker(html),
                    shell=is_app_shell(html), anchor=has_anchor(html, CONFIG.page_anchor))
    return items, check_page([fact], items, FIELDS, expected, last_good)


# --- extraction --------------------------------------------------------------------------------------
@pytest.mark.req("FR-21")
def test_extracts_typed_items_from_the_shop():
    items, health = run_page("/shop")
    assert health.verdict is None and health.items_found == 6 and health.items_valid == 6
    first = items[0]
    assert first.key == "https://shop.example.com/shop/p/blue-kettle"
    assert first.data == {"title": "Blue Kettle", "price": "1250.00",
                          "url": "https://shop.example.com/shop/p/blue-kettle", "stock": "in"}
    assert health.coverage == {"title": 1.0, "price": 1.0, "url": 1.0, "stock": 1.0}


@pytest.mark.req("FR-21")
def test_same_price():
    """EC-39: two products at Rs 1,250 (Blue Kettle and Lunch Box) both keep their own value."""
    items = extract_list(PAGES["/shop"][1], BASE, CONFIG) + extract_list(PAGES["/shop?page=2"][1], BASE, CONFIG)
    by_title = {i.data["title"]: i for i in items}
    assert by_title["Blue Kettle"].data["price"] == by_title["Lunch Box"].data["price"] == "1250.00"
    assert by_title["Blue Kettle"].key != by_title["Lunch Box"].key


# --- verdicts on the shop's own failure pages -------------------------------------------------------------
@pytest.mark.req("FR-28")
def test_layout_v2():
    """EC-25 (judge check 3): the redesign renamed .price, so price is missing everywhere: BROKEN."""
    _, health = run_page("/shop?layout=v2")
    assert health.verdict == "BROKEN"
    assert health.reason == "price missing on 6 of 6 items"
    assert any("no longer matches" in e for e in health.evidence)


@pytest.mark.req("FR-28")
def test_captcha_200():
    """EC-26: a captcha page with status 200 is BLOCKED, never 'all items removed'."""
    _, health = run_page("/shop?mode=blocked")
    assert health.verdict == "BLOCKED" and "block page" in health.reason


@pytest.mark.req("FR-20")
def test_js_shell():
    """EC-28: a JavaScript app shell is UNSUPPORTED (not BLOCKED for its missing anchor)."""
    _, health = run_page("/shop?mode=js")
    assert health.verdict == "UNSUPPORTED"
    assert health.reason == "This page loads its data with JavaScript, which ScrapeOnce does not support."


@pytest.mark.req("FR-28")
def test_duplicates():
    """EC-29"""
    _, health = run_page("/shop?mode=dupes")
    assert health.verdict == "BROKEN" and "more than one item" in health.reason


@pytest.mark.req("FR-28")
@pytest.mark.parametrize("status,error,expected", [
    (404, None, "HTTP 404"), (503, None, "HTTP 503"), (None, "The site didn't answer in time", "in time"),
    (None, "Not an HTML page (application/pdf)", "Not an HTML page"),
])
def test_fetch_failures_are_blocked(status, error, expected):
    health = check_page([PageFact(url=BASE, status=status, error=error)], [], FIELDS)
    assert health.verdict == "BLOCKED" and expected in health.reason


@pytest.mark.req("FR-28")
def test_missing_anchor_and_tiny_page_are_blocked():
    items, _ = run_page("/shop")
    no_anchor = check_page([PageFact(url=BASE, status=200, body_size=4000, anchor=False)], items, FIELDS)
    assert no_anchor.verdict == "BLOCKED" and "page anchor" in no_anchor.reason
    tiny = check_page([PageFact(url=BASE, status=200, body_size=500, anchor=True)], items, FIELDS,
                      last_good=LastGood(items_found=6, coverage={}, body_size=4000))
    assert tiny.verdict == "BLOCKED" and "much smaller" in tiny.reason


# --- boundaries (EC-30, EC-31) ---------------------------------------------------------------------------
def make_items(n: int, missing_price: int, prefix="k") -> list[Item]:
    out = []
    for i in range(n):
        ok = i >= missing_price
        out.append(Item(data={"title": f"T{i}", "price": "10.00" if ok else None, "url": f"{prefix}{i}"},
                        status={"title": "ok", "price": "ok" if ok else "empty", "url": "ok"}, key=f"{prefix}{i}"))
    return out


F3 = {"title": FieldInfo("text", True), "price": FieldInfo("price", True), "url": FieldInfo("url", True)}
OK_PAGE = [PageFact(url=BASE, status=200, body_size=1000)]


@pytest.mark.req("FR-28")
def test_boundaries():
    assert check_page(OK_PAGE, make_items(10, 5), F3).verdict is None          # exactly 50%: not broken
    assert check_page(OK_PAGE, make_items(10, 6), F3).verdict == "BROKEN"      # 40%: broken
    last = LastGood(items_found=10, coverage={"price": 1.0}, body_size=1000)
    assert check_page(OK_PAGE, make_items(10, 3), F3, last_good=last).verdict is None    # down 30 points
    assert check_page(OK_PAGE, make_items(10, 4), F3, last_good=last).verdict == "BROKEN"  # down 40 points


@pytest.mark.req("FR-28")
def test_small_list():
    assert check_page(OK_PAGE, make_items(4, 1), F3).verdict is None           # 1 missing of 4: tolerated
    assert check_page(OK_PAGE, make_items(4, 2), F3).verdict == "BROKEN"       # 2 missing of 4
    assert check_page(OK_PAGE, make_items(1, 1), F3).verdict == "BROKEN"       # the only item missing


@pytest.mark.req("FR-28")
def test_item_count_against_expected_and_last_good():
    expected = SimpleNamespace(min=10, max=14)
    assert "expected 10 to 14" in check_page(OK_PAGE, make_items(6, 0), F3, expected).reason
    last = LastGood(items_found=12, coverage={}, body_size=1000)
    assert "under half" in check_page(OK_PAGE, make_items(5, 0), F3, last_good=last).reason


@pytest.mark.req("FR-28")
def test_parse_failures():
    loose = {"title": FieldInfo("text", False), "url": FieldInfo("url", False), "price": FieldInfo("price", True)}
    items = make_items(10, 0)
    for i in items[:9]:  # 18 of 30 values invalid: 60%
        i.status["title"] = "invalid"
        i.status["url"] = "invalid"
    assert "don't parse" in check_page(OK_PAGE, items, loose).reason
    items = make_items(10, 0)
    for i in items[:7]:  # 14 of 30 values invalid: 47%, under the 50% limit
        i.status["title"] = "invalid"
        i.status["url"] = "invalid"
    assert check_page(OK_PAGE, items, loose).verdict is None


# --- records: labels and verdicts (EC-32 – EC-37) -----------------------------------------------------------
def stored_from(items):
    return {i.key: dict(i.data) for i in items}


@pytest.mark.req("FR-29")
def test_baseline():
    """EC-35: first run: everything new, verdict CHANGED with a 'starting point' reason."""
    items, _ = run_page("/shop")
    diff = diff_records(items, {}, ["price", "stock"])
    assert diff.verdict == "CHANGED" and all(x.change == "new" for x in diff.labelled)
    assert "starting point" in diff.reason


@pytest.mark.req("FR-29")
def test_no_change():
    """EC-36: same page twice, every item 'same', verdict OK."""
    items, _ = run_page("/shop")
    diff = diff_records(items, stored_from(items), ["price", "stock"])
    assert diff.verdict == "OK" and {x.change for x in diff.labelled} == {"same"}


@pytest.mark.req("FR-29")
def test_price_change():
    """EC-33"""
    items, _ = run_page("/shop")
    stored = stored_from(items)
    stored[items[0].key]["price"] = "1388.89"  # it was more expensive last time
    diff = diff_records(items, stored, ["price"])
    kettle = diff.labelled[0]
    assert diff.verdict == "CHANGED" and kettle.change == "changed"
    assert kettle.previous == {"price": "1388.89"} and kettle.pct_change == {"price": -10.0}


@pytest.mark.req("FR-29")
def test_reorder():
    """EC-37: matched by identity, not position."""
    items, _ = run_page("/shop")
    diff = diff_records(list(reversed(items)), stored_from(items), ["price"])
    assert diff.verdict == "OK"


@pytest.mark.req("FR-30")
def test_suspect():
    """EC-34: a 90% drop is held as SUSPECT."""
    items, _ = run_page("/shop")
    stored = stored_from(items)
    stored[items[0].key]["price"] = "12500.00"
    diff = diff_records(items, stored, ["price"])
    assert diff.verdict == "SUSPECT" and diff.labelled[0].change == "suspect"


@pytest.mark.req("FR-29")
def test_mass_removal():
    """EC-32: 30% vanished is BROKEN; one of six vanished (17%) is a real removal."""
    items = make_items(10, 0)
    assert diff_records(items[:7], stored_from(items), ["price"]).verdict == "BROKEN"
    shop, _ = run_page("/shop")
    diff = diff_records(shop[1:], stored_from(shop), ["price"])
    assert diff.verdict == "CHANGED" and diff.removed == [shop[0].key]


@pytest.mark.req("FR-29")
def test_exactly_twenty_percent_removed_is_broken():
    items = make_items(10, 0)
    assert diff_records(items[:8], stored_from(items), ["price"]).verdict == "BROKEN"
    assert diff_records(items[:9], stored_from(items), ["price"]).verdict == "CHANGED"
