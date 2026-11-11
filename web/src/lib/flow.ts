import type { Flow, FlowNode, FlowOp, Issue, NodeType } from "../types/contracts";
import { NODE_META } from "./nodeMeta";

const ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789";
export function newId(prefix = "n_") {
  let s = "";
  for (let i = 0; i < 6; i++) s += ALPHABET[Math.floor(Math.random() * ALPHABET.length)];
  return prefix + s;
}

export const isVarRef = (v: unknown): v is { var: string } => !!v && typeof v === "object" && "var" in (v as object);

export function clone<T>(v: T): T {
  return structuredClone(v);
}

/** Apply agent ops to a flow (C5). Unknown targets are skipped. */
export function applyOps(flow: Flow, ops: FlowOp[]): Flow {
  const f = clone(flow);
  for (const op of ops) {
    switch (op.op) {
      case "add_node":
        if (!f.nodes.some((n) => n.id === op.node.id)) f.nodes.push(clone(op.node));
        break;
      case "update_node": {
        const n = f.nodes.find((x) => x.id === op.id);
        if (n) n.config = clone(op.config);
        break;
      }
      case "remove_node":
        f.nodes = f.nodes.filter((n) => n.id !== op.id && n.parentId !== op.id);
        f.edges = f.edges.filter((e) => e.source !== op.id && e.target !== op.id);
        break;
      case "add_edge":
        if (!f.edges.some((e) => e.id === op.edge.id)) f.edges.push(clone(op.edge));
        break;
      case "remove_edge":
        f.edges = f.edges.filter((e) => e.id !== op.id);
        break;
      case "set_variable": {
        const i = f.variables.findIndex((v) => v.name === op.variable.name);
        if (i >= 0) f.variables[i] = clone(op.variable);
        else f.variables.push(clone(op.variable));
        break;
      }
      case "remove_variable":
        f.variables = f.variables.filter((v) => v.name !== op.name);
        break;
    }
  }
  return f;
}

export type PendingMark = "add" | "change" | "remove";

/** Which nodes / edges each pending op touches, for canvas highlighting. */
export function pendingMarks(ops: FlowOp[]) {
  const nodes: Record<string, PendingMark> = {};
  const edges: Record<string, PendingMark> = {};
  for (const op of ops) {
    if (op.op === "add_node") nodes[op.node.id] = "add";
    if (op.op === "update_node" && nodes[op.id] !== "add") nodes[op.id] = "change";
    if (op.op === "remove_node") nodes[op.id] = "remove";
    if (op.op === "add_edge") edges[op.edge.id] = "add";
    if (op.op === "remove_edge") edges[op.id] = "remove";
  }
  return { nodes, edges };
}

/** Like applyOps, but keeps removed nodes/edges so the canvas can show them struck out. */
export function previewOps(flow: Flow, ops: FlowOp[]): Flow {
  const keepRemovals = ops.filter((o) => o.op !== "remove_node" && o.op !== "remove_edge");
  return applyOps(flow, keepRemovals);
}

export function summarizeOps(ops: FlowOp[]) {
  const c = { added: 0, changed: 0, removed: 0, links: 0, variables: 0 };
  for (const op of ops) {
    if (op.op === "add_node") c.added++;
    else if (op.op === "update_node") c.changed++;
    else if (op.op === "remove_node") c.removed++;
    else if (op.op === "add_edge" || op.op === "remove_edge") c.links++;
    else c.variables++;
  }
  return c;
}

/** Top-level order (Kahn) for step numbers. Loop bodies get numbers after their loop. */
export function stepNumbers(flow: Flow): Record<string, number> {
  const ids = flow.nodes.map((n) => n.id);
  const indeg: Record<string, number> = Object.fromEntries(ids.map((i) => [i, 0]));
  const out: Record<string, string[]> = Object.fromEntries(ids.map((i) => [i, []]));
  for (const e of flow.edges) {
    if (e.targetHandle === "next") continue; // body → loop back-link is not a dependency
    if (!(e.source in out) || !(e.target in indeg)) continue;
    out[e.source].push(e.target);
    indeg[e.target]++;
  }
  const inBody = new Set(flow.nodes.filter((n) => n.parentId).map((n) => n.id));
  // Start from the trigger, so it is always step 1 even when other steps aren't linked yet.
  const isTrigger = new Set(flow.nodes.filter((n) => n.type === "trigger").map((n) => n.id));
  const queue = ids.filter((i) => indeg[i] === 0).sort((a, b) => Number(isTrigger.has(b)) - Number(isTrigger.has(a)));
  const order: string[] = [];
  while (queue.length) {
    const id = queue.shift()!;
    order.push(id);
    // Loop-body steps are numbered before what comes after the loop's "done".
    for (const t of out[id]) if (--indeg[t] === 0) (inBody.has(t) ? queue.unshift(t) : queue.push(t));
  }
  for (const i of ids) if (!order.includes(i)) order.push(i);
  return Object.fromEntries(order.map((id, i) => [id, i + 1]));
}

export function hasCycle(flow: Flow) {
  const indeg: Record<string, number> = Object.fromEntries(flow.nodes.map((x) => [x.id, 0]));
  for (const e of flow.edges) if (e.targetHandle !== "next" && e.target in indeg) indeg[e.target]++;
  const q = Object.keys(indeg).filter((k) => indeg[k] === 0);
  let seen = 0;
  while (q.length) {
    const id = q.shift()!;
    seen++;
    for (const e of flow.edges)
      if (e.source === id && e.targetHandle !== "next" && e.target in indeg && --indeg[e.target] === 0) q.push(e.target);
  }
  return seen !== flow.nodes.length;
}

/** All extracted field names (with types) in the flow, for condition and save forms. */
export function knownFields(flow: Flow): { name: string; type: string }[] {
  const out = new Map<string, string>();
  for (const n of flow.nodes) {
    if (n.type === "extract_list" || n.type === "extract_fields")
      for (const f of n.config.fields ?? []) if (f.name) out.set(f.name, f.type ?? "text");
  }
  if (flow.nodes.some((n) => n.type === "for_each" && isVarRef(n.config.source))) out.set("url", out.get("url") ?? "url");
  return [...out].map(([name, type]) => ({ name, type }));
}

export function flowsEqual(a: Flow | null, b: Flow | null) {
  if (!a || !b) return false;
  const strip = (f: Flow) =>
    JSON.stringify({
      v: f.variables,
      n: [...f.nodes].sort((x, y) => x.id.localeCompare(y.id)).map(({ id, type, parentId, config }) => ({ id, type, parentId, config })),
      e: [...f.edges].sort((x, y) => x.id.localeCompare(y.id)).map(({ source, target, sourceHandle, targetHandle }) => ({ source, target, sourceHandle, targetHandle })),
    });
  return strip(a) === strip(b);
}

/**
 * Light client-side copy of the server's graph rules, used by the mock API only.
 * The real rules live in app/flow (Workstream A); the UI always shows the server's issues.
 */
export function validateFlow(flow: Flow, mode: "save" | "publish"): Issue[] {
  const issues: Issue[] = [];
  const add = (node_id: string | null, path: string, message: string) => issues.push({ node_id, path, message });
  const triggers = flow.nodes.filter((n) => n.type === "trigger");
  if (triggers.length !== 1) add(null, "nodes", `A flow needs exactly one trigger (found ${triggers.length}).`);
  if (flow.nodes.length > 30) add(null, "nodes", "A flow can have at most 30 nodes.");
  if (hasCycle(flow)) add(null, "edges", "These links make a loop. Flows must run top to bottom.");
  if (!flow.nodes.some((n) => n.type === "check_page")) add(null, "nodes", "Check page is required and can't be removed.");
  const datasets = new Set<string>();
  for (const n of flow.nodes) {
    const meta = NODE_META[n.type];
    if (meta.bodyOnly && !n.parentId) add(n.id, "parentId", `${meta.label} only works inside a Loop.`);
    if (n.parentId && !["fetch_item_page", "extract_fields", "condition", "wait"].includes(n.type))
      add(n.id, "parentId", `${meta.label} can't go inside a Loop. Put it after the loop's done output.`);
    if (mode === "save") continue;
    const c = n.config;
    if (meta.disabled) add(n.id, "type", "This step needs a real browser and can't be published yet.");
    switch (n.type) {
      case "fetch_page":
        if (!c.url) add(n.id, "config.url", "Add the page URL.");
        else if (!isVarRef(c.url) && !/^https?:\/\//.test(c.url)) add(n.id, "config.url", "URL must start with http:// or https://");
        break;
      case "extract_list":
        if (!c.base_selector) add(n.id, "config.base_selector", "Add the item selector (the box around one product).");
        if (!(c.fields ?? []).length) add(n.id, "config.fields", "Add at least one field.");
        if (!c.identity_key) add(n.id, "config.identity_key", "Pick which field identifies an item.");
        break;
      case "extract_fields":
        if (!(c.fields ?? []).length) add(n.id, "config.fields", "Add at least one field.");
        break;
      case "save_records":
        if (!c.dataset) add(n.id, "config.dataset", "Name the dataset.");
        else if (datasets.has(c.dataset)) add(n.id, "config.dataset", "Each dataset name must be unique in a flow.");
        datasets.add(c.dataset);
        break;
      case "condition":
        if (!(c.rules ?? []).length) add(n.id, "config.rules", "Add at least one rule.");
        break;
      case "alert":
        if (!c.title) add(n.id, "config.title", "Give the alert a title.");
        break;
    }
    if (n.type === "extract_list" || n.type === "extract_fields")
      (c.fields ?? []).forEach((f: any, i: number) => {
        if (!f.name) add(n.id, `config.fields[${i}].name`, `Field ${i + 1} needs a name.`);
        if (!f.selector) add(n.id, `config.fields[${i}].selector`, `Field “${f.name || i + 1}” needs a selector.`);
        else if (f.selector.length > 200) add(n.id, `config.fields[${i}].selector`, "Selector is longer than 200 characters.");
      });
  }
  return issues;
}

/** Steps that may sit before Check page: they run in one line, with no branches. */
export const BEFORE_CHECK_TYPES: NodeType[] = ["fetch_page", "paginate", "extract_list"];

/** Ids of the top-level steps that lead into Check page (the trigger, the fetch, ...). */
export function beforeCheck(flow: Flow): Set<string> {
  const ids = new Set<string>();
  const check = flow.nodes.find((n) => n.type === "check_page");
  if (!check) return ids;
  const top = new Set(flow.nodes.filter((n) => !n.parentId).map((n) => n.id));
  const stack = [check.id];
  while (stack.length) {
    const id = stack.pop()!;
    for (const e of flow.edges)
      if (e.target === id && top.has(e.source) && e.sourceHandle !== "item" && e.targetHandle !== "next" && !ids.has(e.source)) {
        ids.add(e.source);
        stack.push(e.source);
      }
  }
  return ids;
}

/**
 * The server only checks the line up to Check page when you test or publish; this shows it while
 * you edit: a branch before Check page, a step there that belongs after it, a step that skips it.
 */
export function lineProblems(flow: Flow): Issue[] {
  const line = beforeCheck(flow);
  const check = flow.nodes.find((n) => n.type === "check_page");
  if (!check || !line.size) return [];
  const issues: Issue[] = [];
  const reach = (from: string[]) => {
    const seen = new Set<string>();
    const stack = [...from];
    while (stack.length) {
      const id = stack.pop()!;
      for (const e of flow.edges)
        if (e.source === id && e.sourceHandle !== "item" && e.targetHandle !== "next" && !seen.has(e.target)) {
          seen.add(e.target);
          stack.push(e.target);
        }
    }
    return seen;
  };
  for (const id of line) {
    const n = flow.nodes.find((x) => x.id === id)!;
    if (flow.edges.filter((e) => e.source === id && e.sourceHandle !== "item").length > 1)
      issues.push({ node_id: id, path: "edges", message: "This step leads to two steps. Steps up to Check page run in one line: move the extra step after Check page." });
    if (n.type !== "trigger" && !BEFORE_CHECK_TYPES.includes(n.type))
      issues.push({ node_id: id, path: "type", message: `${NODE_META[n.type].label} goes after Check page, so it only sees checked data.` });
  }
  const afterCheck = reach([check.id]);
  for (const id of reach([...line]))
    if (id !== check.id && !line.has(id) && !afterCheck.has(id))
      issues.push({ node_id: id, path: "edges", message: "This step skips Check page, so it would use data that wasn't checked. Connect it after Check page." });
  return issues;
}

/** Why a step of this type can't go right after `sourceId`, or null if it can. */
export function placementProblem(flow: Flow, sourceId: string, type: NodeType): string | null {
  if (beforeCheck(flow).has(sourceId) && !BEFORE_CHECK_TYPES.includes(type))
    return "Steps that use the data go after Check page, so every run is checked first.";
  return null;
}

export function nodeById(flow: Flow, id: string): FlowNode | undefined {
  return flow.nodes.find((n) => n.id === id);
}
