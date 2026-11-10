import {
  Background,
  BackgroundVariant,
  MarkerType,
  MiniMap,
  ReactFlow,
  applyNodeChanges,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
  type NodeChange,
} from "@xyflow/react";
import clsx from "clsx";
import { Check, FlaskConical, Hand, Map as MapIcon, Maximize, Minus, MousePointer2, Network, Plus, Sparkles, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button, IconButton, Kbd, toast } from "../components/ui";
import { pendingMarks, previewOps, stepNumbers, summarizeOps } from "../lib/flow";
import { NODE_H, NODE_W, autoLayout, loopSizesOf } from "../lib/layout";
import { NODE_META } from "../lib/nodeMeta";
import { useEditor } from "../store/editor";
import type { NodeType } from "../types/contracts";
import { edgeTypes } from "./edges";
import { nodeTypes, type StepData } from "./nodes";

export const DND_TYPE = "application/x-scrapeonce-node";
const BODY_OK: NodeType[] = ["fetch_item_page", "extract_fields", "condition", "wait"];

export function Canvas({ onTestNode, onTestFlow, testing }: { onTestNode: (id: string) => void; onTestFlow: () => void; testing: boolean }) {
  const draft = useEditor((s) => s.draft);
  const pending = useEditor((s) => s.pending);
  const issues = useEditor((s) => s.issues);
  const run = useEditor((s) => s.run);
  const selectedId = useEditor((s) => s.selectedId);
  const flowId = useEditor((s) => s.flowId);
  const { select, setSelection, moveNodes, connect, removeNode, removeEdge, addNode, acceptPending, rejectPending } = useEditor.getState();
  const rf = useReactFlow();
  const [panMode, setPanMode] = useState(false);
  const [showMap, setShowMap] = useState(false);
  const wrapper = useRef<HTMLDivElement>(null);

  const view = useMemo(() => {
    if (pending.length) return autoLayout(previewOps(draft, pending));
    return { flow: draft, loopSizes: loopSizesOf(draft) };
  }, [draft, pending]);
  const marks = useMemo(() => pendingMarks(pending), [pending]);

  const built = useMemo(() => {
    const steps = stepNumbers(view.flow);
    const issueCount: Record<string, number> = {};
    for (const i of issues) if (i.node_id) issueCount[i.node_id] = (issueCount[i.node_id] ?? 0) + 1;
    const outs = new Set(view.flow.edges.filter((e) => e.targetHandle !== "next").map((e) => e.source));
    // React Flow needs parents before children.
    const ordered = [...view.flow.nodes].sort((a, b) => Number(!!a.parentId) - Number(!!b.parentId));
    const nodes: Node[] = ordered.map((n) => {
      const data: StepData = { node: n, step: steps[n.id], issues: issueCount[n.id] ?? 0, mark: marks.nodes[n.id], run: run?.nodes[n.id], hasOut: outs.has(n.id), onTest: onTestNode };
      const size = view.loopSizes[n.id];
      return {
        id: n.id,
        type: n.type === "for_each" ? "loop" : "step",
        position: n.position,
        ...(n.parentId ? { parentId: n.parentId, extent: "parent" as const } : {}),
        data: size ? { ...data, ...size } : data,
        selected: n.id === selectedId,
        draggable: !pending.length,
        deletable: !pending.length && n.type !== "trigger" && n.type !== "check_page",
        ...(size ? { style: { width: size.width, height: size.height }, width: size.width, height: size.height } : {}),
      };
    });
    const insideLoop = (s: string, t: string) => {
      const a = view.flow.nodes.find((n) => n.id === s);
      const b = view.flow.nodes.find((n) => n.id === t);
      return !!(a?.parentId || b?.parentId || a?.type === "for_each" && b?.parentId);
    };
    const edges: Edge[] = view.flow.edges.map((e) => {
      const mark = marks.edges[e.id];
      const running = run && run.nodes[e.source]?.state === "done" && run.nodes[e.target]?.state === "running";
      return {
        id: e.id,
        source: e.source,
        target: e.target,
        sourceHandle: e.sourceHandle ?? null,
        targetHandle: e.targetHandle ?? null,
        type: "insert",
        deletable: !pending.length,
        data: { mark, insideLoop: insideLoop(e.source, e.target) || e.sourceHandle === "item" || e.targetHandle === "next", readOnly: !!pending.length },
        className: clsx(mark && `edge-pending-${mark}`, running && "edge-running"),
        markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: mark === "add" ? "#22c55e" : mark === "remove" ? "#ef4444" : "#b4b4c0" },
        zIndex: e.sourceHandle === "item" || e.targetHandle === "next" || insideLoop(e.source, e.target) ? 1 : 0,
      };
    });
    return { nodes, edges };
  }, [view, marks, issues, run, selectedId, pending.length, onTestNode]);

  const [nodes, setNodes] = useState<Node[]>(built.nodes);
  useEffect(() => setNodes(built.nodes), [built.nodes]);
  const onNodesChange = useCallback((changes: NodeChange[]) => setNodes((nds) => applyNodeChanges(changes.filter((c) => c.type !== "remove"), nds)), []);

  // Fit when a flow opens, and when the assistant proposes a new graph.
  useEffect(() => {
    const t = setTimeout(() => rf.fitView({ padding: 0.18, maxZoom: 1, duration: 250 }), 60);
    return () => clearTimeout(t);
  }, [flowId, pending.length > 0, rf]);

  const onConnect = useCallback(
    (c: Connection) => {
      if (c.source === c.target) return;
      connect({ source: c.source, target: c.target, ...(c.sourceHandle ? { sourceHandle: c.sourceHandle as any } : {}), ...(c.targetHandle ? { targetHandle: c.targetHandle as any } : {}) });
    },
    [connect],
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const type = e.dataTransfer.getData(DND_TYPE) as NodeType;
      if (!type) return;
      const p = rf.screenToFlowPosition({ x: e.clientX, y: e.clientY });
      const loop = view.flow.nodes.find((n) => {
        if (n.type !== "for_each") return false;
        const s = view.loopSizes[n.id];
        return s && p.x >= n.position.x && p.x <= n.position.x + s.width && p.y >= n.position.y && p.y <= n.position.y + s.height;
      });
      const meta = NODE_META[type];
      if (meta.bodyOnly && !loop) return toast.error(`${meta.label} goes inside a Loop`, "Drop it inside a Loop container.");
      if (loop && !BODY_OK.includes(type)) return toast.error(`${meta.label} can't go inside a Loop`, "Only Open item page, Extract fields, Condition and Wait run per item.");
      if (type === "check_page" && draft.nodes.some((n) => n.type === "check_page")) return toast.info("Check page is already in this flow", "A flow has exactly one.");
      const pos = loop ? { x: Math.max(16, p.x - loop.position.x - NODE_W / 2), y: Math.max(64, p.y - loop.position.y - NODE_H / 2) } : { x: p.x - NODE_W / 2, y: p.y - NODE_H / 2 };
      addNode(type, pos, loop?.id);
    },
    [rf, view, draft.nodes, addNode],
  );

  const summary = summarizeOps(pending);

  return (
    <div ref={wrapper} className="relative h-full w-full bg-canvas" onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; }} onDrop={onDrop}>
      <ReactFlow
        nodes={nodes}
        edges={built.edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onNodeDragStop={(_, __, dragged) => moveNodes(dragged.map((n) => ({ id: n.id, position: n.position })))}
        onNodeClick={(_, n) => select(n.id)}
        onPaneClick={() => select(null)}
        onSelectionChange={({ nodes: sel }) => setSelection(sel.map((n) => n.id))}
        onConnect={onConnect}
        onNodesDelete={(del) => del.forEach((n) => removeNode(n.id))}
        onEdgesDelete={(del) => del.forEach((e) => removeEdge(e.id))}
        deleteKeyCode={["Backspace", "Delete"]}
        panOnDrag={panMode ? true : [1, 2]}
        selectionOnDrag={!panMode}
        panOnScroll
        minZoom={0.3}
        maxZoom={1.6}
        proOptions={{ hideAttribution: true }}
        nodesConnectable={!pending.length}
      >
        <Background variant={BackgroundVariant.Dots} gap={18} size={1.2} color="#d4d4dc" />
        {showMap && <MiniMap pannable zoomable className="!bottom-16 !right-3 rounded-lg border border-line" maskColor="rgb(247 247 249 / 0.7)" nodeColor="#d7ccff" />}
      </ReactFlow>

      {/* a new flow starts empty: say how to begin */}
      {draft.nodes.length === 0 && !pending.length && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="max-w-sm rounded-xl border border-dashed border-line bg-white/80 px-6 py-5 text-center">
            <p className="text-sm font-semibold text-zinc-800">This flow is empty</p>
            <p className="mt-1 text-sm text-zinc-500">
              Ask the assistant to build it, or start with a <span className="font-medium">Schedule</span> step
              from the Steps panel, then add a source and <span className="font-medium">Check page</span>.
            </p>
          </div>
        </div>
      )}

      {/* top centre: test flow or pending review */}
      <div className="pointer-events-none absolute inset-x-0 top-3 flex justify-center">
        {pending.length ? (
          <div className="pointer-events-auto flex items-center gap-3 rounded-xl border border-emerald-200 bg-white py-1.5 pl-3 pr-1.5 shadow-pop">
            <Sparkles className="size-4 text-brand-600" />
            <span className="text-[13px]">
              <strong className="font-semibold">Assistant's proposal:</strong>{" "}
              {[summary.added && `${summary.added} new`, summary.changed && `${summary.changed} changed`, summary.removed && `${summary.removed} removed`, summary.variables && `${summary.variables} variable${summary.variables > 1 ? "s" : ""}`].filter(Boolean).join(" · ") || `${summary.links} links`}
            </span>
            <Button size="sm" variant="ghost" icon={<X className="size-3.5" />} onClick={rejectPending}>Reject</Button>
            <Button size="sm" variant="primary" icon={<Check className="size-3.5" />} onClick={acceptPending}>Accept</Button>
          </div>
        ) : (
          <button onClick={onTestFlow} disabled={testing} className="pointer-events-auto flex h-8 items-center gap-2 rounded-lg border border-brand-200 bg-brand-50/90 px-3 text-[13px] font-medium text-brand-700 shadow-card backdrop-blur transition-colors hover:bg-brand-100 disabled:opacity-60">
            <FlaskConical className="size-3.5" /> {testing ? "Testing…" : "Test flow"} <Kbd>Ctrl + D</Kbd>
          </button>
        )}
      </div>

      {/* bottom toolbar */}
      <div className="absolute bottom-4 left-1/2 flex -translate-x-1/2 items-center gap-0.5 rounded-xl border border-line bg-white p-1 shadow-pop">
        <IconButton label="Zoom in" onClick={() => rf.zoomIn({ duration: 150 })}><Plus className="size-4" /></IconButton>
        <IconButton label="Zoom out" onClick={() => rf.zoomOut({ duration: 150 })}><Minus className="size-4" /></IconButton>
        <IconButton label="Fit to screen" onClick={() => rf.fitView({ padding: 0.18, maxZoom: 1, duration: 250 })}><Maximize className="size-4" /></IconButton>
        <IconButton label="Tidy up layout" disabled={!!pending.length} onClick={() => { useEditor.getState().layout(); setTimeout(() => rf.fitView({ padding: 0.18, maxZoom: 1, duration: 250 }), 50); }}><Network className="size-4" /></IconButton>
        <span className="mx-1 h-5 w-px bg-line" />
        <IconButton label="Pan mode" active={panMode} onClick={() => setPanMode(true)}><Hand className="size-4" /></IconButton>
        <IconButton label="Select mode" active={!panMode} onClick={() => setPanMode(false)}><MousePointer2 className="size-4" /></IconButton>
        <span className="mx-1 h-5 w-px bg-line" />
        <IconButton label="Mini map" active={showMap} onClick={() => setShowMap((v) => !v)}><MapIcon className="size-4" /></IconButton>
      </div>
    </div>
  );
}
