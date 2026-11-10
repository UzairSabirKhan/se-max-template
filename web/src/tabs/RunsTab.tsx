import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { CalendarClock, FlaskConical, Hand, History, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { Checks, ItemsTable, NodeTrace } from "../components/RunReport";
import { EmptyState, Pill, Spinner, VERDICT_STYLE, VerdictBadge } from "../components/ui";
import { api } from "../lib/api";
import { NextRun } from "../components/NextRun";
import { dateTime, duration, timeAgo } from "../lib/format";
import type { Flow, RunSummary } from "../types/contracts";

const TRIGGER = {
  schedule: { icon: CalendarClock, label: "Schedule" },
  manual: { icon: Hand, label: "Run now" },
  dry_run: { icon: FlaskConical, label: "Test" },
};

function Changes({ c }: { c: RunSummary["changes"] }) {
  if (!c.new && !c.changed && !c.removed) return <span className="text-muted">no changes</span>;
  return (
    <span className="flex gap-2 font-medium">
      {!!c.new && <span className="text-emerald-700">+{c.new} new</span>}
      {!!c.changed && <span className="text-sky-700">~{c.changed} changed</span>}
      {!!c.removed && <span className="text-red-600">−{c.removed} removed</span>}
    </span>
  );
}

export function RunsTab({ flowId, flow }: { flowId: string; flow: Flow }) {
  const runs = useQuery({ queryKey: ["runs", flowId], queryFn: () => api.listRuns(flowId, 20), refetchInterval: 15_000 });
  const [sel, setSel] = useState<string | null>(null);
  useEffect(() => {
    if (!sel && runs.data?.length) setSel(runs.data[0].id);
  }, [runs.data, sel]);
  const report = useQuery({ queryKey: ["run", sel], queryFn: () => api.getRun(sel!), enabled: !!sel });

  if (runs.isLoading) return <div className="flex h-full items-center justify-center"><Spinner className="size-6" /></div>;
  if (!runs.data?.length)
    return <EmptyState icon={<History className="size-5" />} title="No runs yet" body="Publish the flow and it runs on its schedule. Each run shows here with its verdict and evidence." />;

  const r = report.data;
  return (
    <div className="flex h-full">
      <div className="scroll-thin w-[400px] shrink-0 overflow-y-auto border-r border-line bg-white">
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-line bg-white/95 px-4 py-3 backdrop-blur">
          <p className="text-[14px] font-semibold">Run history</p>
          <span className="flex items-center gap-1 text-[12px] text-emerald-700"><ShieldCheck className="size-3.5" /> 0 AI calls in every run</span>
        </div>
        <div className="border-b border-line px-4 py-2 empty:hidden">
          <NextRun flowId={flowId} withClock />
        </div>
        <ul>
          {runs.data.map((run) => {
            const T = TRIGGER[run.trigger];
            return (
              <li key={run.id}>
                <button onClick={() => setSel(run.id)} className={clsx("w-full border-b border-line px-4 py-3 text-left transition-colors", sel === run.id ? "bg-brand-50/50" : "hover:bg-zinc-50")}>
                  <div className="flex items-center gap-2">
                    <VerdictBadge verdict={run.verdict} size="sm" />
                    <span className="flex items-center gap-1 text-[12px] text-muted"><T.icon className="size-3" /> {T.label}</span>
                    <span className="ml-auto text-[12px] text-muted" title={dateTime(run.started_at)}>{timeAgo(run.started_at)}</span>
                  </div>
                  <p className="mt-1 truncate text-[13px]">{run.reason}</p>
                  <div className="mt-1 flex items-center gap-3 text-[12px] text-muted">
                    <span>{run.items_found} items</span>
                    <Changes c={run.changes} />
                    <span className="ml-auto">{duration(run.duration_ms)}</span>
                    <span title="AI calls in this run">AI calls: {run.ai_calls}</span>
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
      <div className="scroll-thin min-w-0 flex-1 overflow-y-auto p-6">
        {!r ? (
          <div className="flex h-full items-center justify-center"><Spinner className="size-6" /></div>
        ) : (
          <div className="mx-auto max-w-[1000px] space-y-5">
            <div className="flex flex-wrap items-start gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <VerdictBadge verdict={r.verdict} />
                  <span className="text-[12.5px] text-muted">{dateTime(r.started_at)} · {TRIGGER[r.trigger].label}</span>
                </div>
                <h2 className="mt-1.5 text-[18px] font-semibold">{r.reason}</h2>
                <p className="text-[13px] text-muted">{VERDICT_STYLE[r.verdict].help}</p>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
              {[
                ["Items found", r.items_found],
                ["Valid", r.items_valid],
                ["Changes", r.changes.new + r.changes.changed + r.changes.removed],
                ["Duration", duration(r.duration_ms)],
              ].map(([k, v]) => (
                <div key={k} className="rounded-xl border border-line bg-white p-3.5">
                  <p className="text-[12px] text-muted">{k}</p>
                  <p className="mt-0.5 text-[20px] font-semibold tabular-nums">{v}</p>
                </div>
              ))}
              <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-3.5">
                <p className="flex items-center gap-1 text-[12px] text-emerald-800"><ShieldCheck className="size-3.5" /> AI calls</p>
                <p className="mt-0.5 text-[20px] font-semibold tabular-nums text-emerald-800">{r.ai_calls}</p>
              </div>
            </div>
            <section className="rounded-xl border border-line bg-white p-4"><Checks report={r} /></section>
            <div className="grid gap-5 lg:grid-cols-[320px_1fr]">
              <section className="rounded-xl border border-line bg-white p-3">
                <h3 className="mb-2 px-1 text-[13.5px] font-semibold">Steps</h3>
                <NodeTrace report={r} flow={flow} />
              </section>
              <section className="min-w-0 space-y-3">
                {r.iterations && r.iterations.length > 0 && (
                  <div className="rounded-xl border border-line bg-white p-3">
                    <h3 className="mb-2 text-[13.5px] font-semibold">Loop iterations</h3>
                    <table className="w-full text-[12.5px]">
                      <tbody>
                        {r.iterations.map((it) => (
                          <tr key={it.index} className="border-t border-line first:border-0">
                            <td className="w-8 py-1.5 text-muted">{it.index + 1}</td>
                            <td className="truncate py-1.5 font-mono text-[11.5px]">{it.key.replace(/^https?:\/\//, "")}</td>
                            <td className="py-1.5 text-right"><Pill tone={it.status === "ok" ? "green" : it.status === "error" ? "red" : "zinc"}>{it.status}</Pill></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <div>
                  <h3 className="mb-2 text-[13.5px] font-semibold">Items <span className="font-normal text-muted">{r.items.length}</span></h3>
                  {r.items.length ? <ItemsTable items={r.items} /> : <p className="rounded-xl border border-dashed border-line p-6 text-center text-[13px] text-muted">Nothing was saved in this run. Your last good data is kept.</p>}
                </div>
              </section>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
