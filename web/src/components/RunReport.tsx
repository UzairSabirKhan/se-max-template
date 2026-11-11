import clsx from "clsx";
import { ArrowDownRight, ArrowUpRight, CheckCircle2, Globe, MinusCircle, XCircle } from "lucide-react";
import { bytes, cell, money, pct } from "../lib/format";
import { NODE_META } from "../lib/nodeMeta";
import type { ChangeLabel, Flow, Item, RunReport } from "../types/contracts";
import { Pill } from "./ui";

const CHANGE: Record<ChangeLabel, { tone: "green" | "blue" | "zinc" | "red" | "amber"; label: string }> = {
  new: { tone: "green", label: "New" },
  changed: { tone: "blue", label: "Changed" },
  same: { tone: "zinc", label: "Same" },
  removed: { tone: "red", label: "Removed" },
  suspect: { tone: "amber", label: "Suspect" },
};

export function ChangeBadge({ change }: { change?: ChangeLabel }) {
  if (!change) return null;
  return <Pill tone={CHANGE[change].tone} className="text-[11px]">{CHANGE[change].label}</Pill>;
}

export function ItemsTable({ items, max = 100 }: { items: Item[]; max?: number }) {
  if (!items.length) return <p className="py-6 text-center text-[13px] text-muted">No items.</p>;
  const cols = [...new Set(items.flatMap((i) => Object.keys(i.data)))];
  return (
    <div className="overflow-auto rounded-lg border border-line">
      <table className="w-full text-[12.5px]">
        <thead className="sticky top-0 bg-zinc-50 text-left text-[11.5px] font-medium text-muted">
          <tr>
            <th className="w-[84px] px-3 py-2">Change</th>
            {cols.map((c) => <th key={c} className="px-3 py-2">{c}</th>)}
          </tr>
        </thead>
        <tbody>
          {items.slice(0, max).map((it) => (
            <tr key={it.key} className="border-t border-line align-top">
              <td className="px-3 py-2"><ChangeBadge change={it.change} /></td>
              {cols.map((c) => {
                const v = it.data[c];
                const prev = it.previous?.[c];
                const p = it.pct_change?.[c];
                return (
                  <td key={c} className={clsx("max-w-[260px] px-3 py-2", v == null && "text-red-500")}>
                    {/* Scraped text is rendered as text only (never as HTML). */}
                    <span className={clsx("block truncate", c === "url" && "font-mono text-[11.5px] text-zinc-500")} title={v == null ? "missing" : String(v)}>
                      {v == null ? "missing" : cell(c, v)}
                    </span>
                    {prev !== undefined && (
                      <span className="mt-0.5 flex items-center gap-1 text-[11.5px] text-muted">
                        was {money(prev)}
                        {p !== undefined && (
                          <span className={clsx("inline-flex items-center font-medium", p < 0 ? "text-emerald-700" : "text-red-600")}>
                            {p < 0 ? <ArrowDownRight className="size-3" /> : <ArrowUpRight className="size-3" />}
                            {pct(p)}
                          </span>
                        )}
                      </span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {items.length > max && <p className="border-t border-line px-3 py-2 text-[12px] text-muted">Showing {max} of {items.length}.</p>}
    </div>
  );
}

export function Checks({ report }: { report: RunReport }) {
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <section>
        <h4 className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-zinc-400">Evidence</h4>
        <ul className="space-y-1.5">
          {report.evidence.map((e, i) => (
            <li key={i} className="flex items-start gap-1.5 text-[13px]">
              {["OK", "CHANGED"].includes(report.verdict) ? <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-emerald-600" /> : <XCircle className="mt-0.5 size-3.5 shrink-0 text-red-500" />}
              {e}
            </li>
          ))}
          {!report.evidence.length && <li className="text-[13px] text-muted">None recorded.</li>}
        </ul>
      </section>
      <section>
        <h4 className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-zinc-400">Field coverage</h4>
        <div className="space-y-2">
          {Object.entries(report.coverage).map(([f, v]) => (
            <div key={f}>
              <div className="flex justify-between text-[12.5px]">
                <span className="font-medium">{f}</span>
                <span className={v < 1 ? "font-medium text-red-600" : "text-muted"}>{Math.round(v * 100)}%</span>
              </div>
              <div className="mt-1 h-1.5 rounded-full bg-zinc-100">
                <div className={clsx("h-full rounded-full", v === 1 ? "bg-emerald-500" : v > 0.5 ? "bg-amber-500" : "bg-red-500")} style={{ width: `${Math.max(2, v * 100)}%` }} />
              </div>
            </div>
          ))}
          {!Object.keys(report.coverage).length && <p className="text-[13px] text-muted">No fields read.</p>}
        </div>
      </section>
      <section>
        <h4 className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-zinc-400">Pages fetched</h4>
        <ul className="space-y-1.5">
          {report.http.map((h, i) => (
            <li key={i} className="flex items-center gap-2 text-[12.5px]">
              <Globe className="size-3.5 shrink-0 text-zinc-400" />
              <span className="min-w-0 flex-1 truncate font-mono text-[11.5px]" title={h.url}>{h.url.replace(/^https?:\/\//, "")}</span>
              <Pill tone={h.status && h.status < 300 ? "green" : "red"} className="text-[11px]">{h.status ?? "—"}</Pill>
              <span className="w-14 text-right text-muted">{bytes(h.body_size)}</span>
            </li>
          ))}
          {!report.http.length && <li className="text-[13px] text-muted">No pages fetched.</li>}
        </ul>
      </section>
    </div>
  );
}

export function NodeTrace({ report, flow }: { report: RunReport; flow: Flow | null }) {
  return (
    <ol className="space-y-1">
      {report.node_trace.map((t, i) => {
        const node = flow?.nodes.find((n) => n.id === t.node_id);
        const meta = node ? NODE_META[node.type] : null;
        return (
          <li key={t.node_id} className={clsx("flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-[13px]", t.status === "error" && "bg-red-50")}>
            {t.status === "ok" ? <CheckCircle2 className="size-4 text-emerald-600" /> : t.status === "error" ? <XCircle className="size-4 text-red-500" /> : <MinusCircle className="size-4 text-zinc-300" />}
            <span className={clsx("flex-1", t.status === "skipped" && "text-zinc-400")}>
              {i + 1}. {meta?.label ?? t.node_id}
              {t.note && <span className="ml-2 text-[12px] text-muted">{t.note}</span>}
            </span>
            <span className="font-mono text-[11.5px] text-muted">{t.status === "skipped" ? "skipped" : `${t.items_in} → ${t.items_out}`}</span>
          </li>
        );
      })}
    </ol>
  );
}
