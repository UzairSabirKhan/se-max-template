import clsx from "clsx";
import { Braces, Check, ChevronDown, Database } from "lucide-react";
import { useState } from "react";
import { stepNumbers } from "../lib/flow";
import { useEditor } from "../store/editor";
import { sampleText, type useStepData } from "./useStepData";

const TYPE_TONE: Record<string, string> = {
  price: "bg-emerald-50 text-emerald-700", int: "bg-emerald-50 text-emerald-700", url: "bg-sky-50 text-sky-700",
  text: "bg-zinc-100 text-zinc-600", date: "bg-amber-50 text-amber-700", stock: "bg-violet-50 text-violet-700",
  change: "bg-fuchsia-50 text-fuchsia-700",
};

/** "Data from previous steps": what this step can use, grouped by the step that produced it, with a sample
 *  value from the latest run. Only EARLIER steps appear (the server works this out from the graph). */
export function DataPanel({ data }: { data: ReturnType<typeof useStepData> }) {
  const draft = useEditor((s) => s.draft);
  const steps = stepNumbers(draft);
  const [open, setOpen] = useState(true);
  const [copied, setCopied] = useState<string | null>(null);
  const { groups, variables, loading, error } = data;
  if (!loading && !error && !groups.length && !variables.length) return null;

  const copy = (text: string) => {
    void navigator.clipboard?.writeText(text).catch(() => undefined);
    setCopied(text);
    setTimeout(() => setCopied(null), 1200);
  };

  return (
    <div className="rounded-xl border border-line bg-white">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 px-3 py-2.5 text-left">
        <Database className="size-4 text-brand-600" />
        <span className="flex-1 text-[13px] font-semibold">Data from previous steps</span>
        <ChevronDown className={clsx("size-4 text-zinc-400 transition", !open && "-rotate-90")} />
      </button>
      {open && (
        <div className="space-y-2.5 border-t border-line px-3 py-2.5">
          {loading && <p className="text-[12.5px] text-muted">Loading…</p>}
          {error && <p className="text-[12.5px] text-muted">Couldn't load the data list. The settings below still work.</p>}
          {groups.map((g) => (
            <div key={g.label + g.source_node_id}>
              <p className="mb-1 text-[11.5px] font-semibold uppercase tracking-wide text-zinc-400">
                {steps[g.source_node_id] ? `${steps[g.source_node_id]}. ` : ""}{g.label}
              </p>
              <div className="space-y-0.5">
                {g.fields.map((f) => (
                  <button key={f.name} onClick={() => copy(f.name)} title="Click to copy the field name"
                          className="flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left hover:bg-zinc-50">
                    <span className="font-mono text-[12.5px] text-zinc-800">{f.name}</span>
                    <span className={clsx("rounded px-1.5 text-[10.5px] font-medium", TYPE_TONE[f.type] ?? TYPE_TONE.text)}>{f.type}</span>
                    <span className="min-w-0 flex-1 truncate text-right font-mono text-[11.5px] text-zinc-400">
                      {copied === f.name ? <Check className="ml-auto size-3.5 text-emerald-600" /> : sampleText(f.sample)}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ))}
          {variables.length > 0 && (
            <div>
              <p className="mb-1 text-[11.5px] font-semibold uppercase tracking-wide text-zinc-400">Variables</p>
              {variables.map((v) => (
                <button key={v.name} onClick={() => copy(`{"var": "${v.name}"}`)} title="Click to copy the variable reference"
                        className="flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left hover:bg-zinc-50">
                  <Braces className="size-3.5 text-zinc-400" />
                  <span className="font-mono text-[12.5px] text-zinc-800">{v.name}</span>
                  <span className="rounded bg-zinc-100 px-1.5 text-[10.5px] font-medium text-zinc-600">{v.type}</span>
                  <span className="min-w-0 flex-1 truncate text-right font-mono text-[11.5px] text-zinc-400">{sampleText(v.sample)}</span>
                </button>
              ))}
            </div>
          )}
          {!loading && groups.length > 0 && groups.every((g) => g.fields.every((f) => f.sample == null)) && (
            <p className="text-[11.5px] text-muted">Run “Test flow” to see sample values.</p>
          )}
        </div>
      )}
    </div>
  );
}
