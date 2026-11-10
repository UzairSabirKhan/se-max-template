"""Condition rules (FR-24): fixed operators, no expressions, no regex. Pure functions.

`matches(rules, match, item, variables, field_types)` -> bool. A value that is missing never matches a
comparison (a missing price is not "below 200"). SUSPECT items never count as "changed": their new value
is held until someone confirms it.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from app.engine.records import Labelled
from app.flow.schema import Rule, VarRef


def _num(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value).strip())
    except InvalidOperation:
        return None
    return result if result.is_finite() else None


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def _compare(op: str, left: Any, right: Any) -> bool:
    if left is None or right is None:
        return False
    return {
        "lt": left < right, "lte": left <= right, "gt": left > right, "gte": left >= right,
        "eq": left == right, "neq": left != right,
    }[op]


def rule_matches(rule: Rule, item: Labelled, variables: dict[str, Any], field_types: dict[str, str]) -> bool:
    value = rule.value
    if isinstance(value, VarRef):
        value = variables.get(value.var)
    op = rule.op

    if rule.field == "change":
        return (op == "is_new" and item.change == "new") or (op == "is_removed" and item.change == "removed")

    current = item.item.data.get(rule.field)
    ftype = field_types.get(rule.field, "text")
    if op == "is_empty":
        return current in (None, "")
    if op == "not_empty":
        return current not in (None, "")

    changed = item.change == "changed" and rule.field in item.changed_fields
    if op == "changed":
        return changed
    if op in ("increased", "decreased", "drop_pct_gt", "rise_pct_gt"):
        if not changed:
            return False
        before, after = _num(item.previous.get(rule.field)), _num(current)
        if before is None or after is None:
            return False
        if op == "increased":
            return after > before
        if op == "decreased":
            return after < before
        pct = item.pct_change.get(rule.field)
        limit = _num(value)
        if pct is None or limit is None:
            return False
        return -pct > limit if op == "drop_pct_gt" else pct > limit

    if op in ("in_stock", "out_of_stock", "back_in_stock"):
        if op == "in_stock":
            return current == "in"
        if op == "out_of_stock":
            return current == "out"
        return current == "in" and item.previous.get(rule.field) == "out"

    if op in ("contains", "not_contains"):
        if current is None:
            return False
        found = str(value).lower() in str(current).lower()
        return found if op == "contains" else not found

    if ftype in ("price", "int"):
        return _compare(op, _num(current), _num(value))
    if ftype == "date":
        return _compare(op, _date(current), _date(value))
    left = None if current is None else str(current).strip().lower()
    return _compare(op, left, str(value).strip().lower())


def matches(rules: list[Rule], match: str, item: Labelled, variables: dict[str, Any],
            field_types: dict[str, str]) -> bool:
    results = (rule_matches(r, item, variables, field_types) for r in rules)
    return any(results) if match == "any" else all(results)
