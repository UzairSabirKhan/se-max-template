import { useQuery } from "@tanstack/react-query";
import { CalendarClock } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { clockTime, dateTime, timeUntil } from "../lib/format";

/** "Next run in 12 min (10:06)" for a published flow on a schedule; nothing otherwise. */
export function NextRun({ flowId, withClock = false }: { flowId: string; withClock?: boolean }) {
  const q = useQuery({ queryKey: ["next-run", flowId], queryFn: () => api.nextRun(flowId), refetchInterval: 30_000 });
  const [, tick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => tick((n) => n + 1), 20_000); // keep "in N min" current between fetches
    return () => clearInterval(t);
  }, []);
  const at = q.data?.next_run_at;
  if (!at) return null;
  return (
    <span className="flex items-center gap-1.5 whitespace-nowrap text-[12.5px] text-muted" title={`Next scheduled run: ${dateTime(at)}`}>
      <CalendarClock className="size-3.5 text-brand-600" />
      Next run {timeUntil(at)}
      {withClock && <span className="text-zinc-400">· {clockTime(at)}</span>}
    </span>
  );
}
