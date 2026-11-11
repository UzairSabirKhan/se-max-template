import { useMemo } from "react";
import { create } from "zustand";
import { toast } from "../components/ui";
import { applyOps, beforeCheck, clone, lineProblems, newId, placementProblem } from "../lib/flow";
import { autoLayout, needsLayout } from "../lib/layout";
import { NODE_META } from "../lib/nodeMeta";
import type { Flow, FlowDetail, FlowEdge, FlowNode, FlowOp, Issue, NodeType, RunReport, Variable } from "../types/contracts";

export type SaveState = "saved" | "dirty" | "saving" | "invalid" | "conflict" | "error";
export type RightPanel = "agent" | "settings" | "variables";
export type NodeRunState = { state: "running" | "done" | "error"; items_in?: number; items_out?: number };

type State = {
  flowId: string | null;
  name: string;
  status: FlowDetail["status"];
  published: Flow | null;
  publishedAt: string | null;
  draft: Flow;
  /** Bumped on every local edit; autosave compares it to know if newer edits arrived. */
  rev: number;
  savedRev: number;
  saveState: SaveState;
  issues: Issue[];
  selectedId: string | null;
  selectedIds: string[];
  panel: RightPanel;
  pending: FlowOp[];
  /** Last accept/reject of an assistant proposal, so the chat can reflect it. */
  decision: { kind: "accepted" | "rejected"; at: number } | null;
  run: { runId: string; nodes: Record<string, NodeRunState> } | null;
  dryRun: { open: boolean; loading: boolean; report: RunReport | null; error: string | null; untilNode?: string };
  /** Undo / redo stacks of earlier drafts (newest last in `past`, next-to-redo first in `future`). */
  past: Flow[];
  future: Flow[];
};

type Actions = {
  load: (d: FlowDetail) => void;
  applyServer: (d: FlowDetail, sentRev?: number) => void;
  setName: (name: string) => void;
  edit: (fn: (f: Flow) => void) => void;
  updateConfig: (id: string, config: Record<string, any>) => void;
  addNode: (type: NodeType, position: { x: number; y: number }, parentId?: string) => string;
  insertOnEdge: (edgeId: string, type: NodeType) => void;
  appendAfter: (nodeId: string, type: NodeType) => void;
  removeNode: (id: string) => void;
  connect: (e: Omit<FlowEdge, "id">) => void;
  removeEdge: (id: string) => void;
  moveNodes: (moves: { id: string; position: { x: number; y: number } }[]) => void;
  layout: () => void;
  setVariable: (v: Variable, oldName?: string) => void;
  removeVariable: (name: string) => void;
  select: (id: string | null) => void;
  setSelection: (ids: string[]) => void;
  setPanel: (p: RightPanel) => void;
  setIssues: (i: Issue[]) => void;
  setSaveState: (s: SaveState) => void;
  propose: (ops: FlowOp[]) => void;
  acceptPending: () => void;
  rejectPending: () => void;
  discardToPublished: () => void;
  setRun: (r: State["run"]) => void;
  patchRunNode: (id: string, s: NodeRunState) => void;
  setDryRun: (d: Partial<State["dryRun"]>) => void;
  undo: () => void;
  redo: () => void;
};

const emptyFlow: Flow = { version: 0, variables: [], nodes: [], edges: [] };
const HISTORY = 50;
const MERGE_MS = 1000;

export const useEditor = create<State & Actions>((set, get) => {
  /**
   * Every local change goes through here, so autosave notices it and Ctrl+Z can undo it.
   * `key`: edits with the same key within a second merge into one undo step (typing in a setting).
   */
  let lastKey: string | null = null;
  let lastAt = 0;
  const commit = (draft: Flow, extra: Partial<State> = {}, key?: string) =>
    set((s) => {
      const now = Date.now();
      const merge = key !== undefined && key === lastKey && now - lastAt < MERGE_MS;
      lastKey = key ?? null;
      lastAt = now;
      return {
        draft,
        past: merge ? s.past : [...s.past, s.draft].slice(-HISTORY),
        future: [],
        rev: s.rev + 1,
        saveState: s.saveState === "conflict" ? "conflict" : "dirty",
        ...extra,
      };
    });

  /** Put an earlier or later draft back, keeping the server's version number so the save goes through. */
  const restore = (s: State, next: Flow, past: Flow[], future: Flow[]): Partial<State> => {
    lastKey = null;
    const draft = { ...next, version: s.draft.version };
    const keepSelection = draft.nodes.some((n) => n.id === s.selectedId);
    return {
      draft,
      past,
      future,
      rev: s.rev + 1,
      saveState: s.saveState === "conflict" ? "conflict" : "dirty",
      selectedId: keepSelection ? s.selectedId : null,
      panel: !keepSelection && s.panel === "settings" ? "agent" : s.panel,
      issues: s.issues.filter((i) => !i.node_id || draft.nodes.some((n) => n.id === i.node_id)),
    };
  };

  const dropIssuesFor = (id: string) => get().issues.filter((i) => i.node_id !== id);

  return {
    flowId: null,
    name: "",
    status: "draft",
    published: null,
    publishedAt: null,
    draft: emptyFlow,
    rev: 0,
    savedRev: 0,
    saveState: "saved",
    issues: [],
    selectedId: null,
    selectedIds: [],
    panel: "agent",
    pending: [],
    decision: null,
    run: null,
    dryRun: { open: false, loading: false, report: null, error: null },
    past: [],
    future: [],

    load: (d) => {
      const draft = needsLayout(d.draft) ? { ...autoLayout(d.draft).flow, version: d.draft.version } : d.draft;
      set({
        flowId: d.id, name: d.name, status: d.status, published: d.published, publishedAt: d.published_at,
        draft, rev: 0, savedRev: 0, saveState: "saved", issues: [], selectedId: null, selectedIds: [],
        pending: [], run: null, panel: "agent", past: [], future: [],
        dryRun: { open: false, loading: false, report: null, error: null },
      });
    },

    applyServer: (d, sentRev) =>
      set((s) => {
        const upToDate = sentRev === undefined || sentRev === s.rev;
        return {
          name: d.name, status: d.status, published: d.published, publishedAt: d.published_at,
          // Keep local edits made while the save was in flight; only take the new version number.
          draft: { ...s.draft, version: d.draft.version },
          savedRev: sentRev ?? s.rev,
          saveState: upToDate ? "saved" : "dirty",
          issues: s.issues.filter((i) => i.node_id !== null),
        };
      }),

    setName: (name) => set((s) => ({ name, rev: s.rev + 1, saveState: "dirty" })),

    edit: (fn) => {
      const f = clone(get().draft);
      fn(f);
      commit(f);
    },

    updateConfig: (id, config) => {
      const f = clone(get().draft);
      const n = f.nodes.find((x) => x.id === id);
      if (!n) return;
      n.config = config;
      commit(f, { issues: dropIssuesFor(id) }, `config:${id}`);
    },

    addNode: (type, position, parentId) => {
      const f = clone(get().draft);
      const id = newId();
      const node: FlowNode = { id, type, position, config: NODE_META[type].defaultConfig(), ...(parentId ? { parentId } : {}) };
      f.nodes.push(node);
      commit(f, { selectedId: id, panel: "settings" });
      return id;
    },

    insertOnEdge: (edgeId, type) => {
      const f = clone(get().draft);
      const e = f.edges.find((x) => x.id === edgeId);
      if (!e) return;
      const problem = placementProblem(f, e.source, type);
      if (problem) return void toast.info(`${NODE_META[type].label} can't go here`, problem);
      const src = f.nodes.find((n) => n.id === e.source);
      const tgt = f.nodes.find((n) => n.id === e.target);
      const id = newId();
      // A node inserted on an edge between two body nodes lives in the loop too.
      const parentId = src?.parentId && tgt?.parentId === src.parentId ? src.parentId : e.sourceHandle === "item" ? e.source : e.targetHandle === "next" ? e.target : undefined;
      f.nodes.push({ id, type, position: { x: 0, y: 0 }, config: NODE_META[type].defaultConfig(), ...(parentId ? { parentId } : {}) });
      f.edges = f.edges.filter((x) => x.id !== edgeId);
      f.edges.push({ id: newId("e_"), source: e.source, target: id, ...(e.sourceHandle ? { sourceHandle: e.sourceHandle } : {}) });
      f.edges.push({ id: newId("e_"), source: id, target: e.target, ...(type === "condition" ? { sourceHandle: "true" as const } : {}), ...(e.targetHandle ? { targetHandle: e.targetHandle } : {}) });
      commit({ ...autoLayout(f).flow, version: f.version }, { selectedId: id, panel: "settings" });
    },

    appendAfter: (nodeId, type) => {
      const f = clone(get().draft);
      const src = f.nodes.find((n) => n.id === nodeId);
      if (!src) return;
      const problem = placementProblem(f, nodeId, type);
      if (problem) return void toast.info(`${NODE_META[type].label} can't go here`, problem);
      // Before Check page the steps run in one line: add in between instead of starting a branch.
      const next = beforeCheck(f).has(nodeId) && f.edges.find((e) => e.source === nodeId);
      if (next) return get().insertOnEdge(next.id, type);
      const id = newId();
      f.nodes.push({ id, type, position: { x: 0, y: 0 }, config: NODE_META[type].defaultConfig(), ...(src.parentId ? { parentId: src.parentId } : {}) });
      f.edges.push({ id: newId("e_"), source: nodeId, target: id, ...(src.type === "condition" ? { sourceHandle: "true" as const } : src.type === "for_each" ? { sourceHandle: "done" as const } : {}) });
      commit({ ...autoLayout(f).flow, version: f.version }, { selectedId: id, panel: "settings" });
    },

    removeNode: (id) => {
      const f = clone(get().draft);
      const n = f.nodes.find((x) => x.id === id);
      if (!n || n.type === "check_page" || n.type === "trigger") return;
      // Re-link a simple chain: one in, one out → connect them.
      const ins = f.edges.filter((e) => e.target === id);
      const outs = f.edges.filter((e) => e.source === id);
      f.nodes = f.nodes.filter((x) => x.id !== id && x.parentId !== id);
      const gone = new Set([id, ...get().draft.nodes.filter((x) => x.parentId === id).map((x) => x.id)]);
      f.edges = f.edges.filter((e) => !gone.has(e.source) && !gone.has(e.target));
      if (ins.length === 1 && outs.length === 1 && !gone.has(ins[0].source) && !gone.has(outs[0].target))
        f.edges.push({ id: newId("e_"), source: ins[0].source, target: outs[0].target, ...(ins[0].sourceHandle ? { sourceHandle: ins[0].sourceHandle } : {}), ...(outs[0].targetHandle ? { targetHandle: outs[0].targetHandle } : {}) });
      commit(f, { selectedId: get().selectedId === id ? null : get().selectedId, issues: dropIssuesFor(id), panel: get().panel === "settings" && get().selectedId === id ? "agent" : get().panel });
    },

    connect: (e) => {
      const f = clone(get().draft);
      if (f.edges.some((x) => x.source === e.source && x.target === e.target && x.sourceHandle === e.sourceHandle)) return;
      const line = beforeCheck(f);
      const check = f.nodes.find((n) => n.type === "check_page");
      const intoLine = e.target === check?.id || line.has(e.target);
      const branches = e.sourceHandle !== "item" && f.edges.some((x) => x.source === e.source && x.sourceHandle !== "item");
      if ((line.has(e.source) && branches) || (intoLine && f.edges.some((x) => x.target === e.target && !x.targetHandle)))
        return void toast.info("No branches before Check page", "The steps up to Check page run in one line. Add other steps after it.");
      f.edges.push({ id: newId("e_"), ...e });
      commit(f);
    },

    removeEdge: (id) => {
      const f = clone(get().draft);
      f.edges = f.edges.filter((e) => e.id !== id);
      commit(f);
    },

    moveNodes: (moves) => {
      const f = clone(get().draft);
      for (const m of moves) {
        const n = f.nodes.find((x) => x.id === m.id);
        if (n) n.position = m.position;
      }
      commit(f);
    },

    layout: () => {
      const d = get().draft;
      commit({ ...autoLayout(d).flow, version: d.version });
    },

    setVariable: (v, oldName) => {
      const f = clone(get().draft);
      const i = f.variables.findIndex((x) => x.name === (oldName ?? v.name));
      if (i >= 0) f.variables[i] = v;
      else f.variables.push(v);
      if (oldName && oldName !== v.name) {
        // Keep references pointing at the renamed variable.
        const walk = (o: any): any => (o && typeof o === "object" ? ("var" in o && o.var === oldName ? { var: v.name } : Array.isArray(o) ? o.map(walk) : Object.fromEntries(Object.entries(o).map(([k, x]) => [k, walk(x)]))) : o);
        f.nodes.forEach((n) => (n.config = walk(n.config)));
      }
      commit(f);
    },

    removeVariable: (name) => {
      const f = clone(get().draft);
      f.variables = f.variables.filter((v) => v.name !== name);
      commit(f);
    },

    select: (id) => set((s) => ({ selectedId: id, panel: id ? "settings" : s.panel === "settings" ? "agent" : s.panel })),
    setSelection: (ids) => {
      const cur = get().selectedIds;
      if (cur.length === ids.length && cur.every((x, i) => x === ids[i])) return;
      set({ selectedIds: ids });
    },
    setPanel: (panel) => set({ panel }),
    setIssues: (issues) => set({ issues }),
    setSaveState: (saveState) => set({ saveState }),

    propose: (ops) => set((s) => ({ pending: [...s.pending, ...ops] })),
    acceptPending: () => {
      const { draft, pending } = get();
      if (!pending.length) return;
      const merged = applyOps(draft, pending);
      commit({ ...autoLayout(merged).flow, version: draft.version }, { pending: [], decision: { kind: "accepted", at: Date.now() } });
    },
    rejectPending: () => set((s) => (s.pending.length ? { pending: [], decision: { kind: "rejected", at: Date.now() } } : {})),

    discardToPublished: () => {
      const p = get().published;
      if (!p) return;
      commit({ ...clone(p), version: get().draft.version }, { issues: [], pending: [], selectedId: null });
    },

    setRun: (run) => set({ run }),
    patchRunNode: (id, s) => set((st) => (st.run ? { run: { ...st.run, nodes: { ...st.run.nodes, [id]: s } } } : {})),
    setDryRun: (d) => set((s) => ({ dryRun: { ...s.dryRun, ...d } })),

    undo: () => {
      const s = get();
      if (s.pending.length) return s.rejectPending(); // first undo drops an assistant proposal not yet accepted
      const prev = s.past[s.past.length - 1];
      if (!prev) return;
      set(restore(s, prev, s.past.slice(0, -1), [s.draft, ...s.future].slice(0, HISTORY)));
    },

    redo: () => {
      const s = get();
      const next = s.future[0];
      if (!next || s.pending.length) return;
      set(restore(s, next, [...s.past, s.draft].slice(-HISTORY), s.future.slice(1)));
    },
  };
});

/** The server's issues plus the line-up-to-Check-page problems, which the server only reports on test or publish. */
export function useIssues(): Issue[] {
  const issues = useEditor((s) => s.issues);
  const draft = useEditor((s) => s.draft);
  return useMemo(() => {
    const live = lineProblems(draft).filter((l) => !issues.some((i) => i.node_id === l.node_id && i.message === l.message));
    return live.length ? [...issues, ...live] : issues;
  }, [issues, draft]);
}
