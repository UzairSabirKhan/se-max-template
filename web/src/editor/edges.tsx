import { BaseEdge, EdgeLabelRenderer, getSmoothStepPath, type Edge, type EdgeProps } from "@xyflow/react";
import clsx from "clsx";
import { Plus } from "lucide-react";
import { memo, useState } from "react";
import type { PendingMark } from "../lib/flow";
import { useEditor } from "../store/editor";
import { NodePicker } from "./NodePicker";

export type InsertEdgeData = { mark?: PendingMark; insideLoop: boolean; readOnly: boolean };
export type InsertEdgeT = Edge<InsertEdgeData, "insert">;

export const InsertEdge = memo(function InsertEdge(p: EdgeProps<InsertEdgeT>) {
  const [path, labelX, labelY] = getSmoothStepPath({
    sourceX: p.sourceX, sourceY: p.sourceY, targetX: p.targetX, targetY: p.targetY,
    sourcePosition: p.sourcePosition, targetPosition: p.targetPosition, borderRadius: 12, offset: 18,
  });
  const [open, setOpen] = useState(false);
  const insertOnEdge = useEditor((s) => s.insertOnEdge);
  const showPlus = !p.data?.readOnly && !p.data?.mark;
  return (
    <>
      <BaseEdge id={p.id} path={path} markerEnd={p.markerEnd} style={p.style} />
      {showPlus && (
        <EdgeLabelRenderer>
          <div className="nodrag nopan absolute" style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`, pointerEvents: "all", zIndex: open ? 1000 : 1 }}>
            <button
              aria-label="Insert a step here"
              onClick={() => setOpen(true)}
              className={clsx(
                "flex size-5 items-center justify-center rounded-full border bg-white text-zinc-500 shadow-card transition-all hover:scale-110 hover:border-brand-400 hover:text-brand-600",
                p.selected ? "border-brand-400 text-brand-600" : "border-line",
              )}
            >
              <Plus className="size-3" />
            </button>
            {open && (
              <div className="absolute left-1/2 top-7 -translate-x-1/2">
                <NodePicker
                  insideLoop={!!p.data?.insideLoop}
                  onClose={() => setOpen(false)}
                  onPick={(t) => {
                    setOpen(false);
                    insertOnEdge(p.id, t);
                  }}
                />
              </div>
            )}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
});

export const edgeTypes = { insert: InsertEdge };
