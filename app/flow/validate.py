"""validate_flow: schema checks + graph rules, returning issues in the contract C2 shape.

    validate_flow(flow, draft=True)        # save / agent edit: safety + structure only
    validate_flow(flow)                    # dry run / run: also completeness
    validate_flow(flow, for_publish=True)  # publish: also no browser nodes

Draft mode lets a half-built flow be saved (a Trigger alone, a node not yet connected), but
still refuses anything unsafe or structurally wrong: schema errors, bad handles, edges
through loop walls, nested loops, cycles, unknown variables.

An empty list means the flow is valid. Each issue is
    {"node_id": str | None, "path": str, "message": str}
"""

from __future__ import annotations

import copy
import re
from collections import defaultdict, deque
from datetime import date
from typing import Any, get_args

from pydantic import ValidationError

from app.flow.schema import (
    BROWSER_NODE_TYPES,
    FIELD_CHANGE_OPS,
    LOOP_BODY_TYPES,
    NUMERIC_OPS,
    OPS_NEEDING_HISTORY,
    PRESENCE_OPS,
    STOCK_OPS,
    TEXT_OPS,
    Flow,
    FlowNode,
    NodeBase,
    VarRef,
)

Issue = dict[str, Any]

# Which variable types may be used where (design.md "Variables").
_VAR_TYPES_FOR_NUMERIC = {"number", "price"}
_VAR_TYPES_FOR_TEXT = {"text"}

# Which operators work on which field types.
_OPS_BY_FIELD_TYPE: dict[str, set[str]] = {
    "price": set(NUMERIC_OPS) | set(PRESENCE_OPS) | set(FIELD_CHANGE_OPS),
    "int": set(NUMERIC_OPS) | set(PRESENCE_OPS) | set(FIELD_CHANGE_OPS),
    "date": set(NUMERIC_OPS) | set(PRESENCE_OPS) | {"changed"},
    "text": set(TEXT_OPS) | set(PRESENCE_OPS) | {"changed"},
    "url": set(TEXT_OPS) | set(PRESENCE_OPS) | {"changed"},
    "stock": set(STOCK_OPS) | set(PRESENCE_OPS) | {"changed"},
}

_SPINE_PATTERNS = (
    ("fetch_page", "extract_list"),
    ("fetch_page", "paginate", "extract_list"),
    ("for_each",),
)
_AFTER_CHECK_TYPES = {"save_records", "condition", "for_each", "wait", "alert", "results"}
_TERMINAL_TYPES = {"alert", "results"}

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_UNION_TAGS = {"VarRef", "str", "int", "float", "bool", "list", "literal", "none"}


def validate_flow(raw: Any, for_publish: bool = False, draft: bool = False) -> list[Issue]:
    return parse_flow(raw, for_publish=for_publish, draft=draft)[1]


def parse_flow(raw: Any, for_publish: bool = False, draft: bool = False) -> tuple[dict | None, list[Issue]]:
    """Validate and return the NORMALISED flow (what must be stored), or None and the issues.

    Normalisation is what the models do while validating: whitespace trimmed, url_list
    de-duplicated, numbers in variables made canonical, defaults filled in, the identity
    field marked required. Always store this result, never the raw input, so what is saved
    is exactly what was validated.
    """
    try:
        flow = Flow.model_validate(raw)
    except ValidationError as exc:
        if not draft:
            return None, _schema_issues(exc, raw)
        return _parse_incomplete_draft(exc, raw)
    issues = _GraphChecker(flow, for_publish=for_publish and not draft, draft=draft).run()
    if issues:
        return None, issues
    return flow.model_dump(mode="json", exclude_none=True), []


# ---------------------------------------------------------------------------
# Drafts with unfilled settings
# ---------------------------------------------------------------------------
# A step dropped on the canvas starts empty ("url": "", "fields": []). A draft must be savable
# in that state, but must still never contain anything WRONG (unknown keys, a bad selector, a
# file:// URL, template text). So: errors that only mean "not filled in yet" are tolerated in a
# draft; every other error is still refused. Dry run and publish require everything.

_NODE_CLASSES: dict[str, type] = {
    get_args(cls.model_fields["type"].annotation)[0]: cls for cls in get_args(get_args(FlowNode)[0])
}


def _is_incomplete(err: Any) -> bool:
    if err["type"] in ("missing", "incomplete"):
        return True
    value = err.get("input")
    if isinstance(value, str):
        return not value.strip()
    return isinstance(value, list | dict) and not value


def _incomplete_node_indexes(errors: list[Any], raw: Any) -> set[int] | None:
    """Indexes of nodes whose ONLY errors are unfilled config fields; None if any error is real."""
    nodes = raw.get("nodes") if isinstance(raw, dict) else None
    indexes: set[int] = set()
    for err in errors:
        loc = err["loc"]
        if not (_is_incomplete(err) and isinstance(nodes, list) and len(loc) >= 4 and loc[0] == "nodes"
                and isinstance(loc[1], int) and loc[1] < len(nodes) and isinstance(nodes[loc[1]], dict)
                and loc[2] == nodes[loc[1]].get("type") and loc[3] == "config"):
            return None
        indexes.add(loc[1])
    return indexes


def _parse_incomplete_draft(exc: ValidationError, raw: Any) -> tuple[dict | None, list[Issue]]:
    indexes = _incomplete_node_indexes(exc.errors(), raw)
    if indexes is None:  # at least one real error: report only the real ones
        return None, _schema_issues(exc, raw, drop_incomplete=True)

    raw_nodes = raw["nodes"]
    complete = {**raw, "nodes": [n for i, n in enumerate(raw_nodes) if i not in indexes]}
    try:
        flow = Flow.model_validate(complete)
    except ValidationError as again:  # cannot happen if the classification above is right
        return None, _schema_issues(again, complete)

    stubs: dict[int, Any] = {}
    for i in indexes:
        node = raw_nodes[i]
        try:
            base = NodeBase.model_validate({k: node[k] for k in ("id", "parentId", "position") if k in node})
        except ValidationError as bad:
            return None, _schema_issues(bad, {"nodes": [node]})
        cls = _NODE_CLASSES[node["type"]]
        stubs[i] = cls.model_construct(**dict(base), type=node["type"], config=None)  # config unchecked yet

    parsed = iter(flow.nodes)
    merged = [stubs[i] if i in stubs else next(parsed) for i in range(len(raw_nodes))]
    issues = _GraphChecker(flow.model_copy(update={"nodes": merged}), for_publish=False, draft=True).run()
    if issues:
        return None, issues

    out = flow.model_dump(mode="json", exclude_none=True)
    dumped = iter(out["nodes"])
    out["nodes"] = [
        {**copy.deepcopy(raw_nodes[i]), "config": copy.deepcopy(raw_nodes[i].get("config") or {})}
        if i in indexes else next(dumped)
        for i in range(len(raw_nodes))
    ]
    return out, []


# ---------------------------------------------------------------------------
# Schema errors -> C2 issues
# ---------------------------------------------------------------------------
def _schema_issues(exc: ValidationError, raw: Any, drop_incomplete: bool = False) -> list[Issue]:
    nodes = raw.get("nodes") if isinstance(raw, dict) else None
    edges = raw.get("edges") if isinstance(raw, dict) else None
    variables = raw.get("variables") if isinstance(raw, dict) else None
    issues: list[Issue] = []
    seen: set[tuple[Any, str]] = set()

    for err in exc.errors():
        if drop_incomplete and _is_incomplete(err):
            continue
        loc = list(err["loc"])
        node_id = None
        prefix = ""
        if len(loc) >= 2 and loc[0] == "nodes" and isinstance(loc[1], int):
            item = nodes[loc[1]] if isinstance(nodes, list) and loc[1] < len(nodes) else None
            node_id = item.get("id") if isinstance(item, dict) else None
            rest = loc[2:]
            if rest and isinstance(item, dict) and rest[0] == item.get("type"):
                rest = rest[1:]  # drop the discriminator tag pydantic adds
            if node_id is None:
                prefix = f"nodes[{loc[1]}]"
        elif len(loc) >= 2 and loc[0] in ("edges", "variables") and isinstance(loc[1], int):
            items = edges if loc[0] == "edges" else variables
            item = items[loc[1]] if isinstance(items, list) and loc[1] < len(items) else None
            key = "id" if loc[0] == "edges" else "name"
            label = item.get(key) if isinstance(item, dict) else None
            prefix = f"{loc[0]}[{label if label else loc[1]}]"
            rest = loc[2:]
        else:
            rest = loc

        path = _format_path(rest, prefix)
        msg = err["msg"].removeprefix("Value error, ")
        if _is_incomplete(err) and err["type"] != "incomplete":
            msg = "This field is required"  # instead of "String should have at least 1 character"
        if (node_id, path) in seen:  # a union field reports once per branch; keep the first
            continue
        seen.add((node_id, path))
        issues.append({"node_id": node_id, "path": path, "message": msg})
    return issues


def _format_path(parts: list[Any], prefix: str = "") -> str:
    out = prefix
    for part in parts:
        if isinstance(part, int):
            out += f"[{part}]"
        elif isinstance(part, str) and _IDENT.match(part) and part not in _UNION_TAGS:
            out += f".{part}" if out else part
    return out


# ---------------------------------------------------------------------------
# Graph rules
# ---------------------------------------------------------------------------
class _GraphChecker:
    def __init__(self, flow: Flow, for_publish: bool, draft: bool) -> None:
        self.flow = flow
        self.for_publish = for_publish
        self.draft = draft
        self.source_loop = None
        self.issues: list[Issue] = []
        self.nodes = {n.id: n for n in flow.nodes}
        self.variables = {v.name: v for v in flow.variables}
        self.out_edges: dict[str, list] = defaultdict(list)
        self.in_edges: dict[str, list] = defaultdict(list)

    def add(self, message: str, node_id: str | None = None, path: str = "") -> None:
        self.issues.append({"node_id": node_id, "path": path, "message": message})

    def run(self) -> list[Issue]:
        if not self._ids_and_references():
            return self.issues
        for e in self.flow.edges:
            self.out_edges[e.source].append(e)
            self.in_edges[e.target].append(e)
        self._counts()
        self._loops_and_walls()
        self._handles()
        if self.issues:
            return self.issues  # structural problems make later checks noisy
        if self._has_cycle():
            self.add("The flow has a cycle. Use a For Each node to repeat steps.")
            return self.issues
        self._variables()
        if self.draft:
            return self.issues
        self._loop_handles_present()
        if self.issues:
            return self.issues
        self._spine_and_reachability()
        self._fields_and_rules()
        if self.for_publish:
            for n in self.flow.nodes:
                if n.type in BROWSER_NODE_TYPES:
                    self.add("This node needs a browser, which is not supported yet. Remove it to publish.",
                             n.id)
        return self.issues

    # -- ids, references, counts -------------------------------------------
    def _ids_and_references(self) -> bool:
        ok = True
        for kind, ids in (("node", [n.id for n in self.flow.nodes]), ("edge", [e.id for e in self.flow.edges])):
            dupes = sorted({i for i in ids if ids.count(i) > 1})
            for d in dupes:
                self.add(f"Duplicate {kind} id {d!r}", d if kind == "node" else None)
                ok = False
        var_names = [v.name for v in self.flow.variables]
        for d in sorted({n for n in var_names if var_names.count(n) > 1}):
            self.add(f"Duplicate variable name {d!r}", path=f"variables[{d}]")
            ok = False
        node_ids = {n.id for n in self.flow.nodes}
        for e in self.flow.edges:
            for end in (e.source, e.target):
                if end not in node_ids:
                    self.add(f"Edge {e.id!r} points to a missing node {end!r}", path=f"edges[{e.id}]")
                    ok = False
            if e.source == e.target:
                self.add(f"Edge {e.id!r} connects a node to itself", e.source)
                ok = False
        seen_links: dict[tuple, str] = {}
        for e in self.flow.edges:
            link = (e.source, e.sourceHandle, e.target, e.targetHandle)
            if link in seen_links:
                self.add(f"Edge {e.id!r} duplicates edge {seen_links[link]!r}", e.source, f"edges[{e.id}]")
                ok = False
            seen_links.setdefault(link, e.id)
        for n in self.flow.nodes:
            if n.parentId is not None and n.parentId not in node_ids:
                self.add(f"parentId {n.parentId!r} does not exist", n.id, "parentId")
                ok = False
        return ok

    def _counts(self) -> None:
        by_type: dict[str, list] = defaultdict(list)
        for n in self.flow.nodes:
            by_type[n.type].append(n)
        for node_type, label in (("trigger", "Trigger"), ("check_page", "Check Page")):
            count = len(by_type[node_type])
            if count > 1 or (count == 0 and not self.draft):
                self.add(f"A flow needs exactly one {label} node (found {count})")
        datasets = [n.config.dataset for n in by_type["save_records"] if n.config is not None]
        for d in sorted({x for x in datasets if datasets.count(x) > 1}):
            self.add(f"Two Save Records nodes use the dataset {d!r}; dataset names must be unique")

    # -- loops ---------------------------------------------------------------
    def _loops_and_walls(self) -> None:
        for n in self.flow.nodes:
            if n.parentId is None:
                continue
            parent = self.nodes[n.parentId]
            if parent.type != "for_each":
                self.add("Only a For Each node can contain other nodes", n.id, "parentId")
            elif n.type == "for_each":
                self.add("Loops can't be nested", n.id, "parentId")
            elif n.type not in LOOP_BODY_TYPES:
                allowed = ", ".join(sorted(LOOP_BODY_TYPES))
                self.add(f"{n.type} can't be inside a loop (allowed: {allowed})", n.id, "parentId")

    def _loop_handles_present(self) -> None:
        for n in self.flow.nodes:
            if n.type == "for_each" and n.parentId is None:
                outs = self.out_edges[n.id]
                if not any(e.sourceHandle == "item" for e in outs):
                    self.add("For Each needs an edge from its 'item' handle into the loop body", n.id)
                if not any(e.targetHandle == "next" for e in self.in_edges[n.id]):
                    self.add("For Each needs an edge from the loop body back to its 'next' handle", n.id)
                # Every node in the body must be reachable from the 'item' handle, or it never runs.
                reached: set[str] = set()
                stack = [e.target for e in outs if e.sourceHandle == "item"]
                while stack:
                    current = stack.pop()
                    if current in reached:
                        continue
                    reached.add(current)
                    stack.extend(e.target for e in self.out_edges[current] if e.targetHandle != "next")
                for child in self.flow.nodes:
                    if child.parentId == n.id and child.id not in reached:
                        self.add("This node is inside the loop but not connected to its 'item' handle", child.id)

    # -- handles and loop walls ---------------------------------------------
    def _handles(self) -> None:
        for e in self.flow.edges:
            src, tgt = self.nodes[e.source], self.nodes[e.target]
            where = f"edges[{e.id}]"
            # source handles
            if src.type == "condition":
                if e.sourceHandle not in ("true", "false"):
                    self.add("Edges from a Condition must use the 'true' or 'false' handle", src.id, where)
            elif src.type == "for_each":
                if e.sourceHandle not in ("item", "done"):
                    self.add("Edges from a For Each must use the 'item' or 'done' handle", src.id, where)
            elif e.sourceHandle is not None:
                self.add(f"{src.type} has no {e.sourceHandle!r} handle", src.id, where)
            if src.type in _TERMINAL_TYPES:
                self.add(f"{src.type} is an output node and can't have outgoing edges", src.id, where)
            # target handle
            if e.targetHandle == "next" and tgt.type != "for_each":
                self.add("Only a For Each node has a 'next' handle", tgt.id, where)
            # loop walls: edges stay on one side, except item (in) and next (out)
            if e.sourceHandle == "item":
                if tgt.parentId != src.id:
                    self.add("The 'item' handle must connect to a node inside the same loop", src.id, where)
            elif e.targetHandle == "next":
                if src.parentId != tgt.id:
                    self.add("Only nodes inside this loop can connect to its 'next' handle", src.id, where)
            elif src.parentId != tgt.parentId:
                self.add("Edges can't cross a loop's wall except through 'item', 'next' and 'done'",
                         src.id, where)
            if e.sourceHandle == "done" and tgt.parentId == src.id:
                self.add("The 'done' handle must connect to a node outside the loop", src.id, where)

    # -- cycles (edges into a loop's 'next' handle close the loop and are excluded) --
    def _has_cycle(self) -> bool:
        indeg = {nid: 0 for nid in self.nodes}
        adj: dict[str, list[str]] = defaultdict(list)
        for e in self.flow.edges:
            if e.targetHandle == "next":
                continue
            adj[e.source].append(e.target)
            indeg[e.target] += 1
        queue = deque(n for n, d in indeg.items() if d == 0)
        seen = 0
        while queue:
            n = queue.popleft()
            seen += 1
            for m in adj[n]:
                indeg[m] -= 1
                if indeg[m] == 0:
                    queue.append(m)
        return seen != len(self.nodes)

    # -- spine: trigger -> source -> check_page, then branches --------------
    def _spine_and_reachability(self) -> None:
        trigger = next(n for n in self.flow.nodes if n.type == "trigger")
        check = next(n for n in self.flow.nodes if n.type == "check_page")
        if trigger.parentId or check.parentId:
            self.add("Trigger and Check Page can't be inside a loop")
            return

        chain: list = []
        current = trigger
        while True:
            outs = [e for e in self.out_edges[current.id] if e.sourceHandle != "item"]
            if len(outs) != 1:
                self.add("Each step before Check Page must lead to exactly one next step", current.id)
                return
            nxt = self.nodes[outs[0].target]
            if nxt.id == check.id:
                break
            if len(self.in_edges[nxt.id]) - sum(1 for e in self.in_edges[nxt.id] if e.targetHandle) != 1:
                self.add("Steps before Check Page can't be merged from several branches", nxt.id)
                return
            chain.append(nxt)
            current = nxt
            if len(chain) > 3:
                break

        types = tuple(n.type for n in chain)
        if types not in _SPINE_PATTERNS:
            self.add(
                "The flow must start: Trigger → Fetch Page → (Paginate) → Extract List → Check Page, "
                "or Trigger → For Each over a URL list → Check Page",
                chain[0].id if chain else trigger.id,
            )
            return
        self.spine_ids = {trigger.id, check.id, *(n.id for n in chain)}
        self.source_loop = chain[0] if types == ("for_each",) else None
        if self.source_loop is not None:
            src = self.source_loop.config.source
            var = self.variables.get(src.var) if isinstance(src, VarRef) else None
            if var is None or var.type != "url_list":
                self.add("A For Each at the start of a flow must loop over a url_list variable",
                         self.source_loop.id, "config.source")
            body_types = {n.type for n in self.flow.nodes if n.parentId == self.source_loop.id}
            if not {"fetch_item_page", "extract_fields"} <= body_types:
                self.add("This loop needs a Fetch Item Page and an Extract Fields node inside it",
                         self.source_loop.id)

        # Everything else must hang off Check Page (or sit inside a loop).
        after = self._descendants(check.id)
        for n in self.flow.nodes:
            if n.id in self.spine_ids or n.parentId is not None:
                continue
            if n.id not in after:
                self.add("This node is not connected after Check Page", n.id)
            elif n.type not in _AFTER_CHECK_TYPES and n.type not in BROWSER_NODE_TYPES:
                self.add(f"{n.type} can't come after Check Page", n.id)
        for n in self.flow.nodes:
            if n.parentId is not None and n.parentId not in self.spine_ids and n.parentId not in after:
                self.add("This loop is not connected after Check Page", n.parentId)
            if n.type == "for_each" and n.id in after and n.config.source != "items":
                self.add("A For Each after Check Page loops over the items ('source': 'items')",
                         n.id, "config.source")

    def _descendants(self, start: str) -> set[str]:
        seen: set[str] = set()
        stack = [start]
        while stack:
            for e in self.out_edges[stack.pop()]:
                if e.target not in seen and e.targetHandle != "next":
                    seen.add(e.target)
                    stack.append(e.target)
        return seen

    def _ancestors(self, start: str) -> set[str]:
        seen: set[str] = set()
        stack = [start]
        while stack:
            node = stack.pop()
            parents = [e.source for e in self.in_edges[node] if e.targetHandle != "next"]
            parent_loop = self.nodes[node].parentId
            if parent_loop:
                parents.append(parent_loop)
            for p in parents:
                if p not in seen:
                    seen.add(p)
                    stack.append(p)
        return seen

    # -- variables -----------------------------------------------------------
    def _check_var(self, ref: Any, allowed: set[str], node_id: str, path: str) -> None:
        if not isinstance(ref, VarRef):
            return
        var = self.variables.get(ref.var)
        if var is None:
            self.add(f"Variable {ref.var!r} does not exist", node_id, path)
        elif var.type not in allowed:
            self.add(f"Variable {ref.var!r} is a {var.type}; this place needs {' or '.join(sorted(allowed))}",
                     node_id, path)

    def _variables(self) -> None:
        for n in self.flow.nodes:
            if n.config is None:  # draft step with settings not filled in yet
                continue
            if n.type == "fetch_page":
                self._check_var(n.config.url, {"url"}, n.id, "config.url")
            elif n.type == "for_each":
                self._check_var(n.config.source, {"url_list", "text_list"}, n.id, "config.source")
            elif n.type == "wait":
                self._check_var(n.config.seconds, {"number"}, n.id, "config.seconds")
            elif n.type == "condition" and self.draft:
                # Field types may not be known yet in a draft; at least refuse list/url/boolean
                # variables in a comparison. Full mode checks the exact type against the field.
                for i, rule in enumerate(n.config.rules):
                    self._check_var(rule.value, _VAR_TYPES_FOR_NUMERIC | _VAR_TYPES_FOR_TEXT, n.id,
                                    f"config.rules[{i}].value")

    # -- fields, identity keys, condition rules ------------------------------
    def _fields_and_rules(self) -> None:
        declared: dict[str, str] = {}
        for n in self.flow.nodes:
            if n.type in ("extract_list", "extract_fields"):
                for f in n.config.fields:
                    if declared.get(f.name, f.type) != f.type:
                        self.add(f"Field {f.name!r} is declared with two different types", n.id)
                    declared[f.name] = f.type

        for n in self.flow.nodes:
            if n.type not in ("fetch_item_page", "save_records", "condition"):
                continue
            fields = self._fields_available_at(n)
            if n.type == "fetch_item_page":
                if fields.get(n.config.url_field) != "url":
                    self.add(f"url_field {n.config.url_field!r} must be a url field extracted before this step",
                             n.id, "config.url_field")
            elif n.type == "save_records":
                key = n.config.identity_key
                if key is not None and key not in fields:
                    self.add(f"identity_key {key!r} is not extracted before this step", n.id, "config.identity_key")
                if key is None and self.source_loop is not None:
                    self.add("Set identity_key (usually 'url') when tracking a list of links",
                             n.id, "config.identity_key")
                for i, name in enumerate(n.config.track_fields):
                    if name not in fields:
                        self.add(f"track_fields: {name!r} is not an extracted field before this step", n.id,
                                 f"config.track_fields[{i}]")
            else:
                self._check_rules(n, fields)

    def _fields_available_at(self, node: Any) -> dict[str, str]:
        """Fields extracted UPSTREAM of this node (a rule can't use a field extracted later)."""
        fields: dict[str, str] = {}
        ancestors = self._ancestors(node.id)
        for a_id in ancestors:
            a = self.nodes[a_id]
            sources = [a]
            if a.type == "for_each" and node.parentId != a.id:
                # Reached through 'done': everything the loop body extracted is available.
                sources += [c for c in self.flow.nodes if c.parentId == a.id]
            for s in sources:
                if s.type in ("extract_list", "extract_fields"):
                    fields.update({f.name: f.type for f in s.config.fields})
        loop = self.source_loop
        if loop is not None and (loop.id in ancestors or node.parentId == loop.id):
            fields.setdefault("url", "url")  # each item of a URL-list loop starts as {"url": ...}
        return fields

    def _check_rules(self, node: Any, fields: dict[str, str]) -> None:
        has_history = any(self.nodes[a].type == "save_records" for a in self._ancestors(node.id))
        for i, rule in enumerate(node.config.rules):
            path = f"config.rules[{i}]"
            if rule.op in OPS_NEEDING_HISTORY and not has_history:
                self.add(f"{rule.op!r} compares with earlier runs; put a Save Records node before this "
                         "condition", node.id, path)
            if rule.field == "change":
                continue
            ftype = fields.get(rule.field)
            if ftype is None:
                self.add(f"Field {rule.field!r} is not extracted before this step", node.id, f"{path}.field")
                continue
            if rule.op not in _OPS_BY_FIELD_TYPE[ftype]:
                self.add(f"Operator {rule.op!r} can't be used on a {ftype} field", node.id, f"{path}.op")
                continue
            value = rule.value
            if value is None:
                continue
            numeric = rule.op in NUMERIC_OPS and ftype in ("price", "int") or rule.op.endswith("_pct_gt")
            if isinstance(value, VarRef):
                allowed = _VAR_TYPES_FOR_NUMERIC if numeric else _VAR_TYPES_FOR_TEXT
                if ftype == "date":
                    allowed = _VAR_TYPES_FOR_TEXT
                self._check_var(value, allowed, node.id, f"{path}.value")
            elif numeric:
                if not _is_plain_number(value):
                    self.add(f"{rule.op!r} on {rule.field!r} needs a number like 200 or 99.5", node.id,
                             f"{path}.value")
            elif ftype == "date":
                if not _is_iso_date(value):
                    self.add(f"{rule.op!r} on {rule.field!r} needs a date like 2026-11-10", node.id,
                             f"{path}.value")
            elif not isinstance(value, str):
                self.add(f"{rule.op!r} on {rule.field!r} needs text", node.id, f"{path}.value")


_PLAIN_NUMBER = re.compile(r"^-?\d{1,15}(\.\d{1,6})?$")


def _is_plain_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int | float):
        return True  # the schema already refused NaN / Infinity
    return isinstance(value, str) and bool(_PLAIN_NUMBER.match(value))


def _is_iso_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True
