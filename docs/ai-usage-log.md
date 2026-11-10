# AI Usage Log

Required by the event rules. Log every meaningful use of AI tools during the build. Real entries only.

## Tools used

| Tool | Used for |
|------|----------|
| Claude Code (Claude Opus 5.5) | Reading the rule book and committee feedback; architecture Q&A; drafting design, requirements, testing plan, judge checks, ADRs and README |
| Gemini / Claude API (in the product) | The sidebar agent that edits flows at design time. Never used during runs |

## Log

| Time | Member | Tool | What it was asked | What was accepted / changed / rejected | How it was verified |
|------|--------|------|-------------------|----------------------------------------|---------------------|
| ~09:50 | Kaleem | Claude Code | Read the rule book, idea submission, proposal, build plan and committee feedback, and summarise them | Accepted the summary. It also flagged inconsistencies between our documents (price grounding, verdict count, localhost demo blocked by our own URL guard) | Checked against the original documents |
| ~10:00 | Kaleem | Claude Code | Discuss architecture for a general no-code flow builder with a sidebar agent | **Changed:** we wanted Playwright click/scroll; AI pointed out it conflicts with the approved static-only scope and Render's 512 MB, so we kept a static engine with disabled browser nodes. Team chose React Flow, a configurable LLM, and an in-process scheduler with a keep-alive ping | Checked against the committee's required changes and Render free-tier limits |
| ~10:10 | Kaleem | Claude Code | Design publish lifecycle, schedule-in-flow, branches, per-flow alerts | **Changed by team:** schedule lives in the Trigger node; branches added; auth dropped for the hackathon. AI proposed that only the user can publish; team kept it | Team review |
| ~10:20 | Kaleem | Claude Code | Design record storage, loops and variables for price tracking and multi-link watching | Accepted `save_records` datasets, bounded `for_each` container, typed variables as `{"var"}` references (rejected template strings for injection safety) | Team review; to be verified by tests EC-29 – EC-48 |
| 10:35 | Kaleem | Claude Code | Write requirements, testing plan, judge checks, ADRs and README according to the judging criteria | Accepted as a starting point; all results left `Pending` until real runs | Team review pending |
| ~10:45 | Kaleem | Claude Code | Split the build into two parallel workstreams with frozen contracts, covering every feature | Accepted `specs/workstreams.md` (A: engine and platform, B: editor and agent) and `specs/contracts.md`, with a coverage matrix mapping every FR, NFR and edge case to a task | Coverage matrix checked against requirements.md |
| 10:50 | Kaleem | Claude Code | Move generated docs into `specs/`, then complete the template `docs/` files so everything is aligned | Accepted; template docs filled from `specs/`; links checked | Link check script; manual read-through pending |
| ~10:55 | Kaleem | Claude Code | Which tech stack should the sidebar agent use? | AI recommended a **hand-built agent loop (~150 lines) on the plain Gemini and Anthropic SDKs**, with our own provider adapter and no framework. **Team rejected this suggestion** and asked for framework options instead (see next entry) | Team decision |
| ~11:00 | Kaleem | Claude Code | Compare agent frameworks (plain SDKs, LangChain, LangGraph, OpenAI AgentKit, Google ADK, smolagents, PydanticAI) for the sidebar agent | **Team changed the AI's original suggestion from the ~150-line hand-built loop to PydanticAI.** Rejected OpenAI AgentKit (OpenAI-only, hosted), smolagents (executes generated code), LangGraph (too heavy). Docs updated: `FallbackModel` (Gemini → Claude), typed tools, `ModelRetry` on invalid edits, `FunctionModel` contract tests | API names to be checked against the PydanticAI docs before coding |
| ~11:05–11:16 | Usama | Claude Code | Build Workstream A M0: pyproject + test script (A1), Pydantic flow schema (A2), graph rules (A3), schema/TS export + example flows + engine stubs (A4), FastAPI skeleton with error handling, SPA serving and stub routes (A5) | Accepted after review. **Changed during the build:** added a draft validation mode (the first version rejected every half-built flow, which would block saving and make the agent loop on retries); removed the `follow_links` node (superseded by `for_each` + `fetch_item_page`); TS export set to `--maxItems=-1` to avoid huge tuple types | 81 tests (`bash scripts/test.sh`, ruff clean); manual smoke test of the running server (health, create flow, 404 JSON, SPA placeholder, SSE stub) |
| ~11:17–11:24 | Usama | Claude Code | Review M0 as a senior evaluator: find and fix bugs | Probed suspected weaknesses before changing code; **12 more defects found and fixed** (D-03 – D-14 in testing.md), each with a regression test. Notable: the API stored the raw draft instead of the validated one; the body limit was bypassable with chunked uploads, and the AI's first fix for it was itself wrong (FastAPI turned it into a 400) | 110 tests pass, ruff clean; chunked-upload limit re-checked with curl against real uvicorn (413, server stays up) |
| ~11:25–11:30 | Usama | Claude Code | Replace the in-memory flow store with the database (A7 tables, A8 repository) | Accepted. AI also found that the old version check could lose a save under a race and made it atomic. Added: Neon URL conversion for asyncpg (`sslmode`, `channel_binding`, statement cache off for the pooler), refuse to start on Render without `DATABASE_URL`, `/health` checks the database. First health test patched a read-only SQLAlchemy attribute; redesigned as `Database.ping()` | 120 tests on SQLite; real uvicorn killed and restarted, flow still there. **Not yet run on real Postgres** (Docker not running, no Neon URL yet): `test_postgres_round_trip` is ready, marked `live` |

## Reflection

### Where AI helped most

`Pending`

### Where AI was wrong or misleading

- **Agent stack (design time, ~10:55):** the AI first suggested a hand-built agent loop of about 150 lines on the raw provider SDKs, with our own adapter for Gemini and Claude. We overrode it and chose **PydanticAI**. It gives typed, validated tools, built-in Gemini → Claude fallback, `ModelRetry` for self-correction and scripted test models, without us writing and testing that plumbing ourselves.
- **Draft-mode gap (build, ~11:12):** the AI's first draft-mode validator skipped variable checks inside Condition rules, so a price rule could reference a URL-list variable. Caught by `tests/engine/test_flow_validation.py::test_draft_mode_still_refuses_unsafe_or_broken_structure[wrong_variable_type]`; fixed by checking condition variables in draft mode too.
- **Weak test (build, ~11:14):** the AI's first path-traversal test passed even if a file leaked. Caught in review; rewritten to assert that `pyproject.toml` content never appears (`tests/api/test_app.py::test_path_traversal_does_not_escape_web_dist`).
- `Pending`: record every further AI mistake our tests or reviews catch during the build, with the test name.

### What we did not delegate to AI

`Pending`
