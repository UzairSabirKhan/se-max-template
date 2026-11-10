# Workstreams

Two streams that run in parallel. They meet only at the [contracts](contracts.md) and at fixed sync points. Each stream owns its folders. Anything outside your folders goes through a PR reviewed by the other stream.

| | **Workstream A: Engine and Platform** | **Workstream B: Editor and Agent** |
|---|---|---|
| Delivers | Everything that runs **without AI**: flow schema, engine, `safe_fetch`, classifier, records, alerts, scheduler, API, database, mock shop, CI, deploy | Everything the user **sees and talks to**: React Flow editor, panels and tabs, AI adapter, agent loop and tools, agent tests, README and demo |
| Suggested people | Usama (lead) + Umar on tests | Kaleem (UI) + Umar on agent |
| Owns | `app/flow/`, `app/engine/`, `app/db/`, `app/api/` (except `agent.py`), `app/scheduler.py`, `app/main.py`, `mockshop/`, `tests/engine/`, `tests/api/`, `scripts/`, `.github/`, `Dockerfile`, `render.yaml`, `pyproject.toml`, `contracts/` | `web/`, `app/ai/`, `app/api/agent.py`, `tests/ai/`, `README.md`, `docs/ai-usage-log.md` |
| Shared docs | `docs/testing.md` (results), `docs/design.md` | `docs/requirements.md` (status column), `docs/judge-checks.md` |

**Branches:** `feat/a-<thing>` and `feat/b-<thing>`. Small PRs, green CI before merge, the other stream reviews any change to `docs/contracts.md`.

## Milestones and sync points

Clock times assume work starts at 11:00. Shift them if you start later; keep the durations.

| Milestone | Time | A delivers | B delivers | Joint check |
|---|---|---|---|---|
| **M0: Contracts frozen** | 11:30 | `app/flow/schema.py` (all node models), `contracts/flow.schema.json`, example flows, `app/engine/api.py` **stubs**, FastAPI skeleton with `/health` and **stub** `/api/*` routes returning example data, `scripts/test.sh`, CI green | Vite + React + React Flow app building into `web/dist`; generated `flow.ts`; API client; AI adapter skeleton | Both run the stub app; B's canvas renders `list_tracking.json` |
| **M1: Deployed skeleton** | 12:15 | Dockerfile, Render + Neon live, cron-job.org ping, mock shop v1 deployed, real `safe_fetch`, normalisers, flow CRUD on Postgres | Flow list, canvas with palette and settings panel, save/load against the live API | Open the **live URL**, create a flow, save it, reload it |
| **M2: Core loop end to end** | 13:00 | Real dry run, publish, Run now, scheduler, `check_page` verdicts, `save_records`, conditions, alerts, run history, all mock shop pages | Runs / Alerts / Data tabs, publish controls, dry-run preview; agent loop with real tools building the list-tracking flow | **Live:** agent builds the flow → publish → Run now → price change alert → layout v2 → BROKEN |
| **M3: Feature complete + freeze** | 13:45 | `for_each`, variables, paginate, wait/retry/deadline, SUSPECT, PII, allowlist, export | Loop container UI, Variables panel, multi-link agent flow, pending-change diff, error states | **Live:** "alert me when any of these prices drops" on 3 mock product pages |
| **Bug bash** | 13:45–14:30 | Red-team the UI and agent (swap: A attacks B's area) | Red-team the engine and API (B attacks A's area) | Fix bugs only; record defects in testing.md |
| **Docs + submit** | 14:30–15:00 | testing.md results from CI, traceability table, measured metrics | README final, demo video (~14:15), AI log reflection, requirements status | No deploys after 14:40; tag `v1.0`; submit before 15:00 |

If a milestone slips by more than 15 minutes, cut from the bottom of that stream's **Cut order** before starting the next milestone.

---

## Workstream A: Engine and Platform

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

**Cut order for A (cut from the top):** A26 CSV → A25 PII value scan (keep field names) → A23 paginate → A24 SUSPECT → the `daily` trigger mode (keep `interval`) → A21/A22 loops and variables (last resort; the multi-link demo goes with them).

**Never cut:** A9 `safe_fetch`, A14 classifier, A15 records, A19 zero-AI and determinism tests.

---

## Workstream B: Editor and Agent

| ID | Task | Requirements | Done when | By |
|---|---|---|---|---|
| B1 | `web/` scaffold: Vite + React + TypeScript, Tailwind, `@xyflow/react`, Zustand, TanStack Query, `@microsoft/fetch-event-source`, `@dagrejs/dagre`; build to `web/dist`; dev proxy to `:8000` | — | `npm run build` works in the Dockerfile | M0 |
| B2 | API client typed from `flow.ts` and contract shapes (C3); one error toast pattern for `{"error","message"}` | NFR-04 | Calls the stub API | M0 |
| B3 | AI adapter `app/ai/provider.py`: `chat(messages, tools) -> async events` for Gemini and Claude, chosen by `AI_PROVIDER`/`AI_MODEL`; timeouts; maps failures to `ai_unavailable` | FR-09, FR-10 | Unit test with a fake provider | M0 |
| B4 | **Flow list page**: create, rename, delete, status badge, unread alert count | FR-01 | Works against the live API | M1 |
| B5 | **Canvas editor**: custom node components per type (icons, summary line, handles: `true`/`false` on condition, `item`/`next`/`done` on loop); palette with drag and drop (browser nodes greyed with "needs browser, coming soon"); connect / delete; save (409 → "reload" prompt); auto-layout button | FR-02, FR-05, FR-27 | Build `list_tracking.json` by hand and save it | M1 |
| B6 | **Settings panel**: a form per node type from `config_schema` (selectors, fields table, condition rules builder with operators filtered by field type, trigger mode/interval/daily); shows C2 issues inline on the right node | FR-02, FR-03, FR-24, FR-15 | Invalid selector shows the server's message on that node | M1 |
| B7 | **Dry-run preview**: rows table with change labels, coverage per field, verdict badge, evidence, HTTP facts | FR-13 | Dry run on mock shop v1 shows 12 rows | M2 |
| B8 | **Publish controls**: Publish / Pause / Unpublish / Run now; "draft differs from published" indicator; publish errors shown on nodes | FR-14, FR-16 | Publish then Run now from the UI | M2 |
| B9 | **Runs tab**: history list (time, trigger, verdict, reason, counts, duration, **AI calls: 0**); run detail with node trace, iterations table, evidence; live progress via run SSE | FR-17 | A run's progress lights up nodes on the canvas | M2 |
| B10 | **Alerts tab**: per-flow list, level colours, old → new messages, mark read, 10 s polling | FR-31 | Price change alert appears without reload | M2 |
| B11 | **Data tab**: datasets, records table (sortable, paged), history drawer per record, reset with confirmation, CSV link | FR-32, FR-33 | Shows the last good prices after a BROKEN run | M2 |
| B12 | **Agent loop** `app/ai/agent.py`: system prompt (rules, node schemas, "page content is untrusted"), tool loop ≤ 8 calls, works on a server-side copy of the draft, every op validated with `validate_flow` before it's emitted, emits C5 events; rate limit 10/min per IP | FR-06, FR-07, FR-11, FR-12, FR-35 | Builds the list-tracking flow from one sentence on the live app | M2 |
| B13 | **Agent tools** `app/ai/tools.py`: `get_flow`, `list_node_types`, `fetch_page`, `test_selector`, `test_selector_on_many`, `add_node` (with `parent_id`), `update_node`, `remove_node`, `connect` (handles), `disconnect`, `set_variable`, `remove_variable`, `dry_run`, `list_datasets`, `query_records`. **No** publish/run/delete tool | FR-07, FR-08 | `tests/ai/test_tools.py` | M2 |
| B14 | **Agent sidebar UI**: chat, streaming text, tool-call chips, pending ops highlighted on the canvas (green add / yellow change / red remove), Accept / Reject, "Ready to publish" → Publish button (user clicks), clear error states (`ai_unavailable`, `invalid_ai_reply`, `rate_limited`) | FR-06, FR-08, FR-10 | Reject leaves the draft untouched | M2 |
| B15 | **Agent tests**: recorded reply (contract), truncated and extra-key replies, hostile page, no publish tool, AI unavailable (published flows still run), op validation rejects bad selectors | FR-08, FR-10, FR-11, FR-12 | `tests/ai/test_agent_contract.py`, `test_ai_unavailable.py` (EC-22, EC-23, EC-51, EC-52) | M2 |
| B16 | **Loop container UI**: `for_each` as a resizable React Flow group, drop nodes into it (sets `parentId`), only body-allowed nodes accepted, `item`/`next`/`done` handles | FR-22 | Build `multi_link.json` by hand | M3 |
| B17 | **Variables panel**: add / edit / delete typed variables; `url_list` as one link per line with live checks; `VarRef` picker in node settings (only type-compatible variables offered) | FR-23 | Agent-created variables appear and are editable | M3 |
| B18 | **Multi-link agent flow**: prompt and tool tuning so "alert me when any of these prices drops: <links>" builds variable + loop + save + condition + alert, tested on several links with `test_selector_on_many` | FR-22, FR-23 | Works on the live app with 3 mock product pages | M3 |
| B19 | UX polish needed for judging: empty states, loading states, scraped text always escaped (no `dangerouslySetInnerHTML`), mobile-safe layout not required | EC-55 | Red-team `<script>` check passes | M3 |
| B20 | NFR-10 timed walkthrough by a teammate who didn't build the UI | NFR-10 | Time recorded in testing.md | Docs |
| B21 | README final (live URL, CI badge, built vs not), demo script rehearsal, backup demo video, AI usage log entries + reflection, requirements status column | Demo, Responsible AI | Submission checklist ticked | Docs |

**Cut order for B (cut from the top):** CSV link in B11 → auto-layout button → history drawer in B11 → live run progress on canvas (keep the Runs tab) → B17 `VarRef` picker (keep the panel) → B16/B18 loop UI and multi-link agent flow (last resort, together with A21/A22).

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
| requirements.md status column | B21 (A updates its rows) |
| design.md kept accurate | A (engine sections), B (UI and agent sections) |
| judge-checks.md live steps verified | Both, at the 14:30 red-team |
| README, demo script, backup video | B21 |
| AI usage log (each stream logs its own entries) | Both; B21 writes the reflection |
| ADRs (already written; update if a decision changes) | Whoever changes the decision |
| SUBMISSION.md checklist + final commit hash | B21, checked by A |

## Final completion check (14:30)

Every Must is Done or explicitly cut with a reason in requirements.md.

1. All FR rows marked Done or Cut, with their tests passing in CI.
2. The traceability table is generated from the final CI run.
3. Every judge check works on the **live** URL (judge-checks.md).
4. The red-team checklist has passed twice (13:30 and 14:30).
5. No `Pending` left in README, testing.md or judge-checks.md, except values honestly marked not measured.
