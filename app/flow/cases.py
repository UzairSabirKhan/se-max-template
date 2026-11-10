"""Known-invalid flows: one per rule. Used by the tests and exported to
contracts/examples/invalid_<name>.json so the UI can show each error.

Each case: name -> (base example, mutation, substring expected in an issue message, for_publish).
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "contracts" / "examples"


def load_example(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES_DIR / f"{name}.json").read_text(encoding="utf-8"))


def _node(flow: dict, node_id: str) -> dict:
    return next(n for n in flow["nodes"] if n["id"] == node_id)


def _set(path: list, value: Any) -> Callable[[dict], None]:
    def mutate(flow: dict) -> None:
        target: Any = _node(flow, path[0])
        for key in path[1:-1]:
            target = target[key]
        target[path[-1]] = value
    return mutate


def _add_edge(edge: dict) -> Callable[[dict], None]:
    return lambda flow: flow["edges"].append(edge)


def _add_node(node: dict) -> Callable[[dict], None]:
    return lambda flow: flow["nodes"].append(node)


def _remove_node(node_id: str) -> Callable[[dict], None]:
    def mutate(flow: dict) -> None:
        flow["nodes"] = [n for n in flow["nodes"] if n["id"] != node_id]
        flow["edges"] = [e for e in flow["edges"] if node_id not in (e["source"], e["target"])]
    return mutate


def _drop_edge_key(edge_id: str, key: str) -> Callable[[dict], None]:
    return lambda flow: next(e for e in flow["edges"] if e["id"] == edge_id).pop(key)


def _chain(*mutations: Callable[[dict], None]) -> Callable[[dict], None]:
    def mutate(flow: dict) -> None:
        for m in mutations:
            m(flow)
    return mutate


Case = tuple[str, Callable[[dict], None], str, bool]

INVALID_CASES: dict[str, Case] = {
    # --- schema (FR-03) ---
    "unknown_key": ("list_tracking", _set(["f1", "config", "headers"], {"X": "1"}),
                    "Extra inputs are not permitted", False),
    "bad_selector": ("list_tracking", _set(["e1", "config", "base_selector"], "div["),
                     "Selector does not parse", False),
    "long_selector": ("list_tracking", _set(["e1", "config", "base_selector"], "div " * 60),
                      "at most 200 characters", False),
    "code_in_title": ("list_tracking", _set(["a1", "config", "title"], "<script>alert(1)</script>"),
                      "may not contain", False),
    "template_in_rule": ("list_tracking",
                         _set(["c2", "config", "rules"], [{"field": "title", "op": "contains",
                                                           "value": "{{ secret }}"}]),
                         "may not contain", False),
    "file_url": ("list_tracking", _set(["f1", "config", "url"], "file:///etc/passwd"),
                 "Only http and https", False),
    "unknown_node_type": ("list_tracking", _add_node({"id": "x1", "type": "run_python", "config": {}}),
                          "does not match any of the expected tags", False),
    "pii_field": ("list_tracking",
                  _set(["e1", "config", "fields"], [
                      {"name": "url", "selector": "a", "attr": "href", "type": "url"},
                      {"name": "seller_phone", "selector": ".p", "type": "text"}]),
                  "looks like personal data", False),
    "identity_not_field": ("list_tracking", _set(["e1", "config", "identity_key"], "sku"),
                           "must be one of the fields", False),
    "op_needs_value": ("list_tracking", _set(["c2", "config", "rules"], [{"field": "price", "op": "lt"}]),
                       "needs a value", False),
    "interval_without_minutes": ("list_tracking", _set(["t1", "config"], {"mode": "interval"}),
                                 "needs every_minutes", False),
    # --- graph (FR-04) ---
    "two_triggers": ("list_tracking", _add_node({"id": "t2", "type": "trigger", "config": {}}),
                     "exactly one Trigger", False),
    "no_check_page": ("list_tracking", _chain(
        _remove_node("k1"), _add_edge({"id": "e_e1_s1", "source": "e1", "target": "s1"})),
        "exactly one Check Page", False),
    "cycle": ("list_tracking", _chain(
        _add_edge({"id": "e_c1_c2", "source": "c1", "sourceHandle": "false", "target": "c2"}),
        _add_edge({"id": "e_c2_c1", "source": "c2", "sourceHandle": "false", "target": "c1"})),
        "cycle", False),
    "condition_without_handle": ("list_tracking", _drop_edge_key("e_c1_a1", "sourceHandle"),
                                 "'true' or 'false' handle", False),
    "orphan_node": ("list_tracking", _add_node({"id": "r1", "type": "results", "config": {"name": "Lost"}}),
                    "not connected after Check Page", False),
    "fetch_after_check": ("list_tracking", _chain(
        _add_node({"id": "f2", "type": "fetch_page", "config": {"url": "https://example.com/"}}),
        _add_edge({"id": "e_k1_f2", "source": "k1", "target": "f2"})),
        "can't come after Check Page", False),
    "bad_spine": ("list_tracking", _chain(
        _remove_node("e1"), _add_edge({"id": "e_p1_k1", "source": "p1", "target": "k1"})),
        "The flow must start", False),
    "edge_crosses_loop_wall": ("multi_link",
                               _add_edge({"id": "e_b2_s1", "source": "b2", "target": "s1"}),
                               "cross a loop's wall", False),
    "nested_loop": ("multi_link", _add_node({"id": "l2", "type": "for_each", "parentId": "l1", "config": {}}),
                    "can't be nested", False),
    "save_inside_loop": ("multi_link", _add_node({
        "id": "s2", "type": "save_records", "parentId": "l1",
        "config": {"dataset": "inner", "track_fields": ["price"]}}),
        "can't be inside a loop", False),
    "missing_variable": ("multi_link", _set(["l1", "config", "source"], {"var": "nope"}),
                         "does not exist", False),
    "wrong_variable_type": ("multi_link", _set(["c1", "config", "rules"], [
        {"field": "price", "op": "drop_pct_gt", "value": {"var": "watch_urls"}}]),
        "this place needs", False),
    "op_wrong_field_type": ("list_tracking", _set(["c2", "config", "rules"], [
        {"field": "title", "op": "lt", "value": 5}]),
        "can't be used on a text field", False),
    "history_op_without_save": ("list_tracking", _chain(
        _remove_node("s1"),
        _add_edge({"id": "e_k1_c1", "source": "k1", "target": "c1"}),
        _add_edge({"id": "e_k1_c2", "source": "k1", "target": "c2"})),
        "put a Save Records node before", False),
    "track_unknown_field": ("list_tracking", _set(["s1", "config", "track_fields"], ["discount"]),
                            "not an extracted field", False),
    # --- found in the senior review ---
    "rule_value_boolean": ("list_tracking", _set(["c2", "config", "rules"], [
        {"field": "price", "op": "lt", "value": True}]),
        "not true/false", False),
    "rule_value_not_a_number": ("list_tracking", _set(["c2", "config", "rules"], [
        {"field": "price", "op": "lt", "value": "nan"}]),
        "needs a number", False),
    "rule_value_bad_date": ("list_tracking", _chain(
        lambda f: _node(f, "e1")["config"]["fields"].append(
            {"name": "listed", "selector": ".listed", "type": "date"}),
        _set(["c2", "config", "rules"], [{"field": "listed", "op": "lt", "value": "yesterday"}])),
        "needs a date", False),
    "url_with_space": ("list_tracking", _set(["f1", "config", "url"], "https://exa mple.com/shop"),
                       "may not contain spaces", False),
    "duplicate_edge": ("list_tracking", _add_edge({"id": "e_s1_c1_again", "source": "s1", "target": "c1"}),
                       "duplicates edge", False),
    "loop_body_orphan": ("multi_link", _add_node({"id": "b3", "type": "wait", "parentId": "l1", "config": {}}),
                         "not connected to its 'item' handle", False),
    "field_not_upstream": ("list_tracking", _chain(
        # A later loop extracts 'discount', but condition c2 (not downstream of it) uses it.
        _add_node({"id": "l2", "type": "for_each", "config": {"source": "items"}}),
        _add_node({"id": "bf", "type": "fetch_item_page", "parentId": "l2", "config": {"url_field": "url"}}),
        _add_node({"id": "bx", "type": "extract_fields", "parentId": "l2", "config": {"fields": [
            {"name": "discount", "selector": ".discount", "type": "int"}]}}),
        _add_node({"id": "r1", "type": "results", "config": {"name": "Detail"}}),
        _add_edge({"id": "e_s1_l2", "source": "s1", "target": "l2"}),
        _add_edge({"id": "e_l2_bf", "source": "l2", "sourceHandle": "item", "target": "bf"}),
        _add_edge({"id": "e_bf_bx", "source": "bf", "target": "bx"}),
        _add_edge({"id": "e_bx_l2", "source": "bx", "target": "l2", "targetHandle": "next"}),
        _add_edge({"id": "e_l2_r1", "source": "l2", "sourceHandle": "done", "target": "r1"}),
        _set(["c2", "config", "rules"], [{"field": "discount", "op": "gt", "value": 10}])),
        "not extracted before this step", False),
    # --- publish only (FR-27) ---
    "browser_node_at_publish": ("list_tracking", _chain(
        _add_node({"id": "x1", "type": "click", "config": {"selector": "button.more"}}),
        _add_edge({"id": "e_k1_x1", "source": "k1", "target": "x1"})),
        "needs a browser", True),
}


def build_case(name: str) -> tuple[dict[str, Any], str, bool]:
    base, mutate, expected, for_publish = INVALID_CASES[name]
    flow = copy.deepcopy(load_example(base))
    mutate(flow)
    return flow, expected, for_publish
