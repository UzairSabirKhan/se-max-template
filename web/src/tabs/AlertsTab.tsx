import { useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { AlertOctagon, AlertTriangle, Bell, CheckCheck, Info } from "lucide-react";
import { useState } from "react";
import { ItemsTable } from "../components/RunReport";
import { Button, EmptyState, Pill, Segmented, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { dateTime, timeAgo } from "../lib/format";
import type { Alert } from "../types/contracts";

const LEVEL = {
  info: { icon: Info, bar: "bg-sky-500", tile: "bg-sky-50 text-sky-600" },
  warning: { icon: AlertTriangle, bar: "bg-amber-500", tile: "bg-amber-50 text-amber-600" },
  error: { icon: AlertOctagon, bar: "bg-red-500", tile: "bg-red-50 text-red-600" },
};
const KIND: Record<Alert["kind"], string> = { condition: "Your rule", site_changed: "Site changed", blocked: "Blocked", unsupported: "Unsupported", suspect: "Suspect value" };

export function AlertsTab({ flowId }: { flowId: string }) {
  const qc = useQueryClient();
  const alerts = useQuery({ queryKey: ["alerts", flowId], queryFn: () => api.listAlerts(flowId), refetchInterval: 10_000 });
  const [filter, setFilter] = useState<"all" | "unread">("all");
  const [open, setOpen] = useState<string | null>(null);

  const markRead = async (ids: string[]) => {
    qc.setQueryData<Alert[]>(["alerts", flowId], (old) => old?.map((a) => (ids.includes(a.id) ? { ...a, read: true } : a)));
    await Promise.all(ids.map((id) => api.markAlertRead(id)));
    qc.invalidateQueries({ queryKey: ["flows"] });
  };

  if (alerts.isLoading) return <div className="flex h-full items-center justify-center"><Spinner className="size-6" /></div>;
  const list = (alerts.data ?? []).filter((a) => filter === "all" || !a.read);
  const unread = (alerts.data ?? []).filter((a) => !a.read);

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-[820px] px-6 py-6">
        <div className="mb-4 flex items-center gap-3">
          <h2 className="text-[17px] font-semibold">Alerts</h2>
          <Segmented size="sm" value={filter} onChange={setFilter} options={[{ value: "all", label: "All" }, { value: "unread", label: `Unread (${unread.length})` }]} />
          <span className="text-[12px] text-muted">Checks for new alerts every 10 s</span>
          <div className="flex-1" />
          <Button size="sm" variant="ghost" icon={<CheckCheck className="size-3.5" />} disabled={!unread.length} onClick={() => markRead(unread.map((a) => a.id))}>Mark all read</Button>
        </div>
        {!list.length ? (
          <EmptyState icon={<Bell className="size-5" />} title={filter === "unread" ? "You're all caught up" : "No alerts yet"} body="Alerts appear when your rules match, and when the site breaks, blocks us, or a value looks wrong." />
        ) : (
          <ul className="space-y-2.5">
            {list.map((a) => {
              const L = LEVEL[a.level];
              return (
                <li key={a.id} className={clsx("relative overflow-hidden rounded-xl border bg-white shadow-card", a.read ? "border-line" : "border-zinc-300")}>
                  <span className={clsx("absolute inset-y-0 left-0 w-1", L.bar, a.read && "opacity-30")} />
                  <div className="flex gap-3 p-4 pl-5">
                    <div className={clsx("flex size-9 shrink-0 items-center justify-center rounded-lg", L.tile)}><L.icon className="size-4" /></div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <p className={clsx("text-[14px]", a.read ? "font-medium text-zinc-700" : "font-semibold")}>{a.title}</p>
                        <Pill className="text-[11px]">{KIND[a.kind]}</Pill>
                        {!a.read && <span className="size-2 rounded-full bg-brand-600" aria-label="Unread" />}
                        <span className="ml-auto shrink-0 text-[12px] text-muted" title={dateTime(a.created_at)}>{timeAgo(a.created_at)}</span>
                      </div>
                      {/* Messages contain scraped text: rendered as plain text. */}
                      <p className="mt-1 text-[13.5px] text-zinc-700">{a.message}</p>
                      <div className="mt-2 flex items-center gap-3">
                        {a.items.length > 0 && (
                          <button onClick={() => setOpen(open === a.id ? null : a.id)} className="text-[12.5px] font-medium text-brand-700 hover:underline">
                            {open === a.id ? "Hide" : "Show"} {a.items.length} item{a.items.length > 1 ? "s" : ""}
                          </button>
                        )}
                        {!a.read && <button onClick={() => markRead([a.id])} className="text-[12.5px] font-medium text-zinc-500 hover:text-ink">Mark read</button>}
                      </div>
                      {open === a.id && <div className="mt-3"><ItemsTable items={a.items} /></div>}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
