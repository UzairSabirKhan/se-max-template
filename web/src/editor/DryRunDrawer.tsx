import { AlertCircle, ChevronDown, FlaskConical, ShieldCheck, X } from "lucide-react";
import { useState } from "react";
import { Checks, ItemsTable, NodeTrace } from "../components/RunReport";
import { IconButton, Segmented, Spinner, VERDICT_STYLE, VerdictBadge } from "../components/ui";
import { duration } from "../lib/format";
import { useEditor } from "../store/editor";

export function DryRunDrawer() {
  const d = useEditor((s) => s.dryRun);
  const draft = useEditor((s) => s.draft);
  const setDryRun = useEditor((s) => s.setDryRun);
  const [tab, setTab] = useState<"items" | "checks" | "steps">("items");
  const [tall, setTall] = useState(false);
  if (!d.open) return null;
  const r = d.report;

  return (
    <div className="absolute inset-x-3 bottom-3 z-20 flex flex-col overflow-hidden rounded-xl border border-line bg-white shadow-pop" style={{ height: tall ? "70%" : 340 }}>
      <div className="flex items-center gap-3 border-b border-line px-4 py-2.5">
        <FlaskConical className="size-4 text-brand-600" />
        <p className="text-[14px] font-semibold">Test run</p>
        {d.loading ? (
          <span className="flex items-center gap-2 text-[13px] text-muted"><Spinner /> Fetching pages and checking selectors…</span>
        ) : r ? (
          <>
            <VerdictBadge verdict={r.verdict} />
            <span className="min-w-0 flex-1 truncate text-[13px] text-zinc-700">{r.reason}</span>
            <span className="hidden text-[12.5px] text-muted md:inline">{r.items_found} items · {duration(r.duration_ms)}</span>
            <span className="flex items-center gap-1 rounded-md bg-emerald-50 px-1.5 py-0.5 text-[11.5px] font-medium text-emerald-700" title="Runs never call AI">
              <ShieldCheck className="size-3" /> AI calls: {r.ai_calls}
            </span>
          </>
        ) : (
          <span className="flex-1" />
        )}
        <IconButton label={tall ? "Make smaller" : "Make bigger"} onClick={() => setTall((t) => !t)}>
          <ChevronDown className={tall ? "size-4" : "size-4 rotate-180"} />
        </IconButton>
        <IconButton label="Close test run" onClick={() => setDryRun({ open: false })}><X className="size-4" /></IconButton>
      </div>
      {d.error ? (
        <div className="flex flex-1 items-start gap-2.5 p-5 text-[13.5px] text-red-700">
          <AlertCircle className="mt-0.5 size-4 shrink-0" />
          <div>
            <p className="font-semibold">The test couldn't run</p>
            <p className="mt-0.5 text-red-600">{d.error}</p>
          </div>
        </div>
      ) : r ? (
        <>
          <div className="flex items-center gap-3 px-4 pt-3">
            <Segmented size="sm" value={tab} onChange={setTab} options={[{ value: "items", label: `Items (${r.items.length})` }, { value: "checks", label: "Checks" }, { value: "steps", label: "Steps" }]} />
            <span className="text-[12px] text-muted">{VERDICT_STYLE[r.verdict].help} Nothing was saved.</span>
          </div>
          <div className="scroll-thin flex-1 overflow-auto p-4 pt-3">
            {tab === "items" && <ItemsTable items={r.items} />}
            {tab === "checks" && <Checks report={r} />}
            {tab === "steps" && <NodeTrace report={r} flow={draft} />}
          </div>
        </>
      ) : (
        <div className="flex flex-1 items-center justify-center"><Spinner className="size-5" /></div>
      )}
    </div>
  );
}
