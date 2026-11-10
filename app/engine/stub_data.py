"""Fixed example payloads in the contract shapes (specs/contracts.md C3).

Used by the M0 stubs so the UI and the agent can be built before the real engine exists.
Everything here is invented demo data. Delete each piece once its real version lands.
"""

from __future__ import annotations

from typing import Any

STUB_NOTE = "STUB: fixed example data until the real engine lands"

_ITEMS: list[dict[str, Any]] = [
    {"key": "https://scrapeonce.onrender.com/shop/p/blue-kettle",
     "data": {"title": "Blue Kettle", "price": "1099.00", "stock": "in",
              "url": "https://scrapeonce.onrender.com/shop/p/blue-kettle"},
     "change": "changed", "previous": {"price": "1250.00"}, "pct_change": {"price": -12.08}},
    {"key": "https://scrapeonce.onrender.com/shop/p/steel-flask",
     "data": {"title": "Steel Flask", "price": "2400.00", "stock": "in",
              "url": "https://scrapeonce.onrender.com/shop/p/steel-flask"},
     "change": "same"},
    {"key": "https://scrapeonce.onrender.com/shop/p/tea-set",
     "data": {"title": "Tea Set", "price": "3999.00", "stock": "out",
              "url": "https://scrapeonce.onrender.com/shop/p/tea-set"},
     "change": "new"},
]


def run_summary(run_id: str = "run_stub1", flow_id: str = "flow_stub1", trigger: str = "dry_run") -> dict:
    return {
        "id": run_id, "flow_id": flow_id, "trigger": trigger, "verdict": "CHANGED",
        "reason": "1 price changed, 1 new item", "started_at": "2026-11-10T11:00:00Z",
        "duration_ms": 842, "items_found": 3, "items_valid": 3,
        "changes": {"new": 1, "changed": 1, "removed": 0}, "ai_calls": 0,
    }


def run_report(run_id: str = "run_stub1", flow_id: str = "flow_stub1", trigger: str = "dry_run") -> dict:
    return {
        **run_summary(run_id, flow_id, trigger),
        "evidence": [STUB_NOTE, "price changed on 1 of 3 items"],
        "http": [{"url": "https://scrapeonce.onrender.com/shop", "status": 200, "body_size": 18234}],
        "coverage": {"title": 1.0, "price": 1.0, "url": 1.0, "stock": 1.0},
        "node_trace": [
            {"node_id": "t1", "items_in": 0, "items_out": 0, "status": "ok"},
            {"node_id": "f1", "items_in": 0, "items_out": 0, "status": "ok"},
            {"node_id": "e1", "items_in": 0, "items_out": 3, "status": "ok"},
            {"node_id": "k1", "items_in": 3, "items_out": 3, "status": "ok"},
            {"node_id": "s1", "items_in": 3, "items_out": 3, "status": "ok"},
            {"node_id": "c2", "items_in": 3, "items_out": 1, "status": "ok"},
            {"node_id": "a2", "items_in": 1, "items_out": 1, "status": "ok"},
        ],
        "items": _ITEMS,
    }


def alerts(flow_id: str = "flow_stub1") -> list[dict]:
    return [
        {"id": "alert_stub2", "flow_id": flow_id, "run_id": "run_stub1", "node_id": "a2",
         "kind": "condition", "level": "warning", "title": "Price changed",
         "message": "Blue Kettle: Rs 1,250 → Rs 1,099 (−12%)", "items": [_ITEMS[0]],
         "created_at": "2026-11-10T11:00:01Z", "read": False},
        {"id": "alert_stub1", "flow_id": flow_id, "run_id": "run_stub0", "node_id": None,
         "kind": "site_changed", "level": "error", "title": "Site changed",
         "message": "price missing on 12 of 12 items. Nothing stored.", "items": [],
         "created_at": "2026-11-10T10:30:00Z", "read": True},
    ]


def datasets(flow_id: str = "flow_stub1") -> list[dict]:
    return [{"id": "ds_stub1", "name": "shop_prices", "identity_key": "url",
             "fields": {"title": "text", "price": "price", "url": "url", "stock": "stock"},
             "record_count": len(_ITEMS)}]


def records() -> list[dict]:
    return [
        {"id": f"rec_stub{i}", "key": it["key"], "data": it["data"],
         "first_seen": "2026-11-10T09:00:00Z",
         "last_changed": "2026-11-10T11:00:00Z" if it.get("change") == "changed" else None,
         "removed_at": None}
        for i, it in enumerate(_ITEMS, start=1)
    ]


def record_history() -> list[dict]:
    return [
        {"run_id": "run_stub0", "at": "2026-11-10T09:00:00Z", "change": "new", "field": None,
         "old_value": None, "new_value": None, "pct_change": None},
        {"run_id": "run_stub1", "at": "2026-11-10T11:00:00Z", "change": "changed", "field": "price",
         "old_value": "1250.00", "new_value": "1099.00", "pct_change": -12.08},
    ]
