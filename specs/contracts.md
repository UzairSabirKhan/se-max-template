# Contracts (frozen at M0)

The interfaces between **Workstream A** (engine and platform) and **Workstream B** (editor and agent). Both streams build against this file. Changing it needs both stream owners to agree and a PR that updates this file first.

## C1. Flow document

The source of truth is the Pydantic models in `app/flow/schema.py` (owned by A). `scripts/export_schema.py` writes:
- `contracts/flow.schema.json`
- `web/src/types/flow.ts`, via `json-schema-to-typescript`

B never hand-edits `flow.ts`.

```ts
type Flow = {
  version: number;                       // draft_version, for 409 checks
  variables: Variable[];
  nodes: FlowNode[];
  edges: FlowEdge[];
};
type Variable = { name: string; type: "text"|"number"|"price"|"boolean"|"url"|"url_list"|"text_list"; value: unknown };
type FlowNode = {
  id: string;                            // "n_" + 6 chars, unique
  type: NodeType;
  parentId?: string;                     // set when inside a for_each body
  position: { x: number; y: number };    // UI only; ignored by the engine
  config: object;                        // typed per node type (see design.md "Node types")
};
type FlowEdge = { id: string; source: string; target: string; sourceHandle?: "true"|"false"|"item"|"done"; targetHandle?: "next" };
type VarRef = { var: string };
```

`NodeType` = `trigger | fetch_page | paginate | extract_list | for_each | fetch_item_page | extract_fields | condition | wait | check_page | save_records | alert | results | click | scroll | type | wait_for_element` (the last four are disabled).

**Example flows**, used by both streams as fixtures:
- `contracts/examples/list_tracking.json`: the list page with new/changed alerts
- `contracts/examples/multi_link.json`: `url_list` + `for_each`
- `contracts/examples/invalid_*.json`: one per graph rule, for error display

## C2. Validation errors

Every save, publish or agent edit that fails returns **HTTP 422**:

```json
{"error": "invalid_flow",
 "issues": [{"node_id": "n_ab12cd", "path": "config.fields[1].selector", "message": "Selector does not parse"}]}
```

`node_id` may be null for graph-level issues (cycle, missing trigger). B highlights the node and shows the message in its settings panel.

## C3. REST API

All JSON. Errors are always `{"error": code, "message": text}` and never a 500 with a stack trace.

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/health` | — | `{"status":"ok"}` |
| GET | `/api/node-types` | — | `[{type, group, label, disabled, config_schema}]` |
| GET | `/api/flows` | — | `[{id, name, status, unread_alerts, updated_at, published_at}]` |
| POST | `/api/flows` | `{name}` | `FlowDetail` (draft holds a trigger + check_page starter) |
| GET | `/api/flows/{id}` | — | `FlowDetail = {id, name, status, draft: Flow, published: Flow\|null, published_at}` |
| PUT | `/api/flows/{id}` | `{name?, draft: Flow}` | `FlowDetail` · 409 `{"error":"version_conflict"}` · 422 |
| DELETE | `/api/flows/{id}` | — | 204 |
| POST | `/api/flows/{id}/dry-run` | `{draft: Flow, until_node?: string}` | `RunReport` (trigger `dry_run`) |
| POST | `/api/flows/{id}/publish` | — | `FlowDetail` · 422 (incl. failed dry run with `RunReport` in `issues`) |
| POST | `/api/flows/{id}/pause` · `/unpublish` | — | `FlowDetail` |
| POST | `/api/flows/{id}/run` | — | `{run_id}` · 409 `{"error":"already_running"}` · 400 if not published |
| GET | `/api/flows/{id}/runs?limit=20` | — | `RunSummary[]` |
| GET | `/api/runs/{id}` | — | `RunReport` |
| GET | `/api/runs/{id}/stream` | — | SSE: `node_started {node_id}`, `node_finished {node_id, items_in, items_out}`, `iteration {node_id, index, key, status}`, `finished {RunSummary}` |
| GET | `/api/flows/{id}/results` | — | `[{node_id, name, items}]` from the latest run |
| GET | `/api/flows/{id}/alerts` | — | `Alert[]` (newest first) |
| POST | `/api/alerts/{id}/read` | — | 204 |
| GET | `/api/flows/{id}/datasets` | — | `[{id, name, identity_key, fields, record_count}]` |
| GET | `/api/datasets/{id}/records?sort=&limit=&offset=` | — | `{total, records: Record[]}` |
| GET | `/api/records/{id}/history` | — | `RecordChange[]` |
| GET | `/api/datasets/{id}/export.csv` | — | CSV (Stretch) |
| POST | `/api/datasets/{id}/reset` | — | 204 |
| POST | `/api/flows/{id}/agent` | `{message, draft: Flow, selected_node_ids: string[], history: ChatTurn[]}` | SSE (C5) |

### Shapes

```ts
type Verdict = "BLOCKED"|"UNSUPPORTED"|"BROKEN"|"SUSPECT"|"CHANGED"|"OK"|"UNKNOWN";
type RunSummary = { id: string; flow_id: string; trigger: "schedule"|"manual"|"dry_run"; verdict: Verdict;
                    reason: string; started_at: string; duration_ms: number; items_found: number;
                    items_valid: number; changes: {new: number; changed: number; removed: number}; ai_calls: 0 };
type RunReport = RunSummary & {
  evidence: string[];                          // e.g. "price missing on 12 of 12 items"
  http: {url: string; status: number|null; body_size: number; error?: string}[];
  coverage: Record<string, number>;            // field -> 0..1
  node_trace: {node_id: string; items_in: number; items_out: number; status: "ok"|"skipped"|"error"; note?: string}[];
  iterations?: {node_id: string; index: number; key: string; status: "ok"|"error"|"dropped"; error?: string}[];
  items: Item[];                               // final items (dry run: with would-be change labels)
};
type Item = { key: string; data: Record<string, string|number|null>;
              change?: "new"|"changed"|"same"|"removed"|"suspect"; previous?: Record<string, unknown>; pct_change?: Record<string, number> };
type Alert = { id: string; flow_id: string; run_id: string; node_id: string|null;
               kind: "condition"|"site_changed"|"blocked"|"unsupported"|"suspect";
               level: "info"|"warning"|"error"; title: string; message: string; items: Item[]; created_at: string; read: boolean };
type Record = { id: string; key: string; data: Record<string, unknown>; first_seen: string; last_changed: string|null; removed_at: string|null };
type RecordChange = { run_id: string; at: string; change: "new"|"changed"|"removed"; field: string|null; old_value: unknown; new_value: unknown; pct_change: number|null };
```

Prices travel as **strings** holding a decimal (`"1250.00"`), never floats.

## C4. Engine functions the agent calls (Python, owned by A)

B's agent tools call only these, from `app/engine/api.py`. A provides **stubs returning fixed data at M0**, then the real versions.

```python
async def fetch_outline(url: str) -> str                     # safe_fetch, scripts stripped, ~30 KB; raises FetchRefused(reason)
async def test_selector(url: str, selector: str, attr: str | None = None) -> dict   # {"count": int, "samples": [str]*<=5}
async def dry_run(flow: dict, flow_id: str | None, until_node: str | None = None) -> dict  # RunReport; never writes records
def node_type_schemas() -> list[dict]                         # same as GET /api/node-types
def validate_flow(flow: dict) -> list[dict]                   # [] if valid, else C2 issues
async def list_datasets(flow_id: str) -> list[dict]
async def sample_records(dataset_id: str, limit: int = 20) -> list[dict]
```

`app/engine/**` must never import `app/ai/**`. A test checks this.

## C5. Agent stream (owned by B)

SSE events from `POST /api/flows/{id}/agent`:

| Event | Data |
|---|---|
| `text` | `{"delta": "..."}` |
| `tool_call` | `{"name": "test_selector", "args": {...}, "ok": true, "summary": "12 matches"}` |
| `flow_ops` | `{"ops": FlowOp[]}`: proposed changes, already validated server-side |
| `dry_run_result` | `RunReport` |
| `error` | `{"code": "ai_unavailable" \| "invalid_ai_reply" \| "rate_limited" \| "tool_failed", "message": "..."}` |
| `done` | `{"tool_calls": n}` |

```ts
type FlowOp =
  | {op: "add_node"; node: FlowNode}
  | {op: "update_node"; id: string; config: object}          // full new config
  | {op: "remove_node"; id: string}
  | {op: "add_edge"; edge: FlowEdge}
  | {op: "remove_edge"; id: string}
  | {op: "set_variable"; variable: Variable}
  | {op: "remove_variable"; name: string};
```

The UI applies ops as **pending** (highlighted). Accept merges them into the draft; Reject drops them. Nothing is saved until the user saves.
