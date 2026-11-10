"""check_page: one verdict about the health of the pages and items of a run (A14; FR-20, FR-28).

A pure function: no I/O, no AI. Checks run in this order and the first match wins (design.md "Run
classifier"), so a captcha page can never look like "all items removed" and a broken selector can
never look like "every price changed":

1. BLOCKED      hard signals: fetch errors, HTTP 4xx/5xx, a challenge header, captcha text with no items
2. UNSUPPORTED  no items and the page is a JavaScript app shell
3. BLOCKED      softer signals: the page anchor is missing, or the page is under 20% of its usual size
   (checked after 2, because a JavaScript shell also lacks the anchor and is tiny)
4. BROKEN       wrong item count, a required field mostly missing, values that don't parse, duplicate keys

Healthy pages return verdict None; the records step (records.py) then decides CHANGED / OK / SUSPECT.
Thresholds are strict: exactly 50% coverage is NOT broken; lists under 5 items use absolute counts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.engine.extract import Item


@dataclass
class PageFact:
    url: str
    status: int | None = None          # None when the fetch failed
    body_size: int = 0
    error: str | None = None
    error_kind: str | None = None
    challenge: bool = False            # e.g. a `cf-mitigated: challenge` header
    marker: str | None = None          # captcha / "verify you are human" text
    shell: bool = False                # JavaScript app shell
    anchor: bool | None = None         # page_anchor found? None = not configured

    def as_report(self) -> dict[str, Any]:
        out: dict[str, Any] = {"url": self.url, "status": self.status, "body_size": self.body_size}
        if self.error:
            out["error"] = self.error
        return out


@dataclass
class LastGood:
    items_found: int
    coverage: dict[str, float]
    body_size: int


@dataclass
class FieldInfo:
    type: str
    required: bool


@dataclass
class Health:
    verdict: str | None                 # BLOCKED | UNSUPPORTED | BROKEN, or None when healthy
    reason: str = ""
    evidence: list[str] = field(default_factory=list)
    coverage: dict[str, float] = field(default_factory=dict)
    items_found: int = 0
    items_valid: int = 0
    parse_fail_rate: float = 0.0


SMALL_LIST = 5
MIN_COVERAGE = 0.5
MAX_COVERAGE_DROP = 0.30
MIN_COUNT_VS_LAST = 0.5
MAX_PARSE_FAIL = 0.5
MIN_SIZE_VS_LAST = 0.2
MAX_FAILED_PAGES = 0.5


def _pct(n: int, d: int) -> str:
    return f"{round(100 * n / d)}%" if d else "0%"


def check_page(pages: list[PageFact], items: list[Item], fields: dict[str, FieldInfo],
               expected_count: Any = None, last_good: LastGood | None = None) -> Health:
    n = len(items)
    usable = [i for i in items if not i.error]
    coverage = {
        name: (sum(1 for i in usable if i.status.get(name) == "ok") / len(usable)) if usable else 0.0
        for name in fields
    }
    required = [name for name, info in fields.items() if info.required]
    valid = sum(1 for i in usable if i.key and all(i.status.get(r) == "ok" for r in required))
    values = [s for i in usable for s in i.status.values() if s != "empty"]
    parse_fail_rate = (values.count("invalid") / len(values)) if values else 0.0
    base = dict(coverage=coverage, items_found=n, items_valid=valid, parse_fail_rate=parse_fail_rate)

    def verdict(v: str, reason: str, *evidence: str) -> Health:
        return Health(verdict=v, reason=reason, evidence=[reason, *evidence], **base)

    # 1. BLOCKED: hard signals ---------------------------------------------------------------------------
    failed = [p for p in pages if p.error or (p.status is not None and p.status >= 400)]
    if pages and failed:
        many = len(pages) > 1
        if not many or len(failed) / len(pages) >= MAX_FAILED_PAGES:
            first = failed[0]
            what = first.error or f"the site answered HTTP {first.status}"
            reason = (f"{len(failed)} of {len(pages)} pages could not be read: {what}" if many
                      else f"The page could not be read: {what}")
            return verdict("BLOCKED", reason, *[f"{p.url}: {p.error or 'HTTP ' + str(p.status)}" for p in failed[:5]])
    if any(p.challenge for p in pages):
        return verdict("BLOCKED", "The site showed a bot challenge instead of the page")
    marked = [p for p in pages if p.marker]
    if marked and not usable:
        return verdict("BLOCKED", f"The site showed a block page (“{marked[0].marker}”), not the shop")

    # 2. UNSUPPORTED ---------------------------------------------------------------------------------------
    if not usable and any(p.shell for p in pages):
        return verdict("UNSUPPORTED", "This page loads its data with JavaScript, which ScrapeOnce does not support.")

    # 3. BLOCKED: softer signals ---------------------------------------------------------------------------
    if any(p.anchor is False for p in pages):
        return verdict("BLOCKED", "The page is missing the part that marks a real product page (page anchor)")
    if last_good and last_good.body_size and pages:
        size = sum(p.body_size for p in pages)
        if size < MIN_SIZE_VS_LAST * last_good.body_size:
            return verdict("BLOCKED", f"The page is much smaller than usual ({size} bytes, usually "
                                      f"{last_good.body_size})")

    # 4. BROKEN ----------------------------------------------------------------------------------------------
    low = getattr(expected_count, "min", None)
    high = getattr(expected_count, "max", None)
    if expected_count is not None and not (low <= n <= high):
        return verdict("BROKEN", f"Found {n} items, expected {low} to {high}")
    if n == 0 and (expected_count is None or low > 0):
        return verdict("BROKEN", "No items found: the item selector matches nothing")
    if last_good and last_good.items_found >= SMALL_LIST and n < MIN_COUNT_VS_LAST * last_good.items_found:
        return verdict("BROKEN", f"Found {n} items, under half of the last good run ({last_good.items_found})")

    for name in required:
        missing = sum(1 for i in usable if i.status.get(name) != "ok")
        total = len(usable)
        if not total or not missing:
            continue
        if total < SMALL_LIST:
            broken = missing >= 2 or missing == total
        else:
            broken = coverage[name] < MIN_COVERAGE
        if broken:
            return verdict("BROKEN", f"{name} missing on {missing} of {total} items",
                           f"Site changed: the selector for {name} no longer matches")
        if last_good and name in last_good.coverage and total >= SMALL_LIST:
            drop = round(last_good.coverage[name] - coverage[name], 6)  # 1.0 - 0.7 is 0.30000000000000004
            if drop > MAX_COVERAGE_DROP:
                return verdict("BROKEN", f"{name} filled on {_pct(total - missing, total)} of items, down from "
                                         f"{round(100 * last_good.coverage[name])}% in the last good run")

    if parse_fail_rate > MAX_PARSE_FAIL:
        return verdict("BROKEN", f"{_pct(values.count('invalid'), len(values))} of values don't parse as their type")

    keys = [i.key for i in usable if i.key]
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    if dupes:
        return verdict("BROKEN", f"{len(dupes)} identity value(s) appear on more than one item",
                       *[f"duplicate: {k}" for k in dupes[:5]])

    evidence = []
    if failed:
        evidence.append(f"{len(failed)} of {len(pages)} pages could not be read and were skipped")
    return Health(verdict=None, reason="", evidence=evidence, **base)
