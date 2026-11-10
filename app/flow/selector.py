"""Data selector: what a step can use from the steps before it (FR-02, FR-24).

    groups = data_for_step(flow, node_id, samples)

Data flows along the edges as items; later steps refer to item FIELDS by name. This lists, for one step,
every field produced UPSTREAM of it (grouped by the step that produced it), the change fields added by
Save records, and the flow's variables, with types, the condition operators each type allows, and a
sample value from the last run. The editor shows it as a picker, so names are chosen, not typed.

Works on half-built drafts (dicts, not validated models): incomplete steps are simply skipped.
There is no template language: a picked field is stored as its plain name, and the validator still
checks every setting (committee change 4).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.flow.schema import (
    FIELD_CHANGE_OPS,
    ITEM_CHANGE_OPS,
    NODE_CATALOGUE,
    NUMERIC_OPS,
    PRESENCE_OPS,
    STOCK_OPS,
    TEXT_OPS,
)

_LABELS = {e["type"]: e["label"] for e in NODE_CATALOGUE}
_OPS = {
    "price": [*NUMERIC_OPS, *PRESENCE_OPS], "int": [*NUMERIC_OPS, *PRESENCE_OPS], "date": [*NUMERIC_OPS, *PRESENCE_OPS],
    "text": [*TEXT_OPS, *PRESENCE_OPS], "url": [*TEXT_OPS, *PRESENCE_OPS], "stock": [*STOCK_OPS[:2], *PRESENCE_OPS],
}
_CHANGE_OPS = {"price": list(FIELD_CHANGE_OPS), "int": list(FIELD_CHANGE_OPS)}


def _ancestors(node_id: str, nodes: dict[str, dict], edges: list[dict]) -> list[str]:
    """Steps before `node_id`, nearest first. A loop body step also sees its loop and what's before it."""
    incoming: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        if e.get("targetHandle") != "next" and e.get("source") in nodes and e.get("target") in nodes:
            incoming[e["target"]].append(e["source"])
    order: list[str] = []
    frontier = [node_id]
    while frontier:
        current = frontier.pop(0)
        parents = list(incoming.get(current, []))
        parent_loop = nodes.get(current, {}).get("parentId")
        if parent_loop in nodes:
            parents.append(parent_loop)
        for p in parents:
            if p not in order and p != node_id:
                order.append(p)
                frontier.append(p)
    return order


def _fields_of(node: dict) -> list[dict]:
    fields = (node.get("config") or {}).get("fields") or []
    return [f for f in fields if isinstance(f, dict) and f.get("name") and f.get("type")]


def data_for_step(flow: dict, node_id: str, samples: dict[str, Any] | None = None) -> dict[str, Any]:
    samples = samples or {}
    nodes = {n["id"]: n for n in flow.get("nodes", []) if isinstance(n, dict) and n.get("id")}
    edges = [e for e in flow.get("edges", []) if isinstance(e, dict)]
    if node_id not in nodes:
        return {"node_id": node_id, "groups": [], "variables": [], "error": "Step not found in this draft"}

    groups: list[dict[str, Any]] = []
    seen: set[str] = set()
    has_history = False

    def field_entry(name: str, ftype: str, source: str) -> dict[str, Any]:
        entry = {"name": name, "type": ftype, "ops": _OPS.get(ftype, list(PRESENCE_OPS)),
                 "sample": samples.get(name), "source_node_id": source}
        return entry

    for anc_id in _ancestors(node_id, nodes, edges):
        anc = nodes[anc_id]
        kind = anc.get("type")
        produced: list[dict] = []
        if kind in ("extract_list", "extract_fields"):
            produced = _fields_of(anc)
        elif kind == "for_each":
            source = (anc.get("config") or {}).get("source")
            inside = nodes[node_id].get("parentId") == anc_id
            if isinstance(source, dict) and source.get("var"):
                produced.append({"name": "url", "type": "url"})       # each link becomes an item {"url": ...}
            if not inside:  # reached through 'done': everything the loop body read is available
                for child in nodes.values():
                    if child.get("parentId") == anc_id and child.get("type") == "extract_fields":
                        produced += _fields_of(child)
        elif kind == "save_records":
            has_history = True
        fresh = [f for f in produced if f["name"] not in seen]
        seen.update(f["name"] for f in fresh)
        if fresh:
            groups.append({"source_node_id": anc_id, "source_type": kind, "label": _LABELS.get(kind, kind),
                           "fields": [field_entry(f["name"], f["type"], anc_id) for f in fresh]})

    if has_history:
        tracked: list[dict[str, Any]] = [{"name": "change", "type": "change", "ops": list(ITEM_CHANGE_OPS),
                                          "sample": samples.get("change"), "source_node_id": None}]
        for g in groups:
            for f in g["fields"]:
                ops = _CHANGE_OPS.get(f["type"], ["changed"])
                if f["type"] == "stock":
                    ops = ["changed", "back_in_stock"]
                f["ops"] = [*f["ops"], *ops]
        groups.append({"source_node_id": next(a for a in _ancestors(node_id, nodes, edges)
                                              if nodes[a].get("type") == "save_records"),
                       "source_type": "save_records", "label": "Save records (changes since the last run)",
                       "fields": tracked})

    variables = [{"name": v.get("name"), "type": v.get("type"), "sample": v.get("value")}
                 for v in flow.get("variables", []) if isinstance(v, dict) and v.get("name")]
    return {"node_id": node_id, "groups": groups, "variables": variables}


def samples_from_report(report: dict[str, Any] | None) -> dict[str, Any]:
    """field -> the first non-empty value seen in a run report's items (plus an example change label)."""
    out: dict[str, Any] = {}
    for item in (report or {}).get("items", []):
        for name, value in (item.get("data") or {}).items():
            if name not in out and value not in (None, ""):
                out[name] = value
        if "change" not in out and item.get("change"):
            out["change"] = item["change"]
    return out
