# Workstreams: Usama and Kaleem

Two people working in parallel. You meet only at the [contracts](contracts.md) and at fixed sync points. Each person owns their folders. Anything outside your folders goes through a PR the other person reviews.

| | **Usama: Engine and Platform (Workstream A)** | **Kaleem: Editor and Agent (Workstream B)** |
|---|---|---|
| In one line | Everything that runs **without AI** | Everything the user **sees and talks to** |
| Delivers | Flow schema and graph rules, `safe_fetch`, extraction, runner, verdict classifier, records, alerts, scheduler, REST API, database, mock shop, CI, deploy | React Flow editor, panels and tabs, PydanticAI agent and its tools, agent tests, README and demo |
| Owns | `app/flow/`, `app/engine/`, `app/db/`, `app/api/` (except `agent.py`), `app/scheduler.py`, `app/main.py`, `mockshop/`, `tests/engine/`, `tests/api/`, `scripts/`, `.github/`, `Dockerfile`, `render.yaml`, `pyproject.toml`, `contracts/` | `web/`, `app/ai/`, `app/api/agent.py`, `tests/ai/`, `README.md` |
| Packets | A1–A28 | B1–B21 |
| Docs | `docs/testing.md` (results, metrics, traceability), `docs/design.md` engine sections | `docs/requirements.md` status column, `docs/judge-checks.md`, `docs/design.md` UI and agent sections |
| AI usage log | Logs own entries | Logs own entries + writes the reflection |

**Why this split works in parallel:**
- Kaleem's agent tools only call Usama's engine functions (contract C4). Usama ships **stubs** at M0, so Kaleem never waits for the real engine.
- Kaleem's UI only calls the REST API (contract C3). Usama ships **stub routes** at M0.
- Usama never waits for Kaleem. The Dockerfile serves a placeholder page until `web/dist` exists.
- The person who builds the engine never touches the AI code, which backs up the "no AI at runtime" claim.

**Branches:** `feat/usama-<thing>` and `feat/kaleem-<thing>`. Small PRs, green CI before merge. Any change to `specs/contracts.md` needs both of you.

## Timeline per person

Clock times assume work starts at 11:00. Shift them if you start later; keep the durations.

| Time | Usama | Kaleem | Sync point |
|---|---|---|---|
| 11:00–11:30 **M0** | A1 repo + CI · A2 flow schema · A3 graph rules · A4 type export, example flows, engine **stubs** · A5 FastAPI skeleton + **stub** routes | B1 React + React Flow scaffold · B2 typed API client · B3 PydanticAI setup on `TestModel` | **11:30:** Usama pushes `flow.ts` + stubs → Kaleem's canvas renders `list_tracking.json` from the stub API |
| 11:30–12:15 **M1** | A6 Render + Neon + keep-alive ping · A7 database tables · A8 flow CRUD · A9 `safe_fetch` · A10 normalisers · A11 mock shop | B4 flow list · B5 canvas + palette + save · B6 node settings panel with errors on nodes | **12:15:** on the **live URL**, create a flow, save it, reload it |
| 12:15–13:00 **M2** | A12 extraction · A13 runner · A14 classifier · A15 save records · A16 alerts · A17 lifecycle routes · A18 scheduler · A19 zero-AI + determinism tests · A20 **real** engine functions (by 12:40) | B7 dry-run preview · B8 publish controls · B9 Runs tab · B10 Alerts tab · B12 agent · B13 agent tools · B14 agent sidebar · B15 agent tests | **12:40:** Usama swaps stubs for real engine functions. **13:00 live:** agent builds the flow → publish → price change alert → layout v2 → BROKEN |
| 13:00–13:45 **M3** | A21 `for_each` · A22 variables · A23 paginate · A24 SUSPECT · A25 PII scan · A26 CSV export | B11 Data tab · B16 loop container · B17 Variables panel · B18 multi-link agent flow · B19 polish + escaping | **13:45 live:** "alert me when any of these prices drops" on 3 mock product pages. **Feature freeze** |
| 13:45–14:30 **Bug bash** | Attacks Kaleem's area: UI, agent, prompt injection, bad replies | Attacks Usama's area: URLs, huge or slow pages, verdicts, double Run now | Fix bugs only; log defects in testing.md |
| 14:30–15:00 **Submit** | A27 traceability table + secret scan · A28 measure NFRs on the live app | B20 timed usability test (Usama is the tester) · B21 README, demo video (~14:15), AI log reflection, SUBMISSION.md | No deploys after 14:40 · tag `v1.0` · submit before 15:00 |

The Data tab (B11) moved to M3 to lighten Kaleem's M2, which is the heaviest block. If a milestone slips by more than 15 minutes, cut from the top of your **Cut order** before starting the next milestone.

## Handoffs (the only times one person needs the other)

| When | From → to | What | If it's late |
|---|---|---|---|
| 11:30 | Usama → Kaleem | `web/src/types/flow.ts`, example flows, stub API routes, stub engine functions | Kaleem builds the canvas from `contracts/examples/*.json` loaded locally |
| 12:15 | Usama → Kaleem | Real flow CRUD on the live URL | Kaleem keeps using stubs; save/load is retested at 12:30 |
| 12:15 | Kaleem → Usama | `web/` builds with `npm run build` (for the Dockerfile) | Usama deploys with the placeholder page |
| 12:40 | Usama → Kaleem | Real `fetch_outline`, `test_selector`, `dry_run`, `validate_flow` | Agent tests keep running on stubs; live agent demo moves to 13:15 |
| 13:00 | Usama → Kaleem | Lifecycle routes (publish, run, runs, alerts, datasets) | Tabs show stub data until then |
| 13:15 | Usama → Kaleem | `for_each` + variables in the engine | Kaleem finishes the loop UI on example JSON |

## What to do while waiting

| Person | Useful work that needs nothing from the other |
|---|---|
| Usama | More `safe_fetch` edge-case tests; classifier boundary tests (EC-30, EC-31); mock shop pages; traceability script (A27) |
| Kaleem | Node components and icons; settings forms from `config_schema`; agent instructions and `FunctionModel` contract tests; README sections; demo script rehearsal |

---

## Workstream A: Usama (Engine and Platform)

| ID | Task | Requirements | Done when | By |
|---|---|---|---|---|
| A1 | Repo scaffolding: `pyproject.toml` (fastapi, uvicorn, pydantic, httpx, selectolax, sqlalchemy, asyncpg, apscheduler, sse-starlette, pytest, respx, pytest-cov, ruff), package layout, `scripts/test.sh` (ruff + `pytest -m "not live"`), pytest markers `req`, `contract`, `live` | NFR-11 | CI green on an empty test | M0 |
| A2 | **Flow schema**: Pydantic models for every node type and variable type (`extra="forbid"`), `VarRef`, selector rules (≤ 200 characters, parse with selectolax), fixed field types and condition operators per field type, PII field-name rejection | FR-03, FR-23, FR-24, FR-34 | `tests/engine/test_flow_schema.py` (EC-16 – EC-18, EC-21, EC-24) | M0 |
| A3 | **Graph rules** in `validate_flow`: DAG / no cycles, ≤ 30 nodes, one trigger, source → `check_page` spine (list or `for_each` over variable), condition handles, loop wall / body whitelist / no nesting, variable existence and type-fit, browser nodes rejected at publish; returns C2 issues | FR-04, FR-22, FR-23, FR-27 | `test_graph_rules.py` (EC-19, EC-20, EC-56) | M0 |
| A4 | `scripts/export_schema.py` → `contracts/flow.schema.json` + `web/src/types/flow.ts`; example flows in `contracts/examples/`; `app/engine/api.py` stubs (C4) | — | B can import the types and call the stubs | M0 |
| A5 | FastAPI skeleton: `/health`, global error handler (never a 500 body with a trace), stub routes for C3, static serving of `web/dist` with SPA fallback | NFR-04 | `/health` 200; unknown route returns JSON error | M0 |
| A6 | **Deploy**: multi-stage Dockerfile (node builds `web/` → python image), `render.yaml`, Neon database, env vars on Render, cron-job.org ping every 5 min to `/health`, one uvicorn worker | NFR-08, NFR-09 | Live URL serves the React app and `/health` | M1 |
| A7 | **Database** models and migrations (create-all at startup is fine): `flows`, `runs`, `datasets`, `records`, `record_changes`, `run_results`, `alerts` (unique `dedupe_key`) | FR-01, FR-17, FR-29, FR-31 | Tables exist on Neon | M1 |
| A8 | Flow CRUD routes with `draft_version` check (409); new flow starts with trigger + `check_page` | FR-01, FR-05 | `tests/api/test_flows.py` | M1 |
| A9 | **`safe_fetch`**: http/https only; allowlist; resolve and refuse non-global IPs (IPv4, IPv6, mapped, encoded forms); pin the resolved IP; manual redirects (≤ 3, re-checked); 5 s connect / 15 s total; streamed body with 2 MB **decompressed** cap; HTML content types only; honest User-Agent; per-domain 2 s rate limit; 2 retries with backoff on 429/5xx/timeout (`Retry-After` ≤ 10 s) | FR-18, FR-19, FR-26, NFR-01 | `tests/engine/test_safe_fetch.py` (EC-01 – EC-14), mocked DNS only | M1 |
| A10 | **Normalisers** (`Decimal` prices, int, url → absolute, date, stock, text; Eastern-Arabic digits; empty markers) | FR-21 | `test_normalise.py` (EC-40 – EC-44) | M1 |
| A11 | **Mock shop** `/shop` (invented data): v1 list (12 products, 2 pages, JSON-LD), `?layout=v2`, `?mode=blocked` (captcha, 200), `?mode=js` (app shell), `?mode=dupes`, product pages `/shop/p/<slug>`, `/shop/admin` (change price, remove product, switch layout, reset), `/shop/huge`, `/shop/slow`, `/shop/file.pdf`, `/shop/redirect-internal`. Save HTML fixtures to `tests/fixtures/` | FR-36 | Every page reachable on the live URL | M1 |
| A12 | **Extraction**: `extract_list` (base selector, fields, attr, identity key, values read inside their own item element), `extract_fields` (one page = one item) | FR-21 | `test_extract.py` (EC-39) | M2 |
| A13 | **Runner**: walks the DAG in dependency order; item routing through condition handles; union + de-dup on merge; `wait` node; 120 s deadline; per-flow `asyncio.Lock`; node trace; `ai_calls = 0` recorded; dry-run mode that writes nothing | FR-13, FR-16, FR-17, FR-24, FR-26 | `test_runner.py` (EC-15, EC-49) | M2 |
| A14 | **`check_page` classifier** (pure function): BLOCKED → UNSUPPORTED → BROKEN → (UNKNOWN) with evidence strings; last-good comparison; small-list absolute counts; across all pages of a run | FR-20, FR-28 | `test_classifier.py` (EC-25, EC-26, EC-28 – EC-32) | M2 |
| A15 | **`save_records`**: datasets, upsert by identity key, new / changed / same / removed labels, `previous` + `pct_change`, change rows, first-run baseline, removed < 20% rule, identity-key change refused on publish; single transaction with alerts | FR-29 | `test_records.py` (EC-33, EC-35 – EC-37) | M2 |
| A16 | **Alerts**: Alert node output, system alerts (site changed at once, blocked after 2 in a row, unsupported, suspect), message templates ("Rs 1,250 → Rs 1,099 (−12%)"), de-dup keys, mark read, unread counts | FR-31 | `test_alerts.py` (EC-27, EC-38) | M2 |
| A17 | **Lifecycle routes**: dry run, publish (validate + dry run + store `expected_count`/`page_anchor` + snapshot + schedule), pause, unpublish, Run now (409 if running), runs list, run report, run SSE stream, results, alerts, datasets, records, history, reset | FR-13 – FR-17, FR-32 | `tests/api/test_lifecycle.py` (EC-50) | M2 |
| A18 | **Scheduler**: APScheduler jobs from the Trigger node (`manual`, `interval`, `daily` with timezone); rebuild at startup and on publish / pause / unpublish | FR-15 | `test_scheduler.py` | M2 |
| A19 | **Zero-AI + determinism tests**: import scan of `app/engine`; run with `app.ai` blocked and the client patched to raise; 20 identical runs | NFR-02, NFR-03 | `test_zero_ai.py`, `test_determinism.py` (EC-53, EC-54) | M2 |
| A20 | Real `app/engine/api.py` (replace stubs): `fetch_outline`, `test_selector`, `dry_run`, `node_type_schemas`, `validate_flow`, `list_datasets`, `sample_records` | C4 | B's agent works against real functions | M2 |
| A21 | **`for_each`**: over items or a list variable, `max_items` ≤ 25 with "limited to N of M", sequential, `on_error` skip/stop, ≥ 50% failures → BROKEN, iteration trace + SSE events; `fetch_item_page` | FR-22 | `test_loop.py` (EC-45 – EC-47) | M3 |
| A22 | **Variables** at run time: resolve `VarRef`s; publish dry-runs every URL of a `url_list` and names refused ones | FR-23 | `test_variables.py`, `test_publish::test_bad_url_in_list` (EC-48) | M3 |
| A23 | `paginate` (≤ 5 pages) | FR-25 | `test_extract::test_paginate` | M3 |
| A24 | SUSPECT (±50% move held, record not updated, system alert) | FR-30 | `test_records::test_suspect` (EC-34) | M3 |
| A25 | PII value scan (phone, email, CNIC patterns flagged) | FR-34 | `test_flow_schema::test_pii` | M3 |
| A26 | CSV export | FR-33 | `test_api::test_export_csv` | M3 |
| A27 | `scripts/trace_table.py` (pytest JSON report → FR → test → pass/fail) + gitleaks step in CI + coverage report | NFR-11, NFR-12 | Table written into testing.md from a real run | Docs |
| A28 | Measure NFRs on the live app (run times, max duration, memory, `ai_calls` sum) and fill testing.md | NFR-05 – NFR-09 | Numbers in testing.md, honest | Docs |

**Cut order for Usama (cut from the top):** A26 CSV → A25 PII value scan (keep field names) → A23 paginate → A24 SUSPECT → the `daily` trigger mode (keep `interval`) → A21/A22 loops and variables (last resort; the multi-link demo goes with them).

**Never cut:** A9 `safe_fetch`, A14 classifier, A15 records, A19 zero-AI and determinism tests.

---

## Workstream B: Kaleem (Editor and Agent)

| ID | Task | Requirements | Done when | By |
|---|---|---|---|---|
| B1 | `web/` scaffold: Vite + React + TypeScript, Tailwind, `@xyflow/react`, Zustand, TanStack Query, `@microsoft/fetch-event-source`, `@dagrejs/dagre`; build to `web/dist`; dev proxy to `:8000` | — | `npm run build` works in the Dockerfile | M0 |
| B2 | API client typed from `flow.ts` and contract shapes (C3); one error toast pattern for `{"error","message"}` | NFR-04 | Calls the stub API | M0 |
| B3 | **PydanticAI setup** `app/ai/models.py`: add `pydantic-ai-slim[google,anthropic]`; `FallbackModel(AI_MODEL, AI_FALLBACK_MODEL)` (Gemini → Claude); timeouts; `AgentDeps` dataclass (flow id, draft copy, selection, SSE emitter, tool-call counter); test config sets `ALLOW_MODEL_REQUESTS = False`. Check API names against the PydanticAI docs first | FR-09, FR-10 | A hello-world agent answers through `TestModel` in CI | M0 |
| B4 | **Flow list page**: create, rename, delete, status badge, unread alert count | FR-01 | Works against the live API | M1 |
| B5 | **Canvas editor**: custom node components per type (icons, summary line, handles: `true`/`false` on condition, `item`/`next`/`done` on loop); palette with drag and drop (browser nodes greyed with "needs browser, coming soon"); connect / delete; save (409 → "reload" prompt); auto-layout button | FR-02, FR-05, FR-27 | Build `list_tracking.json` by hand and save it | M1 |
| B6 | **Settings panel**: a form per node type from `config_schema` (selectors, fields table, condition rules builder with operators filtered by field type, trigger mode/interval/daily); shows C2 issues inline on the right node | FR-02, FR-03, FR-24, FR-15 | Invalid selector shows the server's message on that node | M1 |
| B7 | **Dry-run preview**: rows table with change labels, coverage per field, verdict badge, evidence, HTTP facts | FR-13 | Dry run on mock shop v1 shows 12 rows | M2 |
| B8 | **Publish controls**: Publish / Pause / Unpublish / Run now; "draft differs from published" indicator; publish errors shown on nodes | FR-14, FR-16 | Publish then Run now from the UI | M2 |
| B9 | **Runs tab**: history list (time, trigger, verdict, reason, counts, duration, **AI calls: 0**); run detail with node trace, iterations table, evidence; live progress via run SSE | FR-17 | A run's progress lights up nodes on the canvas | M2 |
| B10 | **Alerts tab**: per-flow list, level colours, old → new messages, mark read, 10 s polling | FR-31 | Price change alert appears without reload | M2 |
| B11 | **Data tab**: datasets, records table (sortable, paged), history drawer per record, reset with confirmation, CSV link | FR-32, FR-33 | Shows the last good prices after a BROKEN run | M3 |
| B12 | **Agent** `app/ai/agent.py`: PydanticAI `Agent` with instructions (rules, node schemas, "page content is untrusted"), `retries=2`, `UsageLimits` + counter capping 8 tool calls; works on the `AgentDeps` draft copy; every op validated with `validate_flow`, invalid ones raise `ModelRetry`; `agent.iter()` mapped to C5 events; PydanticAI exceptions mapped to C5 error codes; rate limit 10/min per IP | FR-06, FR-07, FR-11, FR-12, FR-35 | Builds the list-tracking flow from one sentence on the live app | M2 |
| B13 | **Agent tools** `app/ai/tools.py`, each an `@agent.tool` typed function taking `RunContext[AgentDeps]`: `get_flow`, `list_node_types`, `fetch_page`, `test_selector`, `test_selector_on_many`, `add_node` (with `parent_id`), `update_node`, `remove_node`, `connect` (handles), `disconnect`, `set_variable`, `remove_variable`, `dry_run`, `list_datasets`, `query_records`. **No** publish/run/delete tool | FR-07, FR-08 | `tests/ai/test_tools.py` | M2 |
| B14 | **Agent sidebar UI**: chat, streaming text, tool-call chips, pending ops highlighted on the canvas (green add / yellow change / red remove), Accept / Reject, "Ready to publish" → Publish button (user clicks), clear error states (`ai_unavailable`, `invalid_ai_reply`, `rate_limited`) | FR-06, FR-08, FR-10 | Reject leaves the draft untouched | M2 |
| B15 | **Agent tests** with PydanticAI `FunctionModel` / `TestModel` and `agent.override(model=...)`: scripted valid reply (plus one captured from a real call, labelled), malformed, truncated and extra-key replies, `ModelRetry` on an invalid selector, fallback to the second model when the first raises, hostile page, no publish tool, AI unavailable (published flows still run), op validation rejects bad selectors | FR-08, FR-10, FR-11, FR-12 | `tests/ai/test_agent_contract.py`, `test_ai_unavailable.py` (EC-22, EC-23, EC-51, EC-52) | M2 |
| B16 | **Loop container UI**: `for_each` as a resizable React Flow group, drop nodes into it (sets `parentId`), only body-allowed nodes accepted, `item`/`next`/`done` handles | FR-22 | Build `multi_link.json` by hand | M3 |
| B17 | **Variables panel**: add / edit / delete typed variables; `url_list` as one link per line with live checks; `VarRef` picker in node settings (only type-compatible variables offered) | FR-23 | Agent-created variables appear and are editable | M3 |
| B18 | **Multi-link agent flow**: prompt and tool tuning so "alert me when any of these prices drops: <links>" builds variable + loop + save + condition + alert, tested on several links with `test_selector_on_many` | FR-22, FR-23 | Works on the live app with 3 mock product pages | M3 |
| B19 | UX polish needed for judging: empty states, loading states, scraped text always escaped (no `dangerouslySetInnerHTML`), mobile-safe layout not required | EC-55 | Red-team `<script>` check passes | M3 |
| B20 | NFR-10 timed walkthrough by a teammate who didn't build the UI | NFR-10 | Time recorded in testing.md | Docs |
| B21 | README final (live URL, CI badge, built vs not), demo script rehearsal, backup demo video, AI usage log entries + reflection, requirements status column | Demo, Responsible AI | Submission checklist ticked | Docs |

**Cut order for Kaleem (cut from the top):** CSV link in B11 → auto-layout button → history drawer in B11 → live run progress on canvas (keep the Runs tab) → B17 `VarRef` picker (keep the panel) → B16/B18 loop UI and multi-link agent flow (last resort, together with A21/A22).

**Never cut:** B5 canvas, B12–B15 agent with validation and tests, B9 Runs tab showing AI calls: 0, B10 Alerts tab.

---

## Coverage matrix: nothing is missed

Every requirement, edge case and deliverable has an owner. Tick these at the final check.

### Functional requirements

| FR | Feature | A | B |
|---|---|---|---|
| FR-01 | Flow CRUD + list | A7, A8 | B4 |
| FR-02 | Canvas editor | — | B5, B6 |
| FR-03 | Schema validation | A2 | B6 (shows issues) |
| FR-04 | Graph rules | A3 | B5 (handles), B16 |
| FR-05 | Version conflict | A8 | B5 |
| FR-06 | Sidebar agent edits draft | — | B12, B14 |
| FR-07 | Agent tools | A20 (engine functions) | B13 |
| FR-08 | Agent can't publish | — | B13, B14, B15 |
| FR-09 | Configurable AI provider | — | B3 |
| FR-10 | AI unavailable fallback | A19 (runs unaffected) | B3, B14, B15 |
| FR-11 | Bad AI replies rejected | A3 (validate_flow) | B12, B15 |
| FR-12 | Untrusted page content | A20 (`fetch_outline`) | B12, B15 |
| FR-13 | Dry run | A13, A17 | B7 |
| FR-14 | Publish / pause / unpublish | A17 | B8 |
| FR-15 | Trigger node schedule | A18 | B6 |
| FR-16 | Run now + lock | A13, A17 | B8 |
| FR-17 | Run history | A13, A17 | B9 |
| FR-18 | `safe_fetch` | A9 | — |
| FR-19 | Domain allowlist | A9 | — |
| FR-20 | Static only / UNSUPPORTED | A14 | B9 (message) |
| FR-21 | Extraction + normalisers | A10, A12 | — |
| FR-22 | `for_each` loop | A3, A21 | B16, B18 |
| FR-23 | Variables | A2, A3, A22 | B17, B18 |
| FR-24 | Conditions | A2, A13 | B6 |
| FR-25 | Paginate | A23 | B6 |
| FR-26 | Waits, rate limit, retries, deadline | A9, A13 | B6 (wait node) |
| FR-27 | Browser nodes disabled | A3 | B5 |
| FR-28 | `check_page` verdicts | A14 | B9 |
| FR-29 | `save_records` | A15 | B11 |
| FR-30 | SUSPECT | A24 | B10 |
| FR-31 | Alerts | A16 | B10 |
| FR-32 | Data tab | A17 | B11 |
| FR-33 | CSV export (Stretch) | A26 | B11 |
| FR-34 | PII rejection | A2, A25 | — |
| FR-35 | Agent rate limit | — | B12 |
| FR-36 | Mock shop | A11 | — |
| FR-37 | AI repair (Stretch, cut list) | dry run reused | only after M3 if both streams are green |
| FR-38 | Version history (Stretch, cut list) | `flow_versions` table | only after M3 |
| FR-39 | Email / Telegram (Stretch, cut list) | — | not planned |

### Non-functional requirements

| NFR | Owner | Task |
|---|---|---|
| NFR-01 URL safety | A | A9 + red-team |
| NFR-02 Zero AI at runtime | A | A19 |
| NFR-03 Determinism | A | A19 |
| NFR-04 No crashes | A + B | A5, A17 · B2, B14 |
| NFR-05 Breakage detected | A | A14, A15 |
| NFR-06 Run time | A | A28 |
| NFR-07 Bounded runs | A | A13, A28 |
| NFR-08 Memory | A | A6, A28 |
| NFR-09 Availability | A | A6 |
| NFR-10 Usability | B | B20 |
| NFR-11 CI, lint, coverage | A | A1, A27 |
| NFR-12 No secrets | A | A27 |

### Edge cases ([testing.md](testing.md))

| EC range | Owner |
|---|---|
| EC-01 – EC-15 (URL safety, fetch robustness) | A9, A13 |
| EC-16 – EC-21, EC-24 (schema, graph, variables, PII) | A2, A3 |
| EC-22, EC-23 (AI replies, hostile page) | B15 |
| EC-25 – EC-39 (classifier, records, alerts, extraction) | A12 – A16, A24 |
| EC-40 – EC-44 (normalisers) | A10 |
| EC-45 – EC-48 (loops, variables) | A21, A22 |
| EC-49, EC-50, EC-56 (lock, draft isolation, browser nodes) | A13, A17, A3 |
| EC-51, EC-52 (no publish tool, AI unavailable) | B15 |
| EC-53, EC-54 (zero AI, determinism) | A19 |
| EC-55 (escaped text) | B19 |

### Deliverables

| Deliverable | Owner |
|---|---|
| Live URL, `/health`, keep-alive ping | A6 |
| CI green, test script, coverage, secret scan | A1, A27 |
| testing.md results, metrics, traceability table | A27, A28 |
| requirements.md status column | Kaleem (B21); Usama updates his rows |
| design.md kept accurate | A (engine sections), B (UI and agent sections) |
| judge-checks.md live steps verified | Usama and Kaleem, at the 14:30 red-team |
| README, demo script, backup video | B21 |
| AI usage log (each stream logs its own entries) | Both; B21 writes the reflection |
| ADRs (already written; update if a decision changes) | Whoever changes the decision |
| SUBMISSION.md checklist + final commit hash | Kaleem (B21), checked by Usama |

## Final completion check (14:30)

Every Must is Done or explicitly cut with a reason in requirements.md.

1. All FR rows marked Done or Cut, with their tests passing in CI.
2. The traceability table is generated from the final CI run.
3. Every judge check works on the **live** URL (judge-checks.md).
4. The red-team checklist has passed twice (13:30 and 14:30).
5. No `Pending` left in README, testing.md or judge-checks.md, except values honestly marked not measured.
