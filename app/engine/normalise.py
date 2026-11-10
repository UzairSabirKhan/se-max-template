"""Turn scraped text into typed values (A10; FR-21). Pure functions, no I/O, no AI.

Each field type has one parser. `normalise(raw, type, base_url)` returns a Value with a status:
- "ok":      parsed (value is set)
- "empty":   nothing there ("", "N/A", "-", "Call for price"...): counts as a MISSING value
- "invalid": text was there but doesn't parse as this type: counts as a PARSE FAILURE (a breakage signal)

Prices are Decimal, never float, and are returned as strings with 2 decimals ("1250.00").
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal
from urllib.parse import urljoin, urlsplit

Status = Literal["ok", "empty", "invalid"]


@dataclass(frozen=True)
class Value:
    value: str | int | None
    status: Status


EMPTY = Value(None, "empty")
INVALID = Value(None, "invalid")

MAX_TEXT = 500
_EMPTY_MARKERS = {"", "-", "–", "—", "n/a", "na", "none", "null", "nil", "tbd", "...", "…"}
_NO_PRICE_WORDS = ("free", "call for price", "contact for price", "price on request", "ask for price",
                   "out of stock", "sold out", "unavailable", "coming soon")

# Arabic-Indic (U+0660–0669) and Extended Arabic-Indic / Urdu (U+06F0–06F9) digits -> ASCII.
_DIGITS = {ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")} | {ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")}
_DIGITS |= {ord("٫"): ".", ord("٬"): ","}  # Arabic decimal and thousands separators


def clean_text(raw: str | None) -> str:
    """Collapse whitespace (including non-breaking spaces) and map Urdu/Arabic digits to ASCII."""
    if raw is None:
        return ""
    text = unicodedata.normalize("NFKC", str(raw)).translate(_DIGITS)
    return " ".join(text.split())


def _is_empty(text: str) -> bool:
    return text.strip().lower() in _EMPTY_MARKERS


# ---------------------------------------------------------------------------
# Field types
# ---------------------------------------------------------------------------
def parse_text(raw: str | None) -> Value:
    text = clean_text(raw)
    if _is_empty(text):
        return EMPTY
    return Value(text[:MAX_TEXT], "ok")


_NUMBER = re.compile(r"\d[\d.,' ]*\d|\d")


def _to_decimal(token: str) -> Decimal | None:
    """'1,250' -> 1250; '1,250.50' -> 1250.50; '1.250,50' -> 1250.50; '1 250' -> 1250; '12,5' -> 12.5."""
    token = token.replace(" ", "").replace("'", "")
    has_dot, has_comma = "." in token, "," in token
    if has_dot and has_comma:
        decimal_sep = "." if token.rfind(".") > token.rfind(",") else ","
        thousands = "," if decimal_sep == "." else "."
        token = token.replace(thousands, "").replace(decimal_sep, ".")
    elif has_comma:
        parts = token.split(",")
        if len(parts) > 2 or len(parts[-1]) == 3:      # 1,250 or 1,250,000 -> thousands
            token = token.replace(",", "")
        else:                                           # 12,5 or 12,50 -> decimal comma
            token = token.replace(",", ".")
    elif has_dot:
        parts = token.split(".")
        if len(parts) > 2:                              # 1.250.000 -> thousands
            token = token.replace(".", "")
    try:
        value = Decimal(token)
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def parse_price(raw: str | None) -> Value:
    """'Rs 1,250', 'Rs. 1,250/-', '₨1250', 'PKR 1,250.00', '£51.77', '€1.250,00', '۱۲۵۰' -> '1250.00'.

    Takes the FIRST number (a sale price usually comes first; an old struck-through price drifting into
    the same element is a known limitation). Zero or negative is not a price.
    """
    text = clean_text(raw)
    if _is_empty(text):
        return EMPTY
    lowered = text.lower()
    if any(word in lowered for word in _NO_PRICE_WORDS) and not _NUMBER.search(text):
        return EMPTY
    match = _NUMBER.search(text)
    if not match:
        return INVALID
    value = _to_decimal(match.group(0).strip(" .,'"))
    if value is None or value <= 0 or value >= Decimal("1e12"):
        return INVALID
    if "-" in text[: match.start()].replace("/-", ""):  # "-1,250" is not a price
        return INVALID
    return Value(str(value.quantize(Decimal("0.01"))), "ok")


def parse_int(raw: str | None) -> Value:
    """'12', '1,250', 'Only 2 left', '۱۲' -> int."""
    text = clean_text(raw)
    if _is_empty(text):
        return EMPTY
    match = re.search(r"-?\d[\d,]*", text)
    if not match:
        return INVALID
    digits = match.group(0).replace(",", "")
    try:
        return Value(int(digits), "ok")
    except ValueError:
        return INVALID


def parse_url(raw: str | None, base_url: str = "") -> Value:
    """Relative links are made absolute against the page URL. Only http(s) links count."""
    text = clean_text(raw)
    if _is_empty(text):
        return EMPTY
    absolute = urljoin(base_url, text) if base_url else text
    try:
        parts = urlsplit(absolute)
    except ValueError:
        return INVALID
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return INVALID
    return Value(absolute.split("#", 1)[0], "ok")


_DATE_FORMATS = (
    "%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y",
    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d",
)


def parse_date(raw: str | None) -> Value:
    """ISO, '10 Nov 2026', 'Nov 10, 2026', '10/11/2026' (day first, as in Pakistan) -> '2026-11-10'."""
    text = clean_text(raw)
    if _is_empty(text):
        return EMPTY
    candidate = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text).strip(" .")
    if re.match(r"\d{4}-\d{2}-\d{2}T", candidate):
        candidate = candidate[:10]
    for fmt in _DATE_FORMATS:
        try:
            return Value(datetime.strptime(candidate, fmt).date().isoformat(), "ok")
        except ValueError:
            continue
    try:
        return Value(date.fromisoformat(candidate).isoformat(), "ok")
    except ValueError:
        return INVALID


_OUT_WORDS = ("out of stock", "sold out", "unavailable", "not available", "stock out", "no stock",
              "currently unavailable", "0 left", "ختم")
_IN_WORDS = ("in stock", "available", "add to cart", "add to bag", "buy now", "left", "few remaining",
             "ready to ship", "دستیاب")


def parse_stock(raw: str | None) -> Value:
    """'In stock', 'Only 2 left' -> 'in'; 'Sold out', 'Out of stock' -> 'out'. Out-words win."""
    text = clean_text(raw).lower()
    if _is_empty(text):
        return EMPTY
    if any(word in text for word in _OUT_WORDS):
        return Value("out", "ok")
    if any(word in text for word in _IN_WORDS):
        return Value("in", "ok")
    return INVALID


def normalise(raw: str | None, field_type: str, base_url: str = "") -> Value:
    if field_type == "price":
        return parse_price(raw)
    if field_type == "int":
        return parse_int(raw)
    if field_type == "url":
        return parse_url(raw, base_url)
    if field_type == "date":
        return parse_date(raw)
    if field_type == "stock":
        return parse_stock(raw)
    return parse_text(raw)
