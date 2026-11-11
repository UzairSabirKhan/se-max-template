import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowUp, Bell, LayoutGrid, List, MoreHorizontal, Plus, Search, Trash2, Workflow } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Dialog, EmptyState, Pill, Select, Spinner, toast } from "../components/ui";
import { api } from "../lib/api";
import { timeAgo } from "../lib/format";
import type { FlowSummary } from "../types/contracts";

const SUGGESTIONS = [
  { label: "Track prices on the mock shop", prompt: "Track product prices on the mock shop and alert me when a price changes or a new product appears" },
  { label: "Watch three product links", prompt: "Alert me when any of these prices drops: blue kettle, steel flask and tea set" },
  { label: "Check every 30 minutes", prompt: "Track prices on the mock shop every 30 minutes" },
];

export function StatusPill({ status }: { status: FlowSummary["status"] }) {
  if (status === "published")
    return (
      <Pill tone="green">
        <span className="size-1.5 rounded-full bg-emerald-500" /> Live
      </Pill>
    );
  if (status === "paused") return <Pill tone="amber">Paused</Pill>;
  return <Pill>Draft</Pill>;
}

function nameFrom(prompt: string) {
  const p = prompt.replace(/https?:\/\/\S+/g, "").trim();
  const short = p.split(/[.,:;]/)[0].split(" ").slice(0, 6).join(" ");
  return short ? short[0].toUpperCase() + short.slice(1) : "Untitled flow";
}

export function FlowsPage() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const flows = useQuery({ queryKey: ["flows"], queryFn: api.listFlows });
  const [prompt, setPrompt] = useState("");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("all");
  const [sort, setSort] = useState("updated");
  const [view, setView] = useState<"grid" | "list">("grid");
  const [toDelete, setToDelete] = useState<FlowSummary | null>(null);

  const create = useMutation({
    mutationFn: (v: { name: string; ask?: string }) => api.createFlow(v.name).then((f) => ({ f, ask: v.ask })),
    onSuccess: ({ f, ask }) => {
      qc.invalidateQueries({ queryKey: ["flows"] });
      nav(`/flows/${f.id}${ask ? `?ask=${encodeURIComponent(ask)}` : ""}`);
    },
    onError: (e: Error) => toast.error("Couldn't create the flow", e.message),
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.deleteFlow(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["flows"] });
      toast.success("Flow deleted");
      setToDelete(null);
    },
    onError: (e: Error) => toast.error("Couldn't delete the flow", e.message),
  });

  const list = useMemo(() => {
    let l = flows.data ?? [];
    if (q) l = l.filter((f) => f.name.toLowerCase().includes(q.toLowerCase()));
    if (status !== "all") l = l.filter((f) => f.status === status);
    return [...l].sort((a, b) => (sort === "name" ? a.name.localeCompare(b.name) : sort === "alerts" ? b.unread_alerts - a.unread_alerts : b.updated_at.localeCompare(a.updated_at)));
  }, [flows.data, q, status, sort]);

  const submit = (text: string) => {
    const t = text.trim();
    if (!t) return;
    create.mutate({ name: nameFrom(t), ask: t });
  };

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <section className="mx-auto max-w-[720px] px-6 pb-10 pt-16 text-center">
        <h1 className="text-[26px] font-semibold tracking-tight">What should we watch for you?</h1>
        <p className="mt-2 text-[15px] text-muted">Describe a page and what to alert you about. The assistant builds the flow, and you review it before it goes live.</p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit(prompt);
          }}
          className="mt-7 flex items-center gap-2 rounded-2xl border border-line bg-zinc-50 p-2 pl-5 transition-shadow focus-within:border-brand-300 focus-within:bg-white focus-within:ring-4 focus-within:ring-brand-50"
        >
          <input
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Track prices on a shop page and alert me when one drops…"
            aria-label="Describe your flow"
            className="h-10 flex-1 bg-transparent text-[15px] placeholder:text-zinc-400 focus:outline-none"
          />
          <button
            type="submit"
            aria-label="Build flow"
            disabled={!prompt.trim() || create.isPending}
            className="flex size-10 items-center justify-center rounded-full bg-brand-600 text-white transition-colors hover:bg-brand-700 disabled:bg-brand-300"
          >
            {create.isPending ? <Spinner className="text-white" /> : <ArrowUp className="size-4.5" />}
          </button>
        </form>
        <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
          <span className="text-[13px] text-muted">Try:</span>
          {SUGGESTIONS.map((s) => (
            <button key={s.label} onClick={() => submit(s.prompt)} className="rounded-full border border-line bg-white px-3 py-1 text-[13px] font-medium text-zinc-700 transition-colors hover:border-zinc-300 hover:bg-zinc-50">
              {s.label}
            </button>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-[1180px] px-8 pb-16">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <h2 className="text-[17px] font-semibold">
            Your flows <span className="ml-1 font-normal text-muted">{flows.data?.length ?? ""}</span>
          </h2>
          <div className="flex-1" />
          <label className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-zinc-400" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search flows" aria-label="Search flows" className="h-9 w-52 rounded-full border border-line bg-zinc-50 pl-8 pr-3 text-[13px] focus:border-brand-300 focus:bg-white focus:outline-none" />
          </label>
          <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-36" aria-label="Filter by status">
            <option value="all">All statuses</option>
            <option value="published">Live</option>
            <option value="paused">Paused</option>
            <option value="draft">Draft</option>
          </Select>
          <Select value={sort} onChange={(e) => setSort(e.target.value)} className="w-44" aria-label="Sort">
            <option value="updated">Recently updated</option>
            <option value="alerts">Most unread alerts</option>
            <option value="name">Name</option>
          </Select>
          <div className="flex rounded-lg border border-line p-0.5">
            {(["grid", "list"] as const).map((v) => (
              <button key={v} aria-label={`${v} view`} onClick={() => setView(v)} className={clsx("flex size-7 items-center justify-center rounded-md", view === v ? "bg-zinc-100 text-ink" : "text-zinc-400 hover:text-ink")}>
                {v === "grid" ? <LayoutGrid className="size-3.5" /> : <List className="size-3.5" />}
              </button>
            ))}
          </div>
          <Button icon={<Plus className="size-4" />} onClick={() => create.mutate({ name: "Untitled flow" })}>
            New flow
          </Button>
        </div>

        {flows.isLoading ? (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(320px,1fr))] gap-4">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-[132px] animate-pulse rounded-xl border border-line bg-zinc-50" />
            ))}
          </div>
        ) : flows.isError ? (
          <EmptyState icon={<Workflow className="size-5" />} title="Couldn't load your flows" body={(flows.error as Error).message} action={<Button onClick={() => flows.refetch()}>Try again</Button>} />
        ) : !list.length ? (
          <EmptyState
            icon={<Workflow className="size-5" />}
            title={q || status !== "all" ? "No flows match" : "No flows yet"}
            body={q || status !== "all" ? "Try a different search or filter." : "Describe what to watch above, or start from an empty flow."}
          />
        ) : view === "grid" ? (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(320px,1fr))] gap-4">
            {list.map((f) => (
              <FlowCard key={f.id} flow={f} onOpen={() => nav(`/flows/${f.id}`)} onDelete={() => setToDelete(f)} />
            ))}
          </div>
        ) : (
          <div className="overflow-hidden rounded-xl border border-line">
            <table className="w-full text-[13.5px]">
              <thead className="bg-zinc-50 text-left text-[12px] font-medium uppercase tracking-wide text-muted">
                <tr>
                  <th className="px-4 py-2.5">Name</th>
                  <th className="px-4 py-2.5">Status</th>
                  <th className="px-4 py-2.5">Unread alerts</th>
                  <th className="px-4 py-2.5">Updated</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {list.map((f) => (
                  <tr key={f.id} onClick={() => nav(`/flows/${f.id}`)} className="cursor-pointer border-t border-line hover:bg-zinc-50">
                    <td className="px-4 py-3 font-medium">{f.name}</td>
                    <td className="px-4 py-3"><StatusPill status={f.status} /></td>
                    <td className="px-4 py-3">{f.unread_alerts || "—"}</td>
                    <td className="px-4 py-3 text-muted">{timeAgo(f.updated_at)}</td>
                    <td className="px-2 text-right">
                      <button aria-label={`Delete ${f.name}`} onClick={(e) => { e.stopPropagation(); setToDelete(f); }} className="rounded-md p-1.5 text-zinc-400 hover:bg-red-50 hover:text-red-600">
                        <Trash2 className="size-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <Dialog
        open={!!toDelete}
        onClose={() => setToDelete(null)}
        title="Delete this flow?"
        footer={
          <>
            <Button variant="ghost" onClick={() => setToDelete(null)}>Cancel</Button>
            <Button variant="danger" loading={remove.isPending} onClick={() => toDelete && remove.mutate(toDelete.id)}>Delete flow</Button>
          </>
        }
      >
        <strong>{toDelete?.name}</strong> and all of its runs, alerts and saved records will be deleted. This can't be undone.
      </Dialog>
    </div>
  );
}

function FlowCard({ flow, onOpen, onDelete }: { flow: FlowSummary; onOpen: () => void; onDelete: () => void }) {
  const [menu, setMenu] = useState(false);
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => e.key === "Enter" && onOpen()}
      className="group relative flex flex-col rounded-xl border border-line bg-white p-5 shadow-card transition-all hover:-translate-y-px hover:border-zinc-300 hover:shadow-pop"
    >
      <div className="flex items-start gap-3.5">
        <div className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600 ring-1 ring-brand-100">
          <Workflow className="size-5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[15px] font-semibold">{flow.name}</p>
          <p className="mt-0.5 text-[13px] text-muted">
            {flow.published_at ? `Published ${timeAgo(flow.published_at)}` : "Never published"}
          </p>
        </div>
        <div className="relative">
          <button
            aria-label="Flow actions"
            onClick={(e) => {
              e.stopPropagation();
              setMenu((m) => !m);
            }}
            className="rounded-md p-1 text-zinc-400 opacity-0 transition-opacity hover:bg-zinc-100 hover:text-ink group-hover:opacity-100 focus:opacity-100"
          >
            <MoreHorizontal className="size-4" />
          </button>
          {menu && (
            <div className="absolute right-0 top-8 z-10 w-40 rounded-lg border border-line bg-white p-1 shadow-pop" onMouseLeave={() => setMenu(false)}>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setMenu(false);
                  onDelete();
                }}
                className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-[13px] text-red-600 hover:bg-red-50"
              >
                <Trash2 className="size-3.5" /> Delete
              </button>
            </div>
          )}
        </div>
      </div>
      <div className="mt-5 flex items-center justify-between text-[12.5px] text-muted">
        <span className="flex items-center gap-1.5">
          <Bell className={clsx("size-3.5", flow.unread_alerts ? "text-orange-500" : "")} />
          {flow.unread_alerts ? <span className="font-medium text-ink">{flow.unread_alerts} unread</span> : "No new alerts"}
          <span className="text-zinc-300">·</span>
          Updated {timeAgo(flow.updated_at)}
        </span>
        <StatusPill status={flow.status} />
      </div>
    </div>
  );
}
