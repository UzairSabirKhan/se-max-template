import { useReactFlow } from "@xyflow/react";
import clsx from "clsx";
import { GripVertical, PanelLeftClose, PanelLeftOpen, Search } from "lucide-react";
import { useState } from "react";
import { IconButton, toast } from "../components/ui";
import { NODE_META, PALETTE_GROUPS, TONE } from "../lib/nodeMeta";
import { NODE_H, NODE_W } from "../lib/layout";
import { useEditor } from "../store/editor";
import type { NodeType } from "../types/contracts";
import { DND_TYPE } from "./Canvas";

export function Palette() {
  const [open, setOpen] = useState(true);
  const [q, setQ] = useState("");
  const rf = useReactFlow();
  const hasCheck = useEditor((s) => s.draft.nodes.some((n) => n.type === "check_page"));
  const hasTrigger = useEditor((s) => s.draft.nodes.some((n) => n.type === "trigger"));
  const once = (t: NodeType) => (t === "check_page" && hasCheck) || (t === "trigger" && hasTrigger);

  const add = (t: NodeType) => {
    const meta = NODE_META[t];
    const { selectedId, draft, appendAfter, addNode } = useEditor.getState();
    const sel = draft.nodes.find((n) => n.id === selectedId);
    if (meta.bodyOnly && !sel?.parentId && sel?.type !== "for_each") return toast.info(`${meta.label} goes inside a Loop`, "Drag it into a Loop, or select a step inside one first.");
    if (sel && sel.type !== "alert" && sel.type !== "results") return appendAfter(sel.id, t);
    const box = document.querySelector(".react-flow")?.getBoundingClientRect();
    const c = rf.screenToFlowPosition({ x: (box?.left ?? 0) + (box?.width ?? 800) / 2, y: (box?.top ?? 0) + (box?.height ?? 600) / 2 });
    addNode(t, { x: c.x - NODE_W / 2, y: c.y - NODE_H / 2 });
  };

  if (!open)
    return (
      <div className="flex w-12 shrink-0 flex-col items-center border-r border-line bg-white py-2">
        <IconButton label="Show steps" onClick={() => setOpen(true)}>
          <PanelLeftOpen className="size-4" />
        </IconButton>
      </div>
    );

  return (
    <aside className="flex w-[244px] shrink-0 flex-col border-r border-line bg-white">
      <div className="flex items-center justify-between px-3 pb-2 pt-3">
        <p className="text-[13px] font-semibold">Steps</p>
        <IconButton label="Hide steps" onClick={() => setOpen(false)}>
          <PanelLeftClose className="size-4" />
        </IconButton>
      </div>
      <label className="relative mx-3 mb-2 block">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-zinc-400" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search steps" aria-label="Search steps" className="h-8 w-full rounded-lg border border-line bg-zinc-50 pl-8 pr-2 text-[13px] focus:border-brand-300 focus:bg-white focus:outline-none" />
      </label>
      <div className="scroll-thin flex-1 overflow-y-auto px-2 pb-4">
        {PALETTE_GROUPS.map((g) => {
          const types = g.types.filter((t) => !q || NODE_META[t].label.toLowerCase().includes(q.toLowerCase()));
          if (!types.length) return null;
          return (
            <div key={g.group} className="mt-2">
              <p className="flex items-center gap-2 px-2 pb-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-400">
                {g.group}
                {g.group === "Browser" && <span className="rounded bg-zinc-100 px-1 py-px text-[10px] normal-case tracking-normal text-zinc-500">coming soon</span>}
              </p>
              {types.map((t) => {
                const m = NODE_META[t];
                const off = m.disabled || once(t);
                return (
                  <div
                    key={t}
                    role="button"
                    tabIndex={off ? -1 : 0}
                    aria-disabled={off}
                    draggable={!off}
                    onDragStart={(e) => {
                      e.dataTransfer.setData(DND_TYPE, t);
                      e.dataTransfer.effectAllowed = "move";
                    }}
                    onClick={() => !off && add(t)}
                    onKeyDown={(e) => e.key === "Enter" && !off && add(t)}
                    title={m.disabled ? "Needs a browser, coming soon" : once(t) ? "Already in this flow (exactly one)" : `${m.blurb}. Drag onto the canvas or click to add.`}
                    className={clsx(
                      "group flex items-center gap-2.5 rounded-lg px-2 py-1.5",
                      off ? "cursor-not-allowed opacity-50" : "cursor-grab hover:bg-zinc-100 active:cursor-grabbing",
                    )}
                  >
                    <span className={clsx("flex size-7 shrink-0 items-center justify-center rounded-md", TONE[m.tone].tile)}>
                      <m.icon className="size-3.5" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-[13px] font-medium leading-tight">{m.label}</span>
                      <span className="block truncate text-[11.5px] text-muted">{m.blurb}</span>
                    </span>
                    {!off && <GripVertical className="size-3.5 shrink-0 text-zinc-300 opacity-0 group-hover:opacity-100" />}
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
    </aside>
  );
}
