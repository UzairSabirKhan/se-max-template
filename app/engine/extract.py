"""Extraction (A12; FR-21) and page facts for the classifier. Pure functions: HTML in, items out.

Every field is read INSIDE its own item element (`item.css_first(selector)`), so two products with the
same price can't be confused and a value from the wrong item can't leak in (EC-39).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from selectolax.lexbor import LexborHTMLParser, LexborNode

from app.engine.normalise import normalise


@dataclass
class Item:
    """One extracted thing (a product, an article...). `key` is its identity value."""

    data: dict[str, Any] = field(default_factory=dict)      # field -> normalised value (None if missing)
    status: dict[str, str] = field(default_factory=dict)    # field -> "ok" | "empty" | "invalid"
    key: str | None = None
    source: str = ""                                        # the page it came from
    error: str | None = None                                # set when a loop step failed for this item

    def as_report(self) -> dict[str, Any]:
        out: dict[str, Any] = {"key": self.key, "data": dict(self.data)}
        if self.error:
            out["error"] = self.error
        return out


def _raw_value(node: LexborNode, selector: str, attr: str | None) -> str | None:
    # ":scope" = the item element itself (selectolax can't parse it, so it never reaches css_first).
    found = node if selector == ":scope" else node.css_first(selector)
    if found is None:
        return None
    if attr:
        return found.attributes.get(attr)
    return found.text(deep=True, separator=" ", strip=True)


def read_fields(scope: LexborNode, fields: list[Any], base_url: str) -> tuple[dict[str, Any], dict[str, str]]:
    data: dict[str, Any] = {}
    status: dict[str, str] = {}
    for f in fields:
        value = normalise(_raw_value(scope, f.selector, f.attr), f.type, base_url)
        data[f.name] = value.value
        status[f.name] = value.status
    return data, status


def extract_list(html: str, base_url: str, config: Any) -> list[Item]:
    """`extract_list`: one Item per `base_selector` match, each field read inside that element."""
    tree = LexborHTMLParser(html)
    items = []
    for element in tree.css(config.base_selector):
        data, status = read_fields(element, config.fields, base_url)
        key = data.get(config.identity_key)
        items.append(Item(data=data, status=status, key=str(key) if key not in (None, "") else None,
                          source=base_url))
    return items


def extract_fields(html: str, base_url: str, fields: list[Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """`extract_fields`: the whole page is one item (a product page)."""
    tree = LexborHTMLParser(html)
    root = tree.body or tree.root
    return read_fields(root, fields, base_url)


def next_page_url(html: str, base_url: str, next_selector: str) -> str | None:
    """The href of the pagination "next" link, made absolute, or None on the last page."""
    from urllib.parse import urljoin

    found = LexborHTMLParser(html).css_first(next_selector)
    href = found.attributes.get("href") if found is not None else None
    return urljoin(base_url, href) if href else None


# ---------------------------------------------------------------------------
# Page facts the classifier needs (block pages, JavaScript shells, anchors)
# ---------------------------------------------------------------------------
_BLOCK_MARKERS = (
    "verify you are human", "are you a robot", "are you human", "captcha", "access denied",
    "unusual traffic", "checking your browser", "just a moment", "attention required", "request blocked",
    "please enable cookies", "bot detection",
)
_SHELL_ROOT_IDS = ("root", "app", "__next", "__nuxt", "svelte")


def block_marker(html: str) -> str | None:
    """A captcha / challenge phrase in the visible text, or None."""
    tree = LexborHTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    title = tree.css_first("title")
    text = " ".join(filter(None, [title.text() if title else "", (tree.body.text(separator=" ") if tree.body else "")]))
    text = re.sub(r"\s+", " ", text).lower()[:5000]
    return next((m for m in _BLOCK_MARKERS if m in text), None)


def is_app_shell(html: str) -> bool:
    """A page that builds itself with JavaScript: an empty app root, or almost no text but scripts."""
    tree = LexborHTMLParser(html)
    if "__NEXT_DATA__" in html or "window.__NUXT__" in html:
        return True
    scripts = len(tree.css("script"))
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = re.sub(r"\s+", " ", tree.body.text(separator=" ") if tree.body else "").strip()
    for root_id in _SHELL_ROOT_IDS:
        root = tree.css_first(f"#{root_id}")
        if root is not None and not root.text(strip=True) and len(text) < 200:
            return True
    return scripts > 0 and len(text) < 40


def has_anchor(html: str, selector: str | None) -> bool | None:
    """None when no page_anchor is configured."""
    if not selector:
        return None
    return LexborHTMLParser(html).css_first(selector) is not None
