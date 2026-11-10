import { useQueries, useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Database, ExternalLink } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { EmptyState, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { DataTab } from "../tabs/DataTab";

/** Everything the flows have saved, in one place: pick a flow on the left, browse its records on the right. */
export function DataPage() {
  const [params, setParams] = useSearchParams();
  const flows = useQuery({ queryKey: ["flows"], queryFn: api.listFlows });
  const datasets = useQueries({
    queries: (flows.data ?? []).map((f) => ({ queryKey: ["datasets", f.id], queryFn: () => api.listDatasets(f.id) })),
  });
  const loading = flows.isLoading || datasets.some((d) => d.isLoading);
  const withData = (flows.data ?? [])
    .map((f, i) => ({ flow: f, sets: datasets[i]?.data ?? [] }))
    .filter((x) => x.sets.length > 0);
  const wanted = params.get("flow");
  const current = withData.find((x) => x.flow.id === wanted) ?? withData[0];

  return (
    <div className="flex h-full flex-col">
      <header className="flex h-14 shrink-0 items-center gap-2 border-b border-line bg-white px-6">
        <Database className="size-4 text-brand-600" />
        <h1 className="text-[15px] font-semibold">Data</h1>
        <span className="text-[13px] text-muted">What your flows have saved, with each item's history</span>
      </header>
      {loading ? (
        <div className="flex flex-1 items-center justify-center"><Spinner className="size-6" /></div>
      ) : !current ? (
        <EmptyState icon={<Database className="size-5" />} title="No saved data yet" body="Add a Save records step to a flow and publish it. After the first healthy run, its items show here." />
      ) : (
        <div className="flex min-h-0 flex-1">
          <nav className="scroll-thin w-[260px] shrink-0 overflow-y-auto border-r border-line bg-white p-2" aria-label="Flows with data">
            {withData.map(({ flow, sets }) => {
              const records = sets.reduce((n, s) => n + s.record_count, 0);
              const active = flow.id === current.flow.id;
              return (
                <div key={flow.id} className={clsx("group flex items-center rounded-lg", active ? "bg-brand-50" : "hover:bg-zinc-100")}>
                  <button onClick={() => setParams({ flow: flow.id })} className="min-w-0 flex-1 px-3 py-2 text-left" aria-current={active || undefined}>
                    <span className={clsx("block truncate text-[13.5px] font-medium", active && "text-brand-700")}>{flow.name}</span>
                    <span className="block text-[12px] text-muted">
                      {sets.length} dataset{sets.length > 1 ? "s" : ""} · {records} record{records === 1 ? "" : "s"}
                    </span>
                  </button>
                  <Link to={`/flows/${flow.id}`} title="Open flow" className="mr-1.5 rounded-md p-1.5 text-zinc-400 opacity-0 hover:bg-white hover:text-ink focus:opacity-100 group-hover:opacity-100">
                    <ExternalLink className="size-3.5" />
                  </Link>
                </div>
              );
            })}
          </nav>
          <div className="min-w-0 flex-1">
            <DataTab key={current.flow.id} flowId={current.flow.id} />
          </div>
        </div>
      )}
    </div>
  );
}
