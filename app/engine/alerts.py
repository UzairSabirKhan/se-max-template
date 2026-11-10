"""Alert payloads (A16; FR-31). Pure: builds what to store; app/db/runs.py stores it, de-duplicated.

- Condition alerts: one per item that reached an Alert step, saying WHY ("Blue Kettle: Rs 1,250 →
  Rs 1,099 (−12%)"). De-dup key: flow + alert step + item + its values, so the same item at the same
  price alerts once, not on every run (EC-38).
- System alerts from the verdict: Site changed (BROKEN) at once; BLOCKED only on the 2nd run in a row
  (EC-27); UNSUPPORTED; SUSPECT values held for confirmation.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation
from typing import Any

from app.engine.records import Labelled


def _short_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()[:16]


def money(value: Any) -> str:
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError):
        return str(value)
    return f"Rs {int(d):,}" if d == d.to_integral_value() else f"Rs {d:,.2f}"


def _label(item: Labelled) -> str:
    data = item.item.data
    return str(data.get("title") or data.get("name") or item.item.key or "An item")


def describe(item: Labelled, field_types: dict[str, str]) -> str:
    """One sentence saying what happened to this item."""
    name = _label(item)
    if item.change == "new":
        prices = [item.item.data[f] for f, t in field_types.items() if t == "price" and item.item.data.get(f)]
        price = prices[0] if prices else None
        return f"New: {name}" + (f" at {money(price)}" if price else "")
    if item.change == "removed":
        return f"Removed: {name}"
    if item.change in ("changed", "suspect") and item.changed_fields:
        parts = []
        for f in item.changed_fields:
            before, after = item.previous.get(f), item.item.data.get(f)
            if field_types.get(f) == "price":
                pct = item.pct_change.get(f)
                arrow = f"{money(before)} → {money(after)}"
                parts.append(arrow + (f" ({'−' if pct < 0 else '+'}{abs(round(pct))}%)" if pct is not None else ""))
            elif field_types.get(f) == "stock":
                parts.append({"in": "back in stock", "out": "out of stock"}.get(str(after), f"stock {after}"))
            else:
                parts.append(f"{f} {before} → {after}")
        return f"{name}: " + ", ".join(parts)
    return f"{name}: matched"


def condition_alerts(flow_id: str, node_id: str, title: str, level: str, items: list[Labelled],
                     field_types: dict[str, str]) -> list[dict[str, Any]]:
    out = []
    for item in items:
        values = {k: item.item.data.get(k) for k in sorted(item.item.data)}
        out.append({
            "node_id": node_id, "kind": "condition", "level": level, "title": title,
            "message": describe(item, field_types), "items": [item.as_report()],
            "dedupe_key": f"{flow_id}:{node_id}:{_short_hash([item.item.key, item.change, values])}",
        })
    return out


SYSTEM_TITLES = {"BROKEN": ("site_changed", "error", "Site changed"),
                 "BLOCKED": ("blocked", "warning", "Site blocked the run"),
                 "UNSUPPORTED": ("unsupported", "warning", "Page needs JavaScript"),
                 "SUSPECT": ("suspect", "warning", "Suspicious value held for review")}


def system_alert(flow_id: str, run_id: str, verdict: str, reason: str, published_hash: str | None,
                 previous_verdict: str | None, items: list[Labelled] | None = None) -> dict[str, Any] | None:
    if verdict not in SYSTEM_TITLES:
        return None
    if verdict == "BLOCKED" and previous_verdict != "BLOCKED":
        return None  # one blocked run can be a hiccup; alert on the second in a row
    kind, level, title = SYSTEM_TITLES[verdict]
    message = reason if verdict != "BROKEN" else f"{reason}. Nothing was stored; the last good data is kept."
    # Once per published version and reason; a new reason (or republishing) can alert again.
    key = f"{flow_id}:{kind}:{published_hash or 'draft'}:{_short_hash(reason)}"
    if verdict == "SUSPECT":
        key = f"{flow_id}:{kind}:{_short_hash([(x.item.key, x.item.data) for x in (items or [])])}"
    return {"node_id": None, "kind": kind, "level": level, "title": title, "message": message,
            "items": [x.as_report() for x in (items or [])][:10], "dedupe_key": key}
