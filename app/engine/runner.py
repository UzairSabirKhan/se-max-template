"""The runner (A13; FR-13, FR-16, FR-17, FR-22, FR-24, FR-26): executes a flow, with NO AI.

    report = await run_flow(flow, flow_id, db, RunOptions(trigger="manual", fetch=...))

1. Source: fetch_page (+ paginate, max 5 pages) -> extract_list, or a for_each loop over a url_list
   variable whose body fetches and reads each page. Every page goes through safe_fetch.
2. check_page: the page-health verdict (classify.py). BLOCKED / UNSUPPORTED / BROKEN stop the run here:
   nothing after it runs and nothing is stored.
3. The rest of the graph, in dependency order: save_records labels items against stored records,
   conditions route items to true / false, loops run their body once per item (in order, one at a time),
   alerts and result tables collect what reaches them.
4. One verdict, one report (contract C3 RunReport). For real runs, records, alerts and results are written
   in one transaction (app/db/runs.py). A dry run writes only its run row.

Bounded: 120 s per run, paginate <= 5 pages, loops <= 25 items, no cycles (the schema forbids them).
`ai_calls` is always 0: this module never imports app.ai (tests/engine/test_zero_ai.py checks it).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.db.runs import DatasetWrite, RunRepo, RunWrite, new_id
from app.db.session import Database
from app.engine import alerts as alert_builder
from app.engine.classify import FieldInfo, LastGood, PageFact, check_page
from app.engine.conditions import matches
from app.engine.extract import Item, block_marker, extract_fields, extract_list, has_anchor, is_app_shell, next_page_url
from app.engine.fetcher import FetchError, FetchOptions, safe_fetch
from app.engine.records import Labelled, diff_records
from app.flow.schema import Flow, VarRef

log = logging.getLogger("scrapeonce.runner")

Emit = Callable[[str, dict[str, Any]], Awaitable[None]]
RUN_DEADLINE_S = 120.0
MAX_REPORT_ITEMS = 200
VERDICT_RANK = {"OK": 0, "CHANGED": 1, "SUSPECT": 2}


async def _no_emit(event: str, data: dict[str, Any]) -> None:
    return None


@dataclass
class RunOptions:
    trigger: str                                   # schedule | manual | dry_run
    fetch: FetchOptions = field(default_factory=FetchOptions)
    published_hash: str | None = None
    emit: Emit = _no_emit
    deadline_s: float = RUN_DEADLINE_S
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    run_id: str | None = None


class _Stop(Exception):
    """End the run early with this verdict (nothing after this point runs, nothing is stored)."""

    def __init__(self, verdict: str, reason: str, evidence: list[str] | None = None) -> None:
        super().__init__(reason)
        self.verdict, self.reason, self.evidence = verdict, reason, evidence or [reason]


@dataclass
class _Ctx:
    flow: Flow
    flow_id: str
    opts: RunOptions
    variables: dict[str, Any]
    nodes: dict[str, Any]
    out: dict[str, list[Any]]
    pages: list[PageFact] = field(default_factory=list)
    trace: dict[str, dict[str, Any]] = field(default_factory=dict)
    iterations: list[dict[str, Any]] = field(default_factory=list)
    field_types: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    async def node(self, node_id: str, items_in: int, items_out: int, status: str = "ok", note: str | None = None):
        entry = {"node_id": node_id, "items_in": items_in, "items_out": items_out, "status": status}
        if note:
            entry["note"] = note
        self.trace[node_id] = entry
        await self.opts.emit("node_finished", entry)


def _value(ref: Any, variables: dict[str, Any]) -> Any:
    return variables.get(ref.var) if isinstance(ref, VarRef) else ref


# ---------------------------------------------------------------------------
# Fetching one page into a PageFact (+ its HTML when usable)
# ---------------------------------------------------------------------------
async def _fetch(ctx: _Ctx, url: str, anchor: str | None = None) -> tuple[PageFact, str | None, str]:
    try:
        res = await safe_fetch(url, ctx.opts.fetch)
    except FetchError as exc:
        fact = PageFact(url=url, error=exc.reason, error_kind=exc.kind)
        ctx.pages.append(fact)
        return fact, None, url
    usable = res.status < 400
    fact = PageFact(url=res.final_url, status=res.status, body_size=res.body_size,
                    challenge=res.headers.get("cf-mitigated", "").lower() == "challenge",
                    marker=block_marker(res.text) if usable else None,
                    shell=is_app_shell(res.text) if usable else False,
                    anchor=has_anchor(res.text, anchor) if usable else None)
    ctx.pages.append(fact)
    return fact, (res.text if usable else None), res.final_url


# ---------------------------------------------------------------------------
# Loop bodies: one item at a time
# ---------------------------------------------------------------------------
async def _run_body(ctx: _Ctx, loop: Any, entry: Labelled, index: int) -> bool:
    """Run the loop body for one item. True if the item reached the loop's `next` handle (kept)."""
    html: str | None = None
    page_url = ""
    kept = False
    status = "dropped"
    frontier = [e.target for e in ctx.out[loop.id] if e.sourceHandle == "item"]
    visited: set[str] = set()
    while frontier:
        node_id = frontier.pop(0)
        if node_id in visited:
            continue
        visited.add(node_id)
        node = ctx.nodes[node_id]
        handle = None
        if node.type == "fetch_item_page":
            url = entry.item.data.get(node.config.url_field)
            fact, html, page_url = await _fetch(ctx, str(url)) if url else (None, None, "")
            if html is None:
                reason = (fact.error or f"HTTP {fact.status}") if fact else f"no {node.config.url_field} to open"
                if loop.config.on_error == "stop":
                    raise _Stop("BROKEN", f"Stopped: {url or 'an item'} could not be read ({reason})")
                entry.item.error = reason
                status = "error"
                kept = True  # kept with the fields it had; check_page counts failed pages
                break
        elif node.type == "extract_fields":
            data, field_status = extract_fields(html or "", page_url, node.config.fields)
            entry.item.data.update(data)
            entry.item.status.update(field_status)
        elif node.type == "condition":
            handle = "true" if matches(node.config.rules, node.config.match, entry, ctx.variables,
                                       ctx.field_types) else "false"
        elif node.type == "wait":
            if ctx.opts.trigger != "dry_run":
                await ctx.opts.sleep(float(_value(node.config.seconds, ctx.variables)))
        for e in ctx.out[node_id]:
            if handle is not None and e.sourceHandle != handle:
                continue
            if e.targetHandle == "next" and e.target == loop.id:
                kept, status = True, "ok"
            else:
                frontier.append(e.target)
    record = {"node_id": loop.id, "index": index, "key": entry.item.key, "status": status}
    if entry.item.error:
        record["error"] = entry.item.error
    ctx.iterations.append(record)
    await ctx.opts.emit("iteration", record)
    return kept


async def _run_loop(ctx: _Ctx, loop: Any, entries: list[Labelled]) -> list[Labelled]:
    limit = loop.config.max_items
    head, tail = entries[:limit], entries[limit:]
    if tail:
        ctx.notes.append(f"Loop limited to {limit} of {len(entries)} items")
    kept = [e for i, e in enumerate(head) if await _run_body(ctx, loop, e, i)]
    errors = sum(1 for e in head if e.item.error)
    if head and errors / len(head) >= 0.5:
        raise _Stop("BROKEN", f"{errors} of {len(head)} item pages could not be read")
    await ctx.node(loop.id, len(entries), len(kept) + len(tail),
                   note=f"limited to {limit} of {len(entries)} items" if tail else None)
    return kept + tail  # items past the limit pass through untouched


# ---------------------------------------------------------------------------
# The source: everything between the trigger and check_page
# ---------------------------------------------------------------------------
async def _source(ctx: _Ctx) -> tuple[list[Labelled], dict[str, FieldInfo], Any, Any]:
    trigger = next(n for n in ctx.flow.nodes if n.type == "trigger")
    first = ctx.nodes[next(e.target for e in ctx.out[trigger.id])]
    await ctx.node(trigger.id, 0, 0)

    if first.type == "fetch_page":
        chain = [first]
        while chain[-1].type != "extract_list":
            chain.append(ctx.nodes[next(e.target for e in ctx.out[chain[-1].id])])
        paginate = next((n for n in chain if n.type == "paginate"), None)
        extract = chain[-1]
        anchor = extract.config.page_anchor
        url = str(_value(first.config.url, ctx.variables))
        fact, html, final = await _fetch(ctx, url, anchor)
        documents = [(html, final)] if html else []
        await ctx.node(first.id, 0, 1 if html else 0, "ok" if html else "error", fact.error)
        if paginate and html:
            seen = {final}
            for _ in range(paginate.config.max_pages - 1):
                nxt = next_page_url(html, final, paginate.config.next_selector)
                if not nxt or nxt in seen:
                    break
                seen.add(nxt)
                fact, html, final = await _fetch(ctx, nxt, anchor)
                if not html:
                    break
                documents.append((html, final))
            await ctx.node(paginate.id, 1, len(documents))
        items = [Labelled(item, "?") for html, base in documents for item in extract_list(html, base, extract.config)]
        await ctx.node(extract.id, len(documents), len(items))
        fields = {f.name: FieldInfo(f.type, f.required) for f in extract.config.fields}
        return items, fields, extract.config.expected_count, extract.config.identity_key

    # for_each over a url_list variable: one item per link, its body reads the page
    loop = first
    urls = list(_value(loop.config.source, ctx.variables) or [])
    entries = [Labelled(Item(data={"url": u}, status={"url": "ok"}, key=u, source=u), "?") for u in urls]
    fields = {"url": FieldInfo("url", True)}
    for child in ctx.flow.nodes:
        if child.parentId == loop.id and child.type == "extract_fields":
            fields.update({f.name: FieldInfo(f.type, f.required) for f in child.config.fields})
    ctx.field_types.update({k: v.type for k, v in fields.items()})
    items = await _run_loop(ctx, loop, entries)
    return items, fields, None, "url"


# ---------------------------------------------------------------------------
# After check_page: the branches
# ---------------------------------------------------------------------------
def _topological(ctx: _Ctx, start: str) -> list[str]:
    reach: set[str] = set()
    stack = [start]
    while stack:
        for e in ctx.out[stack.pop()]:
            if e.target not in reach and e.targetHandle != "next" and ctx.nodes[e.target].parentId is None:
                reach.add(e.target)
                stack.append(e.target)
    indeg = {n: 0 for n in reach}
    for n in reach:
        for e in ctx.out[n]:
            if e.target in indeg and e.targetHandle != "next":
                indeg[e.target] += 1
    order, ready = [], [n for n, d in indeg.items() if d == 0]
    while ready:
        n = ready.pop(0)
        order.append(n)
        for e in ctx.out[n]:
            if e.target in indeg and e.targetHandle != "next":
                indeg[e.target] -= 1
                if indeg[e.target] == 0:
                    ready.append(e.target)
    return order


def _merge(groups: list[list[Labelled]]) -> list[Labelled]:
    seen: set[int] = set()
    out = []
    for group in groups:
        for x in group:
            if id(x) not in seen:
                seen.add(id(x))
                out.append(x)
    return out


@dataclass
class _Outcome:
    items: list[Labelled]
    verdict: str = "OK"
    reason: str = "Checks passed"
    changes: dict[str, int] = field(default_factory=lambda: {"new": 0, "changed": 0, "removed": 0})
    datasets: list[DatasetWrite] = field(default_factory=list)
    alerts: list[dict[str, Any]] = field(default_factory=list)
    results: list[dict[str, Any]] = field(default_factory=list)
    suspects: list[Labelled] = field(default_factory=list)


async def _branches(ctx: _Ctx, check_id: str, items: list[Labelled], identity: str, fields: dict[str, FieldInfo],
                    repo: RunRepo) -> _Outcome:
    outcome = _Outcome(items=items)
    inbox: dict[str, list[list[Labelled]]] = defaultdict(list)
    for e in ctx.out[check_id]:
        inbox[e.target].append(items)
    baseline = False

    for node_id in _topological(ctx, check_id):
        node = ctx.nodes[node_id]
        incoming = _merge(inbox.get(node_id, []))
        await ctx.opts.emit("node_started", {"node_id": node_id})
        outputs: dict[str | None, list[Labelled]] = {None: incoming}

        if node.type == "save_records":
            cfg = node.config
            key_field = cfg.identity_key or identity
            for x in incoming:
                value = x.item.data.get(key_field)
                x.item.key = str(value) if value not in (None, "") else None
            stored = await repo.stored_records(ctx.flow_id, cfg.dataset)
            diff = diff_records([x.item for x in incoming], stored, cfg.track_fields)
            if diff.verdict == "BROKEN":
                raise _Stop("BROKEN", diff.reason, [diff.reason, *diff.evidence])
            removed = [Labelled(Item(data=dict(stored[k]), key=k, status={}), "removed") for k in diff.removed]
            labelled = diff.labelled + removed
            baseline = baseline or (not stored and not cfg.alert_on_first_run)
            outcome.datasets.append(DatasetWrite(name=cfg.dataset, identity_key=key_field,
                                                 fields={k: v.type for k, v in fields.items()},
                                                 tracked=list(cfg.track_fields), diff=diff))
            outcome.suspects += [x for x in diff.labelled if x.change == "suspect"]
            if VERDICT_RANK.get(diff.verdict, 0) >= VERDICT_RANK.get(outcome.verdict, 0):
                outcome.verdict, outcome.reason = diff.verdict, diff.reason
            if outcome.changes == {"new": 0, "changed": 0, "removed": 0}:
                outcome.changes = diff.counts
            outcome.items = labelled
            outputs = {None: labelled}
        elif node.type == "condition":
            yes = [x for x in incoming if matches(node.config.rules, node.config.match, x, ctx.variables,
                                                   ctx.field_types)]
            no = [x for x in incoming if x not in yes]
            outputs = {"true": yes, "false": no}
        elif node.type == "for_each":
            outputs = {"done": await _run_loop(ctx, node, incoming)}
        elif node.type == "wait":
            if ctx.opts.trigger != "dry_run":
                await ctx.opts.sleep(float(_value(node.config.seconds, ctx.variables)))
        elif node.type == "alert":
            if not baseline:
                outcome.alerts += alert_builder.condition_alerts(ctx.flow_id, node.id, node.config.title,
                                                                 node.config.level, incoming, ctx.field_types)
            outputs = {}
        elif node.type == "results":
            outcome.results.append({"node_id": node.id, "name": node.config.name,
                                    "items": [x.as_report() for x in incoming][:MAX_REPORT_ITEMS]})
            outputs = {}
        else:  # browser steps are refused at publish; in a dry run they are skipped
            await ctx.node(node.id, len(incoming), 0, "skipped", "needs a browser")
            continue

        if node.type != "for_each":
            await ctx.node(node.id, len(incoming), sum(len(v) for v in outputs.values()),
                           note="first run: alerts skipped, starting point saved" if node.type == "alert" and baseline
                           else None)
        for e in ctx.out[node_id]:
            if e.targetHandle == "next":
                continue
            handle = e.sourceHandle if node.type in ("condition", "for_each") else None
            inbox[e.target].append(outputs.get(handle, []))
    return outcome


# ---------------------------------------------------------------------------
# run_flow
# ---------------------------------------------------------------------------
async def run_flow(flow_dict: dict[str, Any], flow_id: str, db: Database, opts: RunOptions) -> dict[str, Any]:
    flow = Flow.model_validate(flow_dict)
    out: dict[str, list[Any]] = defaultdict(list)
    for e in flow.edges:
        out[e.source].append(e)
    ctx = _Ctx(flow=flow, flow_id=flow_id, opts=opts, variables={v.name: v.value for v in flow.variables},
               nodes={n.id: n for n in flow.nodes}, out=out)
    for n in flow.nodes:
        if n.type in ("extract_list", "extract_fields"):
            ctx.field_types.update({f.name: f.type for f in n.config.fields})
    run_id = opts.run_id or new_id("run")
    started_wall = datetime.now(UTC)
    started = time.monotonic()

    async with db.sessions() as session:
        repo = RunRepo(session)
        last_good: LastGood | None = await repo.last_good(flow_id)
        previous_verdict = await repo.last_verdict(flow_id)

    health = None
    outcome = _Outcome(items=[])
    verdict, reason, evidence = "UNKNOWN", "", []
    try:
        async with asyncio.timeout(opts.deadline_s):
            items, fields, expected, identity = await _source(ctx)
            check = next(n for n in flow.nodes if n.type == "check_page")
            health = check_page(ctx.pages, [x.item for x in items], fields, expected, last_good)
            await ctx.node(check.id, len(items), 0 if health.verdict else len(items),
                           "error" if health.verdict else "ok", health.reason or None)
            if health.verdict:
                raise _Stop(health.verdict, health.reason, health.evidence)
            outcome.items = items
            async with db.sessions() as session:
                outcome = await _branches(ctx, check.id, items, identity, fields, RunRepo(session))
            verdict, reason, evidence = outcome.verdict, outcome.reason, list(health.evidence)
    except _Stop as stop:
        verdict, reason, evidence = stop.verdict, stop.reason, stop.evidence
        outcome.datasets, outcome.alerts, outcome.results = [], [], []
    except TimeoutError:
        verdict, reason = "BLOCKED", f"The run took longer than {int(opts.deadline_s)} s and was stopped (deadline)"
        evidence = [reason]
        outcome.datasets, outcome.alerts, outcome.results = [], [], []
    except Exception:  # never crash the scheduler: unexpected problems become UNKNOWN, nothing stored
        log.exception("Run %s of flow %s failed unexpectedly", run_id, flow_id)
        verdict, reason = "UNKNOWN", "Something unexpected went wrong in this run. Nothing was stored."
        evidence = [reason]
        outcome.datasets, outcome.alerts, outcome.results = [], [], []

    usable = [x for x in (outcome.items or []) if x.change != "removed"]
    report = {
        "id": run_id, "flow_id": flow_id, "trigger": opts.trigger, "verdict": verdict, "reason": reason,
        "started_at": started_wall.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "duration_ms": int((time.monotonic() - started) * 1000),
        "items_found": health.items_found if health else len(usable),
        "items_valid": health.items_valid if health else 0,
        "changes": (outcome.changes if verdict in ("OK", "CHANGED", "SUSPECT")
                    else {"new": 0, "changed": 0, "removed": 0}),
        "ai_calls": 0,
        "evidence": [*evidence, *ctx.notes],
        "http": [p.as_report() for p in ctx.pages][:50],
        "coverage": health.coverage if health else {},
        "node_trace": list(ctx.trace.values()),
        "iterations": ctx.iterations,
        "items": [x.as_report() for x in (outcome.items or [])][:MAX_REPORT_ITEMS],
    }

    write = RunWrite(run_id=run_id, flow_id=flow_id, trigger=opts.trigger, published_hash=opts.published_hash,
                     report=report)
    if opts.trigger != "dry_run":
        if verdict in ("OK", "CHANGED", "SUSPECT"):
            write.datasets, write.results, write.alerts = outcome.datasets, outcome.results, outcome.alerts
        system = alert_builder.system_alert(flow_id, run_id, verdict, reason, opts.published_hash, previous_verdict,
                                            outcome.suspects if verdict == "SUSPECT" else None)
        if system:
            write.alerts = [*write.alerts, system]
    async with db.sessions() as session:
        await RunRepo(session).save_run(write)
    await opts.emit("finished", {k: report[k] for k in ("id", "flow_id", "trigger", "verdict", "reason", "started_at",
                                                        "duration_ms", "items_found", "items_valid", "changes",
                                                        "ai_calls")})
    return report
