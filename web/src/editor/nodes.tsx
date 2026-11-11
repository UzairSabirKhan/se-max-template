import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { cn as clsx } from "../components/ui";
import { AlertTriangle, Check, FlaskConical, Loader2, Lock, MoreHorizontal, Plus, Settings2, Trash2, Zap } from "lucide-react";
import { memo, useEffect, useRef, useState } from "react";
import type { PendingMark } from "../lib/flow";
import { NODE_H, NODE_W } from "../lib/layout";
import { NODE_META, TONE, summarize } from "../lib/nodeMeta";
import { useEditor, type NodeRunState } from "../store/editor";
import type { FlowNode } from "../types/contracts";
import { NodePicker } from "./NodePicker";

export type StepData = {
  node: FlowNode;
  step: number;
  issues: number;
  mark?: PendingMark;
  run?: NodeRunState;
  hasOut: boolean;
  onTest: (id: string) => void;
};
export type StepNodeT = Node<StepData, "step">;
export type LoopNodeT = Node<StepData & { width: number; height: number }, "loop">;

const markRing: Record<PendingMark, string> = {
  add: "ring-2 ring-emerald-400 border-emerald-300",
  change: "ring-2 ring-amber-400 border-amber-300",
  remove: "ring-2 ring-red-300 border-red-200 opacity-60",
};
const markLabel: Record<PendingMark, { text: string; cls: string }> = {
  add: { text: "Proposed", cls: "bg-emerald-50 text-emerald-700" },
  change: { text: "Changed", cls: "bg-amber-50 text-amber-700" },
  remove: { text: "Removing", cls: "bg-red-50 text-red-700" },
};

function RunDot({ run }: { run?: NodeRunState }) {
  if (!run) return null;
  if (run.state === "running") return <Loader2 className="size-4 animate-spin text-brand-600" aria-label="Running" />;
  if (run.state === "error") return <AlertTriangle className="size-4 text-red-500" aria-label="Failed" />;
  return (
    <span className="flex items-center gap-1 text-[11px] font-medium text-emerald-700" title={`${run.items_in ?? 0} in → ${run.items_out ?? 0} out`}>
      <Check className="size-3.5" />
      {run.items_out ?? ""}
    </span>
  );
}

/** The "⋯" menu on every step: open its settings, test up to it, or delete it. */
function NodeMenu({ node, onTest, testable }: { node: FlowNode; onTest: (id: string) => void; testable: boolean }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const removeNode = useEditor((s) => s.removeNode);
  const select = useEditor((s) => s.select);
  const bodyCount = useEditor((s) => s.draft.nodes.filter((n) => n.parentId === node.id).length);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as globalThis.Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);
  const required = node.type === "trigger" || node.type === "check_page";
  const item = "flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[13px]";
  return (
    <div ref={ref} className="nodrag relative">
      <button
        aria-label="Step actions"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={(e) => {
          e.stopPropagation();
          if (!open) select(node.id); // a selected step is drawn on top, so its menu isn't hidden
          setOpen((o) => !o);
        }}
        className="flex size-6 items-center justify-center rounded-md text-zinc-400 hover:bg-zinc-100 hover:text-ink"
      >
        <MoreHorizontal className="size-4" />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 top-7 z-50 w-56 rounded-xl border border-line bg-white p-1 shadow-pop" onClick={(e) => e.stopPropagation()}>
          <button role="menuitem" className={clsx(item, "hover:bg-zinc-100")} onClick={() => { setOpen(false); select(node.id); }}>
            <Settings2 className="size-3.5" /> Open settings
          </button>
          {testable && (
            <button role="menuitem" className={clsx(item, "hover:bg-zinc-100")} onClick={() => { setOpen(false); onTest(node.id); }}>
              <FlaskConical className="size-3.5" /> Test up to here
            </button>
          )}
          <div className="my-1 h-px bg-line" />
          {required ? (
            <p className={clsx(item, "cursor-default text-zinc-400")} title="Every flow needs its Schedule and Check page">
              <Lock className="size-3.5" /> Required step
            </p>
          ) : (
            <button role="menuitem" className={clsx(item, "text-red-600 hover:bg-red-50")} onClick={() => { setOpen(false); removeNode(node.id); }}>
              <Trash2 className="size-3.5" /> {bodyCount ? `Delete loop and its ${bodyCount} steps` : "Delete step"}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function AddBelow({ id, insideLoop }: { id: string; insideLoop: boolean }) {
  const [open, setOpen] = useState(false);
  const appendAfter = useEditor((s) => s.appendAfter);
  return (
    <div className="absolute left-1/2 top-full mt-3 -translate-x-1/2">
      <button aria-label="Add a step after this" onClick={(e) => { e.stopPropagation(); setOpen(true); }} className="nodrag flex size-5 items-center justify-center rounded-full border border-line bg-white text-zinc-500 shadow-card hover:border-brand-400 hover:text-brand-600">
        <Plus className="size-3" />
      </button>
      {open && (
        <div className="absolute left-1/2 top-7 z-50 -translate-x-1/2">
          <NodePicker insideLoop={insideLoop} onClose={() => setOpen(false)} onPick={(t) => { setOpen(false); appendAfter(id, t); }} />
        </div>
      )}
    </div>
  );
}

export const StepNode = memo(function StepNode({ data, selected }: NodeProps<StepNodeT>) {
  const { node, step, issues, mark, run } = data;
  const meta = NODE_META[node.type];
  const isTrigger = node.type === "trigger";
  const isCondition = node.type === "condition";
  const isOutput = node.type === "alert" || node.type === "results";
  return (
    <div className={clsx("group relative", selected && "is-selected")} style={{ width: NODE_W }}>
      {isTrigger && (
        <span className="absolute -top-[26px] left-0 flex items-center gap-1 rounded-md border border-brand-200 bg-brand-50 px-1.5 py-0.5 text-[11px] font-medium text-brand-700">
          <Zap className="size-3" /> Trigger
        </span>
      )}
      {mark && <span className={clsx("absolute -top-[26px] left-0 rounded-md px-1.5 py-0.5 text-[11px] font-semibold", isTrigger && "left-20", markLabel[mark].cls)}>{markLabel[mark].text}</span>}
      {!isTrigger && <Handle type="target" position={Position.Top} />}
      <div
        className={clsx(
          "flex items-center gap-3 rounded-xl border bg-white px-3 shadow-card transition-shadow",
          meta.disabled && "border-dashed bg-zinc-50",
          issues ? "border-red-300 ring-2 ring-red-100" : "border-line",
          selected && !issues && "border-brand-400 ring-2 ring-brand-100",
          mark && markRing[mark],
          run?.state === "running" && "ring-2 ring-brand-300",
          run?.state === "error" && "border-red-300 ring-2 ring-red-100",
        )}
        style={{ height: NODE_H }}
      >
        <div className={clsx("flex size-9 shrink-0 items-center justify-center rounded-lg", TONE[meta.tone].tile)}>
          <meta.icon className="size-[18px]" />
        </div>
        <div className="min-w-0 flex-1">
          <p className={clsx("truncate text-[13.5px] font-semibold leading-tight", meta.disabled && "text-zinc-500", mark === "remove" && "line-through")}>
            <span className="text-zinc-400">{step}.</span> {meta.label}
          </p>
          <p className="mt-0.5 truncate text-[12px] text-muted">{meta.disabled ? "Needs a browser · coming soon" : summarize(node)}</p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <RunDot run={run} />
          {issues > 0 && (
            <span className="flex size-5 items-center justify-center rounded-full bg-red-500 text-[11px] font-bold text-white" title={`${issues} thing${issues > 1 ? "s" : ""} to fix`}>
              {issues}
            </span>
          )}
          {node.type === "check_page" && <Lock className="size-3.5 text-zinc-300" aria-label="Required step" />}
          {!mark && <NodeMenu node={node} onTest={data.onTest} testable={!isTrigger} />}
        </div>
      </div>
      {isCondition ? (
        <>
          <Handle id="true" type="source" position={Position.Bottom} style={{ left: "30%" }} />
          <Handle id="false" type="source" position={Position.Bottom} style={{ left: "70%" }} />
          <span className="pointer-events-none absolute -bottom-[18px] left-[30%] -translate-x-1/2 text-[10.5px] font-semibold text-emerald-600">true</span>
          <span className="pointer-events-none absolute -bottom-[18px] left-[70%] -translate-x-1/2 text-[10.5px] font-semibold text-zinc-400">false</span>
        </>
      ) : (
        !isOutput && <Handle type="source" position={Position.Bottom} />
      )}
      {!data.hasOut && !isOutput && !isCondition && !mark && <AddBelow id={node.id} insideLoop={!!node.parentId} />}
    </div>
  );
});

export const LoopNode = memo(function LoopNode({ data, selected }: NodeProps<LoopNodeT>) {
  const { node, step, issues, mark, run, width, height } = data;
  const meta = NODE_META.for_each;
  const empty = !useEditor((s) => s.draft.nodes.some((n) => n.parentId === node.id));
  const [open, setOpen] = useState(false);
  const addNode = useEditor((s) => s.addNode);
  const connect = useEditor((s) => s.connect);
  const layout = useEditor((s) => s.layout);
  return (
    <div className={clsx("group relative", selected && "is-selected")} style={{ width, height }}>
      {mark && <span className={clsx("absolute -top-[26px] left-0 rounded-md px-1.5 py-0.5 text-[11px] font-semibold", markLabel[mark].cls)}>{markLabel[mark].text}</span>}
      <Handle type="target" position={Position.Top} />
      <div
        className={clsx(
          "h-full rounded-2xl border-[1.5px] border-dashed bg-fuchsia-50/60 shadow-card",
          issues ? "border-red-300" : selected ? "border-brand-400" : "border-fuchsia-300",
          mark && markRing[mark],
        )}
      >
        <div className="flex h-[52px] items-center gap-2.5 rounded-t-2xl border-b border-dashed border-fuchsia-300 bg-white px-3">
          <div className={clsx("flex size-8 items-center justify-center rounded-lg", TONE.pink.tile)}>
            <meta.icon className="size-4" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[13.5px] font-semibold leading-tight">
              <span className="text-zinc-400">{step}.</span> Loop
            </p>
            <p className="truncate text-[12px] text-muted">{summarize(node)} · one at a time</p>
          </div>
          <RunDot run={run} />
          {issues > 0 && <span className="flex size-5 items-center justify-center rounded-full bg-red-500 text-[11px] font-bold text-white">{issues}</span>}
          {!mark && <NodeMenu node={node} onTest={data.onTest} testable />}
        </div>
        {empty && (
          <div className="flex h-[calc(100%-52px)] flex-col items-center justify-center gap-2 text-[12.5px] text-muted">
            Drop steps here, or
            <div className="relative">
              <button onClick={(e) => { e.stopPropagation(); setOpen(true); }} className="nodrag rounded-lg border border-line bg-white px-2.5 py-1 font-medium text-ink shadow-card hover:border-brand-300">
                + Add first step
              </button>
              {open && (
                <div className="absolute left-1/2 top-9 z-50 -translate-x-1/2">
                  <NodePicker
                    insideLoop
                    onClose={() => setOpen(false)}
                    onPick={(t) => {
                      setOpen(false);
                      const id = addNode(t, { x: 40, y: 80 }, node.id);
                      connect({ source: node.id, sourceHandle: "item", target: id });
                      connect({ source: id, target: node.id, targetHandle: "next" });
                      layout();
                    }}
                  />
                </div>
              )}
            </div>
          </div>
        )}
      </div>
      {/* item → body ... body → next, then done → after the loop */}
      <Handle id="item" type="source" position={Position.Bottom} style={{ top: 52 }} />
      <span className="pointer-events-none absolute left-1/2 top-[56px] ml-2 text-[10.5px] font-semibold text-fuchsia-600">each item</span>
      <Handle id="next" type="target" position={Position.Top} style={{ top: "auto", bottom: 14 }} />
      <span className="pointer-events-none absolute bottom-[8px] left-1/2 ml-2 text-[10.5px] font-semibold text-fuchsia-600">next</span>
      <Handle id="done" type="source" position={Position.Bottom} />
      <span className="pointer-events-none absolute -bottom-[18px] left-1/2 ml-2 text-[10.5px] font-semibold text-zinc-500">done</span>
    </div>
  );
});

export const nodeTypes = { step: StepNode, loop: LoopNode };
