// API shapes from specs/contracts.md (C1, C2, C3, C5).
//
// C1 names come from the generated web/src/types/flow.ts (scripts/export_schema.py; never edit it by
// hand), so step types, variable types and link handles can't drift from the server's Pydantic models.
// The generated types describe VALID flows (e.g. extract_list needs at least one field). The editor
// holds DRAFTS, where a step's settings may still be unfilled (D-17), so FlowNode.config stays loose
// here. The checks at the end of this block make sure every valid server flow fits the draft shape.
import type {
  Flow as ValidFlow,
  FlowEdge as ValidEdge,
  Nodes as ValidNodes,
  Variable as ValidVariable,
  VarRef as ValidVarRef,
} from "./flow";

// ---------- C1. Flow document ----------
export type NodeType = ValidNodes[number]["type"];
export type VariableType = ValidVariable["type"];
export type Variable = { name: string; type: VariableType; value: unknown };
export type VarRef = ValidVarRef;

export type FlowNode = {
  id: string;
  type: NodeType;
  parentId?: string;
  position: { x: number; y: number };
  /** Draft settings: may be unfilled until the step is dry-run or published. */
  config: Record<string, any>;
};

export type SourceHandle = NonNullable<ValidEdge["sourceHandle"]>;
export type TargetHandle = NonNullable<ValidEdge["targetHandle"]>;

// Compile-time contract checks (they fail `npm run build` if the server's models change shape).
type Assert<T extends true> = T;
type Same<A, B> = [A] extends [B] ? ([B] extends [A] ? true : false) : false;
export type _ContractChecks = [
  Assert<Same<TargetHandle, "next">>,
  Assert<Same<SourceHandle, "true" | "false" | "item" | "done">>,
  Assert<"trigger" | "check_page" | "for_each" | "save_records" extends NodeType ? true : false>,
  Assert<ValidNodes[number] extends { id: string; type: NodeType } ? true : false>,
  Assert<NonNullable<ValidFlow["version"]> extends number ? true : false>,
];

export type FlowEdge = {
  id: string;
  source: string;
  target: string;
  sourceHandle?: SourceHandle;
  targetHandle?: TargetHandle;
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

/** `fields` is a name -> type map from the server; older payloads (and the mock) send a list of names. */
export type Dataset = {
  id: string;
  name: string;
  identity_key: string;
  fields: string[] | Record<string, string>;
  record_count: number;
};

export const fieldNames = (d: Pick<Dataset, "fields">): string[] =>
  Array.isArray(d.fields) ? d.fields : Object.keys(d.fields ?? {});

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

/** POST /api/flows/{id}/data-selector: what one step can use from the steps BEFORE it. */
export type SelectorField = {
  name: string;                       // store this plain name in the setting (no templates)
  type: "text" | "price" | "int" | "url" | "date" | "stock" | "change";
  ops: string[];                      // condition operators allowed for this field at this step
  sample: unknown;                    // a value from the flow's latest run, or null
  source_node_id: string | null;
};
export type DataSelector = {
  node_id: string;
  groups: { source_node_id: string; source_type: string; label: string; fields: SelectorField[] }[];
  variables: { name: string; type: string; sample: unknown }[];
};
