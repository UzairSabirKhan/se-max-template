import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useEditor } from "../store/editor";
import type { DataSelector, SelectorField } from "../types/contracts";

/** What the selected step can use from the steps before it (POST /api/flows/{id}/data-selector).
 *  The draft is debounced so typing in a setting doesn't send a request per key. */
export function useStepData(nodeId: string | null) {
  const flowId = useEditor((s) => s.flowId);
  const draft = useEditor((s) => s.draft);
  const [settled, setSettled] = useState(draft);
  useEffect(() => {
    const t = setTimeout(() => setSettled(draft), 400);
    return () => clearTimeout(t);
  }, [draft]);

  const q = useQuery<DataSelector>({
    queryKey: ["data-selector", flowId, nodeId, settled],
    queryFn: () => api.dataSelector(flowId!, settled, nodeId!),
    enabled: !!flowId && !!nodeId,
    staleTime: 10_000,
    retry: false,
    placeholderData: (previous) => previous,
  });

  const groups = q.data?.groups ?? [];
  const fields: SelectorField[] = groups.flatMap((g) => g.fields).filter((f) => f.type !== "change");
  const hasChange = groups.some((g) => g.fields.some((f) => f.type === "change"));
  return { data: q.data, groups, fields, hasChange, loading: q.isLoading, error: q.isError, variables: q.data?.variables ?? [] };
}

/** "Rs 1,250" style sample text for a picker row. */
export function sampleText(value: unknown): string {
  if (value === null || value === undefined || value === "") return "";
  if (Array.isArray(value)) return `${value.length} item${value.length === 1 ? "" : "s"}`;
  const s = String(value);
  return s.length > 40 ? s.slice(0, 39) + "…" : s;
}
