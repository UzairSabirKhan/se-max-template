import { useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Database, Download, History, RotateCcw, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Button, Dialog, EmptyState, IconButton, Pill, Spinner, toast } from "../components/ui";
import { api } from "../lib/api";
import { cell, dateTime, money, pct, timeAgo } from "../lib/format";
import { fieldNames, type DataRecord } from "../types/contracts";

const PAGE = 25;

function HistoryDrawer({ record, onClose }: { record: DataRecord; onClose: () => void }) {
  const h = useQuery({ queryKey: ["history", record.id], queryFn: () => api.recordHistory(record.id) });
  const title = String(record.data.title ?? record.data.name ?? record.key);
  return (
    <aside className="flex w-[360px] shrink-0 flex-col border-l border-line bg-white">
      <div className="flex items-start gap-2 border-b border-line px-4 py-3">
        <div className="min-w-0 flex-1">
          <p className="truncate text-[14.5px] font-semibold">{title}</p>
          <p className="truncate font-mono text-[11px] text-muted">{record.key}</p>
        </div>
        <IconButton label="Close history" onClick={onClose}><X className="size-4" /></IconButton>
      </div>
      <div className="scroll-thin flex-1 overflow-y-auto p-4">
        <dl className="mb-5 grid grid-cols-2 gap-2">
          {Object.entries(record.data).filter(([k]) => k !== "url").map(([k, v]) => (
            <div key={k} className="rounded-lg bg-zinc-50 p-2.5">
              <dt className="text-[11.5px] text-muted">{k}</dt>
              <dd className="truncate text-[13.5px] font-medium">{cell(k, v)}</dd>
            </div>
          ))}
        </dl>
        <p className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-zinc-400">History</p>
        {h.isLoading ? (
          <Spinner />
        ) : (
          <ol className="relative space-y-4 border-l border-line pl-4">
            {(h.data ?? []).map((c, i) => (
              <li key={i} className="relative">
                <span className={clsx("absolute -left-[21px] top-1 size-2.5 rounded-full ring-4 ring-white", c.change === "new" ? "bg-emerald-500" : c.change === "removed" ? "bg-red-500" : "bg-sky-500")} />
                <p className="text-[12px] text-muted">{dateTime(c.at)}</p>
                {c.change === "changed" ? (
                  <p className="text-[13.5px]">
                    <span className="font-medium">{c.field}</span>: {c.field?.includes("price") ? money(c.old_value) : String(c.old_value)} → <strong>{c.field?.includes("price") ? money(c.new_value) : String(c.new_value)}</strong>
                    {c.pct_change != null && <span className={clsx("ml-1.5 text-[12.5px] font-medium", c.pct_change < 0 ? "text-emerald-700" : "text-red-600")}>{pct(c.pct_change)}</span>}
                  </p>
                ) : (
                  <p className="text-[13.5px]">{c.change === "new" ? "First seen" : "Removed from the page"}</p>
                )}
              </li>
            ))}
          </ol>
        )}
      </div>
    </aside>
  );
}

export function DataTab({ flowId }: { flowId: string }) {
  const qc = useQueryClient();
  const ds = useQuery({ queryKey: ["datasets", flowId], queryFn: () => api.listDatasets(flowId) });
  const [dsId, setDsId] = useState<string | null>(null);
  const [sort, setSort] = useState<string>("");
  const [page, setPage] = useState(0);
  const [open, setOpen] = useState<DataRecord | null>(null);
  const [reset, setReset] = useState(false);
  useEffect(() => {
    if (ds.data?.length && !ds.data.some((d) => d.id === dsId)) setDsId(ds.data[0].id);
  }, [ds.data, dsId]);
  const dataset = ds.data?.find((d) => d.id === dsId);
  const fields = dataset ? fieldNames(dataset) : [];
  const recs = useQuery({
    queryKey: ["records", dsId, sort, page],
    queryFn: () => api.listRecords(dsId!, { sort: sort || undefined, limit: PAGE, offset: page * PAGE }),
    enabled: !!dsId,
  });

  if (ds.isLoading) return <div className="flex h-full items-center justify-center"><Spinner className="size-6" /></div>;
  if (!ds.data?.length || !dataset)
    return <EmptyState icon={<Database className="size-5" />} title="No saved data yet" body="Add a Save records step and publish. After the first healthy run, every item shows here with its history." />;

  const toggleSort = (k: string) => {
    setPage(0);
    setSort(sort === k ? `-${k}` : sort === `-${k}` ? "" : k);
  };
  const total = recs.data?.total ?? 0;

  return (
    <div className="flex h-full">
      <div className="scroll-thin min-w-0 flex-1 overflow-y-auto p-6">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <div className="flex gap-1 rounded-lg bg-zinc-100 p-0.5">
            {ds.data.map((d) => (
              <button key={d.id} onClick={() => { setDsId(d.id); setPage(0); setOpen(null); }} className={clsx("h-7 rounded-md px-3 font-mono text-[12.5px] font-medium", d.id === dsId ? "bg-white shadow-sm" : "text-zinc-500 hover:text-ink")}>
                {d.name}
              </button>
            ))}
          </div>
          <span className="text-[13px] text-muted">{dataset.record_count} records · identified by <span className="font-mono">{dataset.identity_key}</span></span>
          <div className="flex-1" />
          <a href={api.exportCsvUrl(dataset.id)} download={`${dataset.name}.csv`}>
            <Button size="sm" icon={<Download className="size-3.5" />}>CSV</Button>
          </a>
          <Button size="sm" variant="ghost" icon={<RotateCcw className="size-3.5" />} onClick={() => setReset(true)}>Reset data</Button>
        </div>
        <p className="mb-3 text-[12.5px] text-muted">These are the last good values. A broken or blocked run never overwrites them.</p>
        <div className="overflow-hidden rounded-xl border border-line bg-white">
          <table className="w-full text-[13px]">
            <thead className="bg-zinc-50 text-left text-[12px] font-medium text-muted">
              <tr>
                {[...fields, "last_changed"].map((f) => (
                  <th key={f} className="px-3 py-2.5">
                    <button onClick={() => toggleSort(f)} className="flex items-center gap-1 hover:text-ink">
                      {f === "last_changed" ? "Last changed" : f}
                      {sort === f ? <ArrowUp className="size-3" /> : sort === `-${f}` ? <ArrowDown className="size-3" /> : null}
                    </button>
                  </th>
                ))}
                <th className="w-10" />
              </tr>
            </thead>
            <tbody>
              {recs.isLoading ? (
                <tr><td colSpan={fields.length + 2} className="py-10 text-center"><Spinner className="mx-auto" /></td></tr>
              ) : (
                recs.data?.records.map((r) => (
                  <tr key={r.id} onClick={() => setOpen(r)} className={clsx("cursor-pointer border-t border-line", open?.id === r.id ? "bg-brand-50/50" : "hover:bg-zinc-50", r.removed_at && "text-zinc-400 line-through")}>
                    {fields.map((f) => (
                      <td key={f} className={clsx("max-w-[280px] truncate px-3 py-2.5", f === "url" && "font-mono text-[11.5px] text-muted", /price/.test(f) && "font-medium tabular-nums")}>{cell(f, r.data[f])}</td>
                    ))}
                    <td className="px-3 py-2.5 text-muted">{r.last_changed ? <Pill tone="blue">{timeAgo(r.last_changed)}</Pill> : "—"}</td>
                    <td className="pr-3 text-zinc-400"><History className="size-3.5" /></td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
          {total > PAGE && (
            <div className="flex items-center justify-end gap-2 border-t border-line px-3 py-2 text-[12.5px] text-muted">
              {page * PAGE + 1}–{Math.min(total, (page + 1) * PAGE)} of {total}
              <IconButton label="Previous page" disabled={page === 0} onClick={() => setPage(page - 1)}><ChevronLeft className="size-4" /></IconButton>
              <IconButton label="Next page" disabled={(page + 1) * PAGE >= total} onClick={() => setPage(page + 1)}><ChevronRight className="size-4" /></IconButton>
            </div>
          )}
        </div>
      </div>
      {open && <HistoryDrawer record={open} onClose={() => setOpen(null)} />}
      <Dialog
        open={reset}
        onClose={() => setReset(false)}
        title={`Reset “${dataset.name}”?`}
        footer={
          <>
            <Button variant="ghost" onClick={() => setReset(false)}>Cancel</Button>
            <Button
              variant="danger"
              onClick={async () => {
                setReset(false);
                await api.resetDataset(dataset.id);
                setOpen(null);
                qc.invalidateQueries({ queryKey: ["datasets", flowId] });
                qc.invalidateQueries({ queryKey: ["records", dataset.id] });
                toast.success("Data reset", "The next healthy run saves a new baseline.");
              }}
            >
              Reset data
            </Button>
          </>
        }
      >
        All {dataset.record_count} records and their history are deleted. The next healthy run saves a fresh baseline without alerts. This can't be undone.
      </Dialog>
    </div>
  );
}
