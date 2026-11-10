// Hand copy of specs/contracts.md (C1, C2, C3, C5).
// When scripts/export_schema.py starts writing web/src/types/flow.ts, import the
// Flow types from there instead and delete the C1 block below.

// ---------- C1. Flow document ----------
export type NodeType =
  | "trigger"
  | "fetch_page"
  | "paginate"
  | "extract_list"
  | "for_each"
  | "fetch_item_page"
  | "extract_fields"
  | "condition"
  | "wait"
  | "check_page"
  | "save_records"
  | "alert"
  | "results"
  | "click"
  | "scroll"
  | "type"
  | "wait_for_element";

export type VariableType = "text" | "number" | "price" | "boolean" | "url" | "url_list" | "text_list";
export type Variable = { name: string; type: VariableType; value: unknown };
export type VarRef = { var: string };

export type FlowNode = {
  id: string;
  type: NodeType;
  parentId?: string;
  position: { x: number; y: number };
  config: Record<string, any>;
};

export type SourceHandle = "true" | "false" | "item" | "done";
export type FlowEdge = {
  id: string;
  source: string;
  target: string;
  sourceHandle?: SourceHandle;
  targetHandle?: "next";
};

export type Flow = {
  version: number;
  variables: Variable[];
  nodes: FlowNode[];
  edges: FlowEdge[];
};

// ---------- C2. Validation errors ----------
export type Issue = { node_id: string | null; path: string; message: string };

// ---------- C3. REST shapes ----------
export type FlowStatus = "draft" | "published" | "paused";

export type FlowSummary = {
  id: string;
  name: string;
  status: FlowStatus;
  unread_alerts: number;
  updated_at: string;
  published_at: string | null;
};

export type FlowDetail = {
  id: string;
  name: string;
  status: FlowStatus;
  draft: Flow;
  published: Flow | null;
  published_at: string | null;
};

export type NodeTypeInfo = {
  type: NodeType;
  group: string;
  label: string;
  disabled: boolean;
  config_schema: Record<string, unknown>;
};

export type Verdict = "BLOCKED" | "UNSUPPORTED" | "BROKEN" | "SUSPECT" | "CHANGED" | "OK" | "UNKNOWN";
export type ChangeLabel = "new" | "changed" | "same" | "removed" | "suspect";

export type RunSummary = {
  id: string;
  flow_id: string;
  trigger: "schedule" | "manual" | "dry_run";
  verdict: Verdict;
  reason: string;
  started_at: string;
  duration_ms: number;
  items_found: number;
  items_valid: number;
  changes: { new: number; changed: number; removed: number };
  ai_calls: 0;
};

export type Item = {
  key: string;
  data: Record<string, string | number | null>;
  change?: ChangeLabel;
  previous?: Record<string, unknown>;
  pct_change?: Record<string, number>;
};

export type RunReport = RunSummary & {
  evidence: string[];
  http: { url: string; status: number | null; body_size: number; error?: string }[];
  coverage: Record<string, number>;
  node_trace: { node_id: string; items_in: number; items_out: number; status: "ok" | "skipped" | "error"; note?: string }[];
  iterations?: { node_id: string; index: number; key: string; status: "ok" | "error" | "dropped"; error?: string }[];
  items: Item[];
};

export type Alert = {
  id: string;
  flow_id: string;
  run_id: string;
  node_id: string | null;
  kind: "condition" | "site_changed" | "blocked" | "unsupported" | "suspect";
  level: "info" | "warning" | "error";
  title: string;
  message: string;
  items: Item[];
  created_at: string;
  read: boolean;
};

export type Dataset = { id: string; name: string; identity_key: string; fields: string[]; record_count: number };

export type DataRecord = {
  id: string;
  key: string;
  data: Record<string, unknown>;
  first_seen: string;
  last_changed: string | null;
  removed_at: string | null;
};

export type RecordChange = {
  run_id: string;
  at: string;
  change: "new" | "changed" | "removed";
  field: string | null;
  old_value: unknown;
  new_value: unknown;
  pct_change: number | null;
};

export type ApiErrorBody = { error: string; message?: string; issues?: Issue[] };

// ---------- SSE: run stream ----------
export type RunStreamEvent =
  | { event: "node_started"; data: { node_id: string } }
  | { event: "node_finished"; data: { node_id: string; items_in: number; items_out: number } }
  | { event: "iteration"; data: { node_id: string; index: number; key: string; status: string } }
  | { event: "finished"; data: RunSummary };

// ---------- C5. Agent stream ----------
export type FlowOp =
  | { op: "add_node"; node: FlowNode }
  | { op: "update_node"; id: string; config: Record<string, any> }
  | { op: "remove_node"; id: string }
  | { op: "add_edge"; edge: FlowEdge }
  | { op: "remove_edge"; id: string }
  | { op: "set_variable"; variable: Variable }
  | { op: "remove_variable"; name: string };

export type AgentErrorCode = "ai_unavailable" | "invalid_ai_reply" | "rate_limited" | "tool_failed";

export type AgentEvent =
  | { event: "text"; data: { delta: string } }
  | { event: "tool_call"; data: { name: string; args: Record<string, unknown>; ok: boolean; summary: string } }
  | { event: "flow_ops"; data: { ops: FlowOp[] } }
  | { event: "dry_run_result"; data: RunReport }
  | { event: "error"; data: { code: AgentErrorCode; message: string } }
  | { event: "done"; data: { tool_calls: number } };

export type ChatTurn = { role: "user" | "assistant"; content: string };
