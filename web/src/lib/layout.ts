import { graphlib, layout } from "@dagrejs/dagre";
import type { Flow } from "../types/contracts";

export const NODE_W = 264;
export const NODE_H = 66;
const LOOP_PAD_X = 32;
const LOOP_HEADER = 76;
const LOOP_PAD_BOTTOM = 56;
const LOOP_MIN_W = 340;

export type LoopSize = Record<string, { width: number; height: number }>;

/** Top-to-bottom layout. Loop bodies are laid out inside their container first. */
export function autoLayout(flow: Flow): { flow: Flow; loopSizes: LoopSize } {
  const f: Flow = structuredClone(flow);
  const loopSizes: LoopSize = {};
  const byId = new Map(f.nodes.map((n) => [n.id, n]));

  for (const loop of f.nodes.filter((n) => n.type === "for_each")) {
    const kids = f.nodes.filter((n) => n.parentId === loop.id);
    if (!kids.length) {
      loopSizes[loop.id] = { width: LOOP_MIN_W, height: 180 };
      continue;
    }
    const g = new graphlib.Graph();
    g.setGraph({ rankdir: "TB", nodesep: 36, ranksep: 52 });
    g.setDefaultEdgeLabel(() => ({}));
    kids.forEach((k) => g.setNode(k.id, { width: NODE_W, height: NODE_H }));
    const kidIds = new Set(kids.map((k) => k.id));
    f.edges.filter((e) => kidIds.has(e.source) && kidIds.has(e.target)).forEach((e) => g.setEdge(e.source, e.target));
    layout(g);
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const k of kids) {
      const p = g.node(k.id);
      minX = Math.min(minX, p.x - NODE_W / 2);
      maxX = Math.max(maxX, p.x + NODE_W / 2);
      minY = Math.min(minY, p.y - NODE_H / 2);
      maxY = Math.max(maxY, p.y + NODE_H / 2);
    }
    const width = Math.max(maxX - minX + LOOP_PAD_X * 2, LOOP_MIN_W);
    const offsetX = (width - (maxX - minX)) / 2;
    for (const k of kids) {
      const p = g.node(k.id);
      k.position = { x: p.x - NODE_W / 2 - minX + offsetX, y: p.y - NODE_H / 2 - minY + LOOP_HEADER };
    }
    loopSizes[loop.id] = { width, height: maxY - minY + LOOP_HEADER + LOOP_PAD_BOTTOM };
  }

  const top = f.nodes.filter((n) => !n.parentId);
  const g = new graphlib.Graph();
  g.setGraph({ rankdir: "TB", nodesep: 48, ranksep: 64 });
  g.setDefaultEdgeLabel(() => ({}));
  const size = (id: string) => loopSizes[id] ?? { width: NODE_W, height: NODE_H };
  top.forEach((n) => g.setNode(n.id, size(n.id)));
  const lift = (id: string) => byId.get(id)?.parentId ?? id;
  for (const e of f.edges) {
    if (e.targetHandle === "next") continue;
    const s = lift(e.source), t = lift(e.target);
    if (s !== t && g.hasNode(s) && g.hasNode(t)) g.setEdge(s, t);
  }
  layout(g);
  for (const n of top) {
    const p = g.node(n.id);
    const { width, height } = size(n.id);
    n.position = { x: Math.round(p.x - width / 2), y: Math.round(p.y - height / 2) };
  }
  return { flow: f, loopSizes };
}

export function needsLayout(flow: Flow) {
  const top = flow.nodes.filter((n) => !n.parentId);
  return top.length > 1 && top.every((n) => n.position.x === top[0].position.x && n.position.y === top[0].position.y);
}

/** Sizes for loops without re-positioning anything (used after manual moves). */
export function loopSizesOf(flow: Flow): LoopSize {
  const out: LoopSize = {};
  for (const loop of flow.nodes.filter((n) => n.type === "for_each")) {
    const kids = flow.nodes.filter((n) => n.parentId === loop.id);
    if (!kids.length) {
      out[loop.id] = { width: LOOP_MIN_W, height: 180 };
      continue;
    }
    const maxX = Math.max(...kids.map((k) => k.position.x + NODE_W));
    const maxY = Math.max(...kids.map((k) => k.position.y + NODE_H));
    out[loop.id] = { width: Math.max(maxX + LOOP_PAD_X, LOOP_MIN_W), height: maxY + LOOP_PAD_BOTTOM };
  }
  return out;
}
