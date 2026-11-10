# ScrapeOnce

> AI-Powered SE-MAX · CUI Tech Fest FA'26 · Team: LazyLoaders

[![CI](https://github.com/muhammadusamahoyrr/ScrapeOne/actions/workflows/ci.yml/badge.svg)](https://github.com/muhammadusamahoyrr/ScrapeOne/actions/workflows/ci.yml)

## What it does

ScrapeOnce is a no-code builder for website-watching flows. You describe what to watch, and an AI assistant builds the flow on a canvas for you to review. Once you publish, the flow runs on its schedule with **no AI at all**, and it alerts you when prices change, new items appear, or the site's layout breaks.

## Problem and user

The user is a small seller or shopper who wants to know when competitors' prices move. They're not a developer: scraping scripts are out of reach, and paid monitoring tools are too expensive. Asking an AI every time is slow and costly, and it can't be trusted to notice when a page silently changes. ScrapeOnce uses AI only **once**, to set the flow up. Every run after that is plain rules: deterministic, cheap, and checked for breakage.

## Live deployment

- **URL:** https://scrapeonce-production-839d.up.railway.app (health check: [/health](https://scrapeonce-production-839d.up.railway.app/health))
- **Platform:** Railway (primary), Render (backup). One Docker image serves the editor, the API and the mock shop.

## How it works

```mermaid
flowchart TB
    subgraph BUILD["① Build once, with AI"]
        direction LR
        A["Describe what<br/>to watch"] --> B["Assistant proposes steps<br/>and tests every selector"] --> C["You review<br/>and Accept"] --> D["Publish<br/>(test run must pass)"]
    end
    subgraph RUN["② Every run, zero AI"]
        direction LR
        E["Schedule or<br/>Run now"] --> F["Fetch pages<br/>safely"] --> G{"Check page"}
        G -->|healthy| H["Save records<br/>new · changed · removed"] --> I["Conditions"] --> J["Alert<br/>Rs 1,250 → Rs 1,099"]
        G -->|layout changed<br/>or blocked| K["Site changed alert<br/>nothing stored"]
    end
    BUILD --> RUN
```

- **AI builds, code runs.** The assistant only edits a draft through typed tools; every edit is validated and shown for you to accept. It cannot publish, run or delete. Published runs never call AI (`ai_calls: 0` on every run, proven by a test).
- **Every run gets one verdict**, checked in this order: **Blocked** (error page, captcha) → **Unsupported** (needs JavaScript) → **Broken** (layout changed: fields missing, wrong item count, duplicates) → **Suspect** (a price moved more than 50%) → **Changed** / **OK**. A captcha page can never look like "all products removed", and a broken layout never stores empty prices.
- **Steps:** Schedule, Fetch page, Paginate, Extract list, Loop (open each item's page), Condition, Wait, Check page, Save records, Alert, Results. Variables hold a list of links to watch. Each step's settings show the data available from earlier steps.

## Safety

- **No internal requests:** http/https only; private, loopback and cloud-metadata addresses refused in any spelling, after DNS and on every redirect; the connection is pinned to the checked IP.
- **Bounded:** 15 s per page, 2 MB (after decompression), HTML only, 2 s between requests to a site, 120 s per run, loops of at most 25 items.
- **Flows are data, not code:** strict schema, fixed operators, no scripts, no regex, no templates; page text is treated as untrusted by the assistant.
- **Honest scraping:** a clear User-Agent, no CAPTCHA solving or proxies; during the event we only scrape our own demo shop with invented products.

## Judge quick start (under 5 minutes)

1. Open the live URL. The flow list asks **"What should we watch for you?"**
2. Click the suggestion **Track prices on the mock shop**. The assistant opens the mock shop, tests its selectors, and proposes the steps on the canvas in green.
3. Review the proposal, press **Accept**, then **Publish**. Publishing runs a test first and refuses a broken flow.
4. Press **Run now**. Each step lights up as it runs. The **Runs** tab shows the verdict, the evidence and **AI calls: 0**.
5. In the mock shop's admin page (`/shop/admin`), change a price and press **Run now** again. An alert appears in the **Alerts** tab, for example "Blue Kettle: Rs 1,250 → Rs 1,099 (−12%)".
6. Switch the shop to layout v2 in the admin page and run again. The run is marked **Broken**, nothing is saved, and the last good prices stay in the **Data** tab.

Step-by-step checks with what to look for are in [docs/judge-checks.md](docs/judge-checks.md).

## Test accounts

None. There is no sign-in, so every visitor can use the app directly.

## What is built and what is not

| Area | Status |
|---|---|
| Editor: flow list, canvas, step palette, settings forms, variables, test-run drawer, publish controls | Built |
| Assistant: PydanticAI agent with 16 typed tools, Gemini / Groq / Claude fallback, edits shown as proposals to accept or reject, no publish tool | Built and tested with scripted models |
| Flow schema and graph rules, flow storage with version checks | Built |
| `safe_fetch` (URL and IP checks, redirects, size and time limits), normalisers, mock shop | Built |
| Runner, `check_page` verdicts, `save_records`, conditions, alerts, scheduler, loops, paginate, SUSPECT, CSV export | Built |
| Variables at run time (watch a list of links), data selector for step settings | Built |
| PII value scan (FR-34; personal-data field NAMES are already refused) | Planned |
| Browser steps (click, scroll, type) | Not planned: shown greyed out, refused at publish |

The status of each requirement is in [docs/requirements.md](docs/requirements.md).

## Run locally

### Prerequisites

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Node.js 22 or newer and npm

### Setup

```bash
uv sync
npm --prefix web install
```

### Environment variables

Copy `.env.example` to `.env` and fill in what you need. Names only, never commit values:

| Name | Needed for |
|---|---|
| `DATABASE_URL` | Postgres. Leave empty locally to use a SQLite file; required on Railway and Render |
| `AI_MODEL`, `AI_FALLBACK_MODEL` | The assistant's models, e.g. `google:<gemini-model>`; the fallback may list several, comma-separated, such as `groq:<model>,anthropic:<claude-model>` |
| `GEMINI_API_KEY`, `GROQ_API_KEY`, `ANTHROPIC_API_KEY` | Keys for the models above. Without any, the assistant shows "offline" and everything else works |
| `GEMINI_API_KEY_2`, `GROQ_API_KEY_2`, `ANTHROPIC_API_KEY_2` | Optional second key per provider. When the first key fails (for example its quota runs out), the same model is tried with the second key before the next model |
| `PUBLIC_BASE_URL` | The app's public URL (for mock shop links) |

### Run

```bash
uv run uvicorn app.main:app --port 8000 --workers 1
```

```bash
npm --prefix web run dev
```

Open http://localhost:5173. The dev server forwards `/api`, `/health` and `/shop` to port 8000. To work on the UI without the backend, set `VITE_API_MODE=mock` in `web/.env`.

### Run tests

```bash
bash scripts/test.sh
```

This runs ruff and every test except `live` ones (those call a real model and need AI keys). Frontend type check and build:

```bash
npm --prefix web run build
```

### Deploy

The `Dockerfile` builds the editor and runs FastAPI with one worker (the scheduler runs inside the app). On Railway:

1. Add a PostgreSQL database to the project.
2. On the web service, set `DATABASE_URL` to `${{Postgres.DATABASE_URL}}`, plus `PUBLIC_BASE_URL` and the AI variables. Any public site can be tracked.
3. Deploy. `/health` returns `{"status":"ok","database":"ok"}` when it's up.

The app refuses to start on a host without `DATABASE_URL`, because the host's disk is wiped on every deploy and saved flows would be lost.

## Quality

- **451 automated tests** (`bash scripts/test.sh`), run by GitHub Actions on every push. They cover the judges' checks: internal URLs refused, no AI during runs, a layout change raising "Site changed" with nothing stored, the same page giving the same output 20 times, and bad input (huge or slow pages, malformed AI replies) handled without crashing.
- Every defect we found, including the AI's own mistakes, is in [docs/testing.md](docs/testing.md); how AI was used is in [docs/ai-usage-log.md](docs/ai-usage-log.md).

## Related work

Generating a scraper once and running it without AI is not new: **Crawlr** and **harvest-agent** (as noted by the committee) generate selectors once, **Crawl4AI** does it as a library, and **Parsera** and **Kadoa** offer it as paid services. Those repair scrapers automatically and leave failures unexplained; change monitors such as Visualping and Distill are known for false alerts.

ScrapeOnce's difference: a **no-code editor and assistant for non-developers**, **every change approved by the user** after a validated test run, and **every run explained** by one verdict with evidence.

## Known limitations

- Static HTML only. Pages that build themselves with JavaScript are reported as **Unsupported**, not scraped.
- The assistant is checked by tests with scripted model replies. A recorded real-model reply is still to be added (`uv run pytest -m live -k capture`, with AI keys).
- No sign-in: anyone with the URL can see and edit every flow. Fine for a judged demo, not for real users.
- The assistant's rate limit (10 messages a minute per client) is kept in memory, so it resets when the app restarts.

## Documentation

- [Requirements](docs/requirements.md)
- [Design](docs/design.md)
- [Testing](docs/testing.md)
- [AI usage log](docs/ai-usage-log.md)
- [Judge checks](docs/judge-checks.md)
- [Contracts between the two workstreams](specs/contracts.md) and [workstreams](specs/workstreams.md)
- [Architecture decisions](specs/adr/)

## Team

| Name | Role |
|------|------|
| Muhammad Usama | Workstream A: engine, platform, database, deploy |
| Kaleem Hassan | Workstream B: editor, assistant, docs and demo |
