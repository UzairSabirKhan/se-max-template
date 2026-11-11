# Judge Checks

Each judge check and each of the committee's required changes, with where it's built, the test that proves it, and how to see it on the live app.

Live URL: `Pending` · Final commit: `Pending`

## 1. The judges' five checks

| # | Check | Requirement | Automated test | See it live |
|---|---|---|---|---|
| 1 | Internal and private URLs are refused | FR-18, FR-19, NFR-01 | `tests/test_safe_fetch.py::test_refuses_internal`, `test_dns_to_private`, `test_redirect_to_internal`, `test_scheme` (EC-01 – EC-09) | Create a flow → Fetch Page node → enter `http://169.254.169.254` or `http://127.1` → **Dry run**. You'll see a refusal with the reason. Also try `/shop/redirect-internal` (redirects to the metadata IP) |
| 2 | No AI call during a scheduled or manual run | FR-16, FR-17, NFR-02 | `tests/test_zero_ai.py` (the engine imports nothing from `app.ai`; runs pass with the AI client patched to raise; `ai_calls == 0`) | Open any published flow → **Runs** tab. Every scheduled and manual run shows **AI calls: 0** |
| 3 | A layout change raises an alert instead of storing wrong or empty data | FR-28, FR-31, NFR-05 | `tests/test_classifier.py::test_layout_v2` (EC-25): verdict BROKEN, 0 records written, alert raised | Open the demo flow → mock shop admin → **Switch to layout v2** → **Run now**. Verdict **BROKEN**, "price missing on 12 of 12 items", the **Alerts** tab shows "Site changed", the **Data** tab still shows the last good prices |
| 4 | The same page always produces the same output | FR-21, NFR-03 | `tests/test_determinism.py` (EC-54: 20 runs on one fixture → identical output) | **Run now** twice on an unchanged shop. Both runs show **OK** with every item `same`, and the record values are identical |
| 5 | Bad URLs, timeouts, huge pages and malformed AI specs are handled without crashing | FR-03, FR-11, FR-18, NFR-04 | `tests/test_safe_fetch.py` (EC-10 – EC-14), `tests/test_flow_schema.py` (EC-16 – EC-18), `tests/test_agent_contract.py` (EC-22) | Fetch `/shop/huge` (over 2 MB), `/shop/slow` (slow drip), `/shop/file.pdf`, or type `not a url`. Each gives a clear error, never a server error |

## 2. The committee's required changes

| # | Required change | Where it is | Proof |
|---|---|---|---|
| 1 | **Related work** cites tools that already generate selectors once (harvest-agent, Crawlr); our differentiator is human-approved, test-gated changes and a non-developer interface | README "Related work"; [design.md](design.md) | README section |
| 2 | **Scheduling** fits the free host's limits; there's a "Run now" action and visible run history | Trigger node + APScheduler in the single web service: Railway (always on) or Render (kept awake by a cron-job.org ping); we avoid Vercel Hobby cron, which runs once a day); **Run now**; **Runs** tab (FR-15 – FR-17) | `test_runner::test_lock`, `test_publish::*`; Runs tab shows real scheduled runs |
| 3 | **URL safety**: block private, internal and metadata addresses after DNS lookup and redirects; http/https only; timeouts and size limits | `app/engine/fetcher.py` `safe_fetch()`, used for every request (FR-18) | EC-01 – EC-14 |
| 4 | **Spec safety**: page content is untrusted; every AI-generated spec is schema-validated; selectors and fixed field types only; no code; no unguarded regex | Pydantic flow schema with `extra="forbid"`, fixed node types, field types and condition operators; no regex anywhere; variables are typed references, not templates (FR-03, FR-11, FR-12, FR-23) | EC-16 – EC-24 |
| 5 | **Scope**: static HTML only, with a clear message for JavaScript pages | httpx + selectolax engine; UNSUPPORTED verdict; browser nodes disabled (FR-20, FR-27) | EC-28, EC-56 |
| 6 | **Change detection** separates broken selectors, removed items, error or block pages and real value changes, and it's tested | `check_page` verdict order + `save_records` labels (FR-28 – FR-30); the 7-verdict table in [design.md](design.md) | EC-25 – EC-39 |
| 7 | **Demo data** comes from a mock site we control; no real stores or personal data | `/shop` mock shop with invented data (FR-36); PII fields rejected (FR-34) | EC-09, EC-24 |
| 8 | **Scope cuts**: AI repair and version history are cut-list items; the core is generate, validate, preview, approve, deterministic run, change and breakage detection, alerts | FR-37 and FR-38 are marked Stretch; the core maps to FR-06/FR-13 (generate + preview), FR-03 (validate), FR-14 (approve = publish), FR-16/FR-21 (deterministic run), FR-28 – FR-31 (detection + alerts) | [requirements.md](requirements.md) |
| 9 | **Fallback**: if AI is unavailable at setup, show a clear error; existing approved scrapers keep running | FR-10; runs never import AI (NFR-02) | `test_ai_unavailable::*` (EC-52) |

## 3. Evidence for each judging criterion

| Criterion (weight) | Where to look |
|---|---|
| Shippable product (25%) | Live URL in the README; judge quick start; the demo flow on the mock shop |
| Testing and edge cases (20%) | [testing.md](testing.md): 56 edge cases, results from CI, traceability table from a real run; CI badge |
| Engineering quality and Git (13%) | Feature branches and PRs with green CI; [ADRs](adr/); small commits through the day |
| Requirements and design (12%) | [requirements.md](requirements.md) (FR/NFR with measurable targets); [design.md](design.md) (architecture, flow model, verdict table, threat model) |
| Demo, README and Q&A (12%) | [README](README.md); 3-minute demo script in the README |
| Market value (10%) | Problem and users in [requirements.md](requirements.md); cost argument (AI tokens only at setup, not per run) |
| Responsible AI (8%) | "AI proposes, code validates, the user publishes"; zero-AI test; prompt-injection test; [AI usage log](ai-usage-log.md) including mistakes our tests caught |
