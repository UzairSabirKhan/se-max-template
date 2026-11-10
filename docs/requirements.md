# Requirements

Every test carries `@pytest.mark.req("FR-xx")` or `@pytest.mark.req("NFR-xx")`. The requirement-to-test table in [testing.md](testing.md) is generated from a real test run by `scripts/trace_table.py`, not written by hand.

## Problem statement

People who need the same data from a website every day have three poor options:
- check it by hand, which is slow and misses changes
- write a scraper, which needs a developer and **breaks silently** when the layout changes, storing wrong or empty data
- use an AI scraper that calls an LLM on every run, which costs money per run and can give different output for the same page

**ScrapeOnce** is a no-code builder for scraping workflows. A sidebar AI agent helps the user build a visual flow once: fetch pages, extract fields, loop over items, apply conditions, store records, raise alerts. The user reviews and **publishes** it. After that, every scheduled or manual run is plain, deterministic code with **no AI calls**. Each run gets one verdict (blocked, needs JavaScript, broken, suspicious, changed, OK, unknown) with evidence, so a layout change raises an alert instead of storing wrong data.

## Users

| User | Need | Example goal |
|---|---|---|
| **Small online seller (primary)** | Watch 5–20 competitor listings on independent, server-rendered stores (Shopify or WooCommerce themes) every day | "Alert me when any of these prices drops" |
| Researcher or student | Collect public listings over time | "Save every new article title and price each day" |
| Operations staff | Watch a public catalogue or notice list | "Tell me when a new item appears" |

**User evidence:** none yet. We will add a quote only from a real interview, never an invented one.

**Not a target:** JavaScript-only marketplaces (for example Daraz), which are out of scope (static HTML only).

## Functional requirements

Status: `Planned`, then `In progress`, then `Done` (with a test passing in CI), or `Cut`.

### Flows and editor

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | Create, list, open, rename and delete flows. The flow list shows status (draft / published / paused) and unread alert count | Must | Done |
| FR-02 | Canvas editor (React Flow): drag nodes from a palette, connect them, and edit each node's settings in a side panel | Must | Done |
| FR-03 | Every save, agent edit and publish validates the flow against the schema: fixed node types, unknown keys rejected, selectors of 200 characters or fewer that parse, fixed field types and condition operators, no code and no regex. An invalid flow gets a clear message and is never saved | Must | Done |
| FR-04 | Graph rules are enforced: no cycles (DAG); at most 30 nodes; exactly one trigger; a source → `check_page` spine; condition edges use `true`/`false`; loop body rules (see FR-22) | Must | Done |
| FR-05 | Saving a draft checks `draft_version`. A stale save returns 409 with a "reload" message instead of overwriting | Should | Done |

### Sidebar agent (design time only)

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-06 | A sidebar agent sees the open flow and the user's selection and edits the **draft** through typed tools. Its edits appear on the canvas as pending changes the user accepts or rejects | Must | Done (tested with scripted models; live model run is B18) |
| FR-07 | Agent tools: `get_flow`, `list_node_types`, `fetch_page`, `test_selector`, `test_selector_on_many`, `add_node`, `add_steps`, `update_node`, `remove_node`, `connect`, `disconnect`, `set_variable`, `remove_variable`, `dry_run`, `list_datasets`, `query_records`. At most 12 tool calls per message (room to recover from one refused edit); `add_steps` adds several steps and their links in one call so a whole flow fits | Must | Done |
| FR-08 | The agent has no tool to publish, run, pause or delete, and none to execute code. Only the user can publish | Must | Done |
| FR-09 | The agent uses `AI_MODEL` (e.g. Gemini) with automatic fallback, in order, to each model in `AI_FALLBACK_MODEL` (e.g. Groq, then Claude) when one errors, times out or is rate-limited (PydanticAI `FallbackModel`). Providers: Gemini, Groq, Claude; a model without its API key is skipped | Should | Done |
| FR-10 | If AI is unavailable, the sidebar shows "AI service is unavailable, please try again". Manual editing, dry runs and published flows keep working | Must | Done |
| FR-11 | A malformed, truncated or extra-key AI reply, or a tool call that fails validation, is rejected with a clear error and never applied to the draft | Must | Done |
| FR-12 | Page content sent to the agent is stripped of scripts, cut to about 30 KB and marked as untrusted. Text on the page cannot change the rules | Must | Done (agent tools also refuse internal URLs; safe_fetch is the real guard) |

### Lifecycle, scheduling and runs

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-13 | **Dry run** executes the draft and shows rows, field coverage, the verdict and the change labels that would be assigned. It writes no records and sends no alerts | Must | Done |
| FR-14 | **Publish** validates, dry-runs, stores `expected_count` and `page_anchor`, copies the draft to the published copy and registers the schedule. **Pause** and **Unpublish** remove the schedule. Editing a published flow changes only the draft | Must | Done |
| FR-15 | The Trigger node holds the schedule: `manual`, `interval` (`every_minutes` ≥ 1) or `daily` (`at_time` + timezone). Schedules are rebuilt from published flows at startup | Must | Done |
| FR-16 | **Run now** runs the published copy. A flow never runs twice at once (per-flow lock) | Must | Done |
| FR-17 | Run history records time, trigger, verdict, reason, evidence, HTTP status, item counts, field coverage, duration, a per-node trace and `ai_calls` (always 0) | Must | Done |

### Engine and nodes

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-18 | `safe_fetch` is used for **every** outbound request: http/https only; the host is resolved and any IP that is not global is refused (private, loopback, link-local, metadata, IPv6 local); the check runs again on every redirect (at most 3); 5 s connect and 15 s total timeouts; 2 MB cap on the decompressed body; HTML content types only | Must | Done |
| FR-19 | Any public website can be tracked (no allowlist). Internal, private and metadata addresses are always refused (FR-18) | Should | Done |
| FR-20 | Static HTML only. A page that is a JavaScript app shell gets the UNSUPPORTED verdict with "This page loads its data with JavaScript, which ScrapeOnce does not support." | Must | Done |
| FR-21 | `extract_list` (base selector + fields + identity key) and `extract_fields` (one page = one item), with tested normalisers for text, price, int, url, date and stock | Must | Done |
| FR-22 | `for_each` loops over items or a list variable: at most 25 items, one at a time, no nesting, body limited to `fetch_item_page`, `extract_fields`, `condition` and `wait`, `on_error` = skip or stop | Should | Done |
| FR-23 | Typed flow variables (`text`, `number`, `price`, `boolean`, `url`, `url_list`, `text_list`) referenced as `{"var": name}` only in fixed places, type-checked on save | Should | Done |
| FR-24 | `condition` routes each item to `true` / `false` using fixed operators per field type (`lt`, `gt`, `contains`, `is_new`, `changed`, `drop_pct_gt`, `back_in_stock`, …) | Must | Done |
| FR-25 | `paginate` follows a "next" link, at most 5 pages | Should | Done |
| FR-26 | Waits: `wait` node (1–10 s); a rate limit of 2 s per domain; 2 retries with backoff on 429/5xx/timeout (`Retry-After` honoured up to 10 s); a 120 s run deadline | Must | Done |
| FR-27 | Browser nodes (click, scroll, type, wait for element) appear in the palette as disabled ("needs browser, coming soon") and are rejected at publish | Should | Done |

### Change detection, records and alerts

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-28 | `check_page` gives one verdict per run, in order: **BLOCKED** (fetch error, 403/407/429/5xx, captcha or "access denied" text, non-HTML, body under 20% of the last good size, missing `page_anchor`), **UNSUPPORTED**, **BROKEN** (count outside `expected_count` or under 50% of the last good run; a required field filled on under 50% of items or down more than 30 points; over 50% of values fail to parse; duplicate identity keys). For lists under 5 items it uses absolute counts. If the verdict is BLOCKED, UNSUPPORTED, BROKEN or UNKNOWN, nothing after it runs and nothing is stored | Must | Done |
| FR-29 | `save_records` stores items in a named dataset keyed by identity key. It labels each item new / changed / same / removed (removed only if under 20% vanished), writes the current record plus one change row per changed field, and the first run is a silent baseline | Must | Done |
| FR-30 | A price that moved more than ±50% is labelled SUSPECT: the record is not updated and a system alert asks for confirmation | Should | Done |
| FR-31 | Alerts are per flow, from Alert nodes (condition matches) and system verdicts (site changed, blocked after 2 runs in a row, unsupported, suspect). They are de-duplicated, say why they fired (for example "Blue Kettle: Rs 1,250 → Rs 1,099 (−12%)") and appear in the flow's Alerts tab | Must | Done |
| FR-32 | The Data page (sidebar) lists each dataset's records and each record's change history | Should | Done |
| FR-33 | CSV export of a dataset | Stretch | Done |
| FR-34 | Field names that look like personal data (email, phone, CNIC) are rejected, and values matching those patterns are flagged | Should | Planned |
| FR-35 | The agent endpoint is rate-limited (10 requests per minute per IP) | Should | Done |

### Demo target

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-36 | Our own mock shop at `/shop` with invented data: list page v1 (12 products, 2 pages), layout v2 (price class renamed), a blocked page (captcha text, status 200), a JavaScript shell, a duplicate-SKU page, product detail pages, an admin action to change a price or remove a product, and robustness pages for the judges (`/shop/huge` over 2 MB, `/shop/slow` slow drip, `/shop/file.pdf`, `/shop/redirect-internal` redirecting to `169.254.169.254`) | Must | Done |

### Cut list (only if the core is done)

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-37 | AI-proposed repair after a BROKEN run, shown as a draft diff; applied only if it passes the last good data and the user publishes | Stretch | Planned |
| FR-38 | Published version history with rollback | Stretch | Planned |
| FR-39 | Email or Telegram alerts | Stretch | Planned |

## Non-functional requirements

`Result` is filled only from a real measurement. Until then it says `Not measured`.

| ID | Category | Requirement | Target | How measured | Result |
|----|----------|-------------|--------|--------------|--------|
| NFR-01 | Security | Internal, private and metadata URLs are refused | 100% of the URL-safety list refused (IPv4/IPv6 forms, encoded IPs, metadata hostnames, non-http schemes, redirect to internal) | `tests/test_safe_fetch.py` (parametrised, mocked DNS) + live check on the deployed URL | Not measured |
| NFR-02 | Responsible AI | No AI call during a scheduled or manual run | `ai_calls = 0` on every run; the engine imports nothing from `app/ai` | `tests/test_zero_ai.py`: import scan + run with the AI client patched to raise | Not measured |
| NFR-03 | Correctness | Same page, same output | 20 runs on the same fixture give identical data (ignoring ids and timestamps) | `tests/test_determinism.py` | Not measured |
| NFR-04 | Robustness | Bad input never crashes the server | 0 responses with status 500 across the bad-input suite (bad URLs, timeouts, huge pages, malformed AI replies, invalid flows) | API tests + red-team checklist on the live URL | Not measured |
| NFR-05 | Reliability | Breakage is detected, not stored | Every mock-shop page gives its expected verdict (v2 → BROKEN, blocked → BLOCKED, js → UNSUPPORTED, dupes → BROKEN) with 0 records written | `tests/test_classifier.py` + live red-team run | Not measured |
| NFR-06 | Performance | A list-page run is quick | p95 under 5 s for the 12-item mock shop list (warm service) | `runs.duration_ms` over at least 10 live runs | Not measured |
| NFR-07 | Boundedness | Every run ends | No run longer than 120 s, including slow-drip servers | Slow-drip test + max of `runs.duration_ms` | Not measured |
| NFR-08 | Resources | Fits the free host | Memory under 400 MB on the free host (512 MB) | Host metrics (Railway or Render) during the demo schedule | Not measured |
| NFR-09 | Availability | Reachable for judging | `/health` returns 200 from the public URL; scheduled runs keep firing during judging | cron-job.org history + run history timestamps | Not measured |
| NFR-10 | Usability | A non-developer can set up tracking | A teammate who didn't build the UI creates and publishes the "alert me when any of these prices drops" flow with the agent in under 5 min on a fresh browser | Timed walkthrough, recorded in testing.md | Not measured |
| NFR-11 | Maintainability | Code quality is checked on every push | CI green on `main`; ruff clean; line coverage of `app/engine` at least 80% | GitHub Actions + pytest-cov | Not measured |
| NFR-12 | Privacy | No secrets or personal data in the repo | Secret scan passes on the full history | gitleaks in CI | Not measured |

## Constraints

- 6-hour build on 10 Nov 2026 (9:00–3:00), starting from the organizers' template. No pre-written code.
- Free hosting, one Docker image: Railway (trial credit; does not sleep; Postgres in the same project) as primary, Render free (512 MB, sleeps after about 15 min idle) + Neon Postgres as backup.
- Static HTML only. No headless browser (memory and committee scope).
- Only our own mock shop is scraped during the event. No real stores, no personal data.
- No secrets in the repository. Keys live in the host's environment variables.

## Assumptions

- Target stores render prices in the HTML (true for typical Shopify and WooCommerce themes).
- One uvicorn worker is enough for the demo load, which keeps the in-process scheduler from firing twice.
- On Render only: a free cron-job.org ping every 5 minutes keeps the service awake during judging.
- The Gemini or Claude API is reachable at the venue for the agent. Runs don't need it.

## Out of scope

- Pages that need JavaScript, login, infinite scroll or form submission.
- CAPTCHA solving, proxies, rotating IPs or any other way around anti-bot protection.
- Sites whose terms forbid scraping.
- User accounts and authentication (hackathon build; see the README's known limitations).
- Unbounded loops, nested loops, free-text expressions or regex in flows.
