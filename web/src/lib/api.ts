import { fetchEventSource } from "@microsoft/fetch-event-source";
import type {
  AgentEvent,
  Alert,
  ApiErrorBody,
  DataSelector,
  ChatTurn,
  DataRecord,
  Dataset,
  Flow,
  FlowDetail,
  FlowSummary,
  NodeTypeInfo,
  RecordChange,
  RunReport,
  RunStreamEvent,
  RunSummary,
} from "../types/contracts";
import { createMockApi } from "../mocks/mockApi";
import { ApiError, friendly } from "./errors";

export { ApiError };

export type AgentRequest = { message: string; draft: Flow; selected_node_ids: string[]; history: ChatTurn[] };

export interface Api {
  mode: "mock" | "live";
  nodeTypes(): Promise<NodeTypeInfo[]>;
  listFlows(): Promise<FlowSummary[]>;
  createFlow(name: string): Promise<FlowDetail>;
  getFlow(id: string): Promise<FlowDetail>;
  saveFlow(id: string, body: { name?: string; draft: Flow }): Promise<FlowDetail>;
  deleteFlow(id: string): Promise<void>;
  dryRun(id: string, draft: Flow, until_node?: string): Promise<RunReport>;
  dataSelector(id: string, draft: Flow, nodeId: string): Promise<DataSelector>;
  publish(id: string): Promise<FlowDetail>;
  pause(id: string): Promise<FlowDetail>;
  unpublish(id: string): Promise<FlowDetail>;
  runNow(id: string): Promise<{ run_id: string }>;
  listRuns(flowId: string, limit?: number): Promise<RunSummary[]>;
  getRun(runId: string): Promise<RunReport>;
  streamRun(runId: string, onEvent: (e: RunStreamEvent) => void, signal: AbortSignal): Promise<void>;
  listAlerts(flowId: string): Promise<Alert[]>;
  markAlertRead(alertId: string): Promise<void>;
  listDatasets(flowId: string): Promise<Dataset[]>;
  listRecords(datasetId: string, q: { sort?: string; limit?: number; offset?: number }): Promise<{ total: number; records: DataRecord[] }>;
  recordHistory(recordId: string): Promise<RecordChange[]>;
  resetDataset(datasetId: string): Promise<void>;
  exportCsvUrl(datasetId: string): string;
  agent(flowId: string, body: AgentRequest, onEvent: (e: AgentEvent) => void, signal: AbortSignal): Promise<void>;
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, { error: "network", message: "Can't reach the server. Check your connection." });
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!res.ok) throw new ApiError(res.status, data && data.error ? data : { error: "http_" + res.status });
  return data as T;
}

function createLiveApi(): Api {
  return {
    mode: "live",
    nodeTypes: () => req("GET", "/api/node-types"),
    listFlows: () => req("GET", "/api/flows"),
    createFlow: (name) => req("POST", "/api/flows", { name }),
    getFlow: (id) => req("GET", `/api/flows/${id}`),
    saveFlow: (id, body) => req("PUT", `/api/flows/${id}`, body),
    deleteFlow: (id) => req("DELETE", `/api/flows/${id}`),
    dryRun: (id, draft, until_node) => req("POST", `/api/flows/${id}/dry-run`, { draft, until_node }),
    dataSelector: (id, draft, nodeId) => req("POST", `/api/flows/${id}/data-selector`, { draft, node_id: nodeId }),
    publish: (id) => req("POST", `/api/flows/${id}/publish`),
    pause: (id) => req("POST", `/api/flows/${id}/pause`),
    unpublish: (id) => req("POST", `/api/flows/${id}/unpublish`),
    runNow: (id) => req("POST", `/api/flows/${id}/run`),
    listRuns: (flowId, limit = 20) => req("GET", `/api/flows/${flowId}/runs?limit=${limit}`),
    getRun: (runId) => req("GET", `/api/runs/${runId}`),
    streamRun: (runId, onEvent, signal) =>
      new Promise<void>((resolve) => {
        const es = new EventSource(`/api/runs/${runId}/stream`);
        const done = () => {
          es.close();
          resolve();
        };
        signal.addEventListener("abort", done);
        for (const name of ["node_started", "node_finished", "iteration", "finished"] as const) {
          es.addEventListener(name, (m) => {
            onEvent({ event: name, data: JSON.parse((m as MessageEvent).data) } as RunStreamEvent);
            if (name === "finished") done();
          });
        }
        es.onerror = done;
      }),
    listAlerts: (flowId) => req("GET", `/api/flows/${flowId}/alerts`),
    markAlertRead: (id) => req("POST", `/api/alerts/${id}/read`),
    listDatasets: (flowId) => req("GET", `/api/flows/${flowId}/datasets`),
    listRecords: (id, q) => {
      const p = new URLSearchParams();
      if (q.sort) p.set("sort", q.sort);
      if (q.limit) p.set("limit", String(q.limit));
      if (q.offset) p.set("offset", String(q.offset));
      return req("GET", `/api/datasets/${id}/records?${p}`);
    },
    recordHistory: (id) => req("GET", `/api/records/${id}/history`),
    resetDataset: (id) => req("POST", `/api/datasets/${id}/reset`),
    exportCsvUrl: (id) => `/api/datasets/${id}/export.csv`,
    agent: async (flowId, body, onEvent, signal) => {
      await fetchEventSource(`/api/flows/${flowId}/agent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal,
        openWhenHidden: true,
        async onopen(res) {
          if (res.ok) return;
          let data: ApiErrorBody = { error: "ai_unavailable" };
          try {
            data = await res.json();
          } catch {
            /* keep default */
          }
          const code = res.status === 429 ? "rate_limited" : (data.error as any) || "ai_unavailable";
          onEvent({ event: "error", data: { code, message: data.message || friendly(code) } });
          throw new ApiError(res.status, data);
        },
        onmessage(m) {
          if (!m.event) return;
          onEvent({ event: m.event, data: m.data ? JSON.parse(m.data) : {} } as AgentEvent);
        },
        onerror(err) {
          throw err; // no automatic retry: one message, one stream
        },
      }).catch(() => undefined);
    },
  };
}

// Live (the real FastAPI backend) unless mock is asked for explicitly. Defaulting to mock would
// make a production build show invented data from the in-browser fake API.
export const api: Api = import.meta.env.VITE_API_MODE === "mock" ? createMockApi() : createLiveApi();
