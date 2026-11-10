"""Normalisers (A10; FR-21). Edge cases EC-40 – EC-44 in docs/testing.md."""

import pytest

from app.engine.normalise import normalise, parse_date, parse_int, parse_price, parse_stock, parse_text, parse_url


@pytest.mark.req("FR-21")
@pytest.mark.parametrize("raw,expected", [
    ("Rs 1,250", "1250.00"), ("Rs. 1,250/-", "1250.00"), ("₨1250", "1250.00"), ("PKR 1,250.00", "1250.00"),
    ("Rs 1,250.50", "1250.50"), ("£51.77", "51.77"), ("$ 9.99", "9.99"), ("€1.250,00", "1250.00"),
    ("1.250,5", "1250.50"), ("12,50 €", "12.50"), ("1,250,000", "1250000.00"), ("1.250.000", "1250000.00"),
    ("Rs 1,250", "1250.00"), ("  Rs   999  ", "999.00"), ("Price: Rs 3,999 (incl. tax)", "3999.00"),
    ("Rs 1,099 Rs 1,250", "1099.00"), ("۱۲۵۰ روپے", "1250.00"), ("٣٬٩٩٩", "3999.00"),
])
def test_price(raw, expected):
    assert parse_price(raw).value == expected and parse_price(raw).status == "ok"


@pytest.mark.req("FR-21")
@pytest.mark.parametrize("raw", ["", "   ", "N/A", "-", "—", None, "Free", "Call for price", "Out of stock", "Sold out"])
def test_price_text(raw):
    assert parse_price(raw).status == "empty" and parse_price(raw).value is None


@pytest.mark.req("FR-21")
@pytest.mark.parametrize("raw", ["Rs 0", "Rs 0.00", "abc", "-1,250", "Rs -99"])
def test_price_that_is_not_a_price_is_invalid(raw):
    assert parse_price(raw).status == "invalid"


@pytest.mark.req("FR-21")
def test_eastern_digits():
    assert parse_price("Rs ۱,۲۵۰").value == "1250.00"
    assert parse_int("۱۲").value == 12
    assert parse_text("قیمت ۱۲۵۰").value == "قیمت 1250"  # Urdu text kept, digits made ASCII


@pytest.mark.req("FR-21")
@pytest.mark.parametrize("raw,expected", [("12", 12), ("1,250", 1250), ("Only 2 left", 2), ("Qty: 30 pcs", 30)])
def test_int(raw, expected):
    assert parse_int(raw).value == expected


@pytest.mark.req("FR-21")
@pytest.mark.parametrize("raw,base,expected", [
    ("/shop/p/blue-kettle", "https://app.example.com/shop?page=2", "https://app.example.com/shop/p/blue-kettle"),
    ("p/tea-set", "https://app.example.com/shop/", "https://app.example.com/shop/p/tea-set"),
    ("https://other.example.com/x#reviews", "", "https://other.example.com/x"),
])
def test_url(raw, base, expected):
    assert parse_url(raw, base).value == expected


@pytest.mark.req("FR-21")
@pytest.mark.parametrize("raw", ["javascript:alert(1)", "mailto:a@b.com", "data:text/html,x", "#top"])
def test_url_that_is_not_a_web_link_is_invalid(raw):
    assert parse_url(raw, "").status == "invalid"


@pytest.mark.req("FR-21")
@pytest.mark.parametrize("raw,expected", [
    ("2026-11-10", "2026-11-10"), ("10 Nov 2026", "2026-11-10"), ("Nov 10, 2026", "2026-11-10"),
    ("10th November 2026", "2026-11-10"), ("10/11/2026", "2026-11-10"), ("2026-11-10T09:00:00Z", "2026-11-10"),
])
def test_date(raw, expected):
    assert parse_date(raw).value == expected


@pytest.mark.req("FR-21")
@pytest.mark.parametrize("raw,expected", [
    ("In stock", "in"), ("Only 2 left", "in"), ("Add to cart", "in"), ("Sold out", "out"),
    ("Out of stock", "out"), ("Currently unavailable", "out"), ("Not available", "out"),
])
def test_stock(raw, expected):
    assert parse_stock(raw).value == expected


@pytest.mark.req("FR-21")
def test_text_collapses_whitespace_and_treats_markers_as_empty():
    assert parse_text("  Blue \n\t Kettle ").value == "Blue Kettle"
    assert parse_text("N/A").status == "empty"
    assert len(parse_text("x" * 2000).value) == 500


@pytest.mark.req("FR-21")
def test_dispatch_by_field_type():
    assert normalise("Rs 1,250", "price").value == "1250.00"
    assert normalise("/p/x", "url", "https://a.example.com/").value == "https://a.example.com/p/x"
    assert normalise("Sold out", "stock").value == "out"
    assert normalise("  hi ", "text").value == "hi"
    assert normalise("abc", "price").status == "invalid"
