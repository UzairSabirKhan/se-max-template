import clsx from "clsx";
import { Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { NODE_META, PALETTE_GROUPS, TONE } from "../lib/nodeMeta";
import type { NodeType } from "../types/contracts";

const BODY_OK: NodeType[] = ["fetch_item_page", "extract_fields", "condition", "wait"];

/** Small searchable menu used by the "+" buttons on edges and under nodes. */
export function NodePicker({ insideLoop, onPick, onClose }: { insideLoop: boolean; onPick: (t: NodeType) => void; onClose: () => void }) {
  const [q, setQ] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const h = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && onClose();
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    setTimeout(() => document.addEventListener("mousedown", h));
    document.addEventListener("keydown", k);
    return () => {
      document.removeEventListener("mousedown", h);
      document.removeEventListener("keydown", k);
    };
  }, [onClose]);

  const groups = PALETTE_GROUPS.map((g) => ({
    ...g,
    types: g.types.filter((t) => {
      const m = NODE_META[t];
      if (t === "check_page") return false; // exactly one, always present
      if (insideLoop ? !BODY_OK.includes(t) : m.bodyOnly) return false;
      return !q || m.label.toLowerCase().includes(q.toLowerCase()) || m.blurb.toLowerCase().includes(q.toLowerCase());
    }),
  })).filter((g) => g.types.length && g.group !== "Browser");

  return (
    <div ref={ref} className="nodrag nopan nowheel w-64 rounded-xl border border-line bg-white p-1.5 text-left shadow-pop" onClick={(e) => e.stopPropagation()}>
      <label className="relative mb-1 block">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-zinc-400" />
        <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder={insideLoop ? "Add a step inside the loop" : "Add a step"} className="h-8 w-full rounded-lg bg-zinc-50 pl-8 pr-2 text-[13px] focus:outline-none" />
      </label>
      <div className="scroll-thin max-h-72 overflow-y-auto">
        {groups.map((g) => (
          <div key={g.group} className="py-1">
            <p className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-400">{g.group}</p>
            {g.types.map((t) => {
              const m = NODE_META[t];
              return (
                <button key={t} onClick={() => onPick(t)} className="flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 hover:bg-zinc-100">
                  <span className={clsx("flex size-7 items-center justify-center rounded-md", TONE[m.tone].tile)}>
                    <m.icon className="size-3.5" />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-[13px] font-medium leading-tight">{m.label}</span>
                    <span className="block truncate text-[11.5px] text-muted">{m.blurb}</span>
                  </span>
                </button>
              );
            })}
          </div>
        ))}
        {!groups.length && <p className="px-2 py-4 text-center text-[12.5px] text-muted">No steps match.</p>}
      </div>
    </div>
  );
}
