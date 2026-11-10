# ScrapeOnce

> AI-Powered SE-MAX · CUI Tech Fest FA'26 · Team: LazyLoaders

**Approve once. Explain every change.**

![CI](https://github.com/<owner>/<repo>/actions/workflows/ci.yml/badge.svg)

## What it does

ScrapeOnce is a no-code builder for scraping workflows. You describe what to track, and a sidebar AI agent builds a visual flow on a canvas: fetch pages, extract fields, loop, check conditions, store records, alert. You review it and publish it. After that, every scheduled or manual run is plain code with **no AI calls**. Each run tells you whether the site blocked you, broke, removed an item or really changed a price, with evidence.

## Problem and user

A small online seller checks 5–20 competitor prices on independent stores every day. Checking by hand misses changes. Hand-written scrapers need a developer and break silently when a layout changes. AI scrapers pay for an LLM on every run and can give different answers for the same page.

ScrapeOnce uses AI once, to help build the flow. Runs are free, deterministic and checked, so a layout change raises a "Site changed" alert instead of storing wrong or empty prices.

## Live deployment

- **URL:** `Pending`
- **Platform:** Render (one web service) + Neon Postgres
- The app's own mock shop is at `<URL>/shop`. It's the only site scraped during the event, and all its data is invented.

The service may take 30–60 s to wake on the first request.

## Judge quick start (under 5 minutes)

1. Open the live URL and click **New flow**.
2. In the sidebar, ask the agent: *"Track the prices of every product on `<URL>/shop` and alert me when a price changes or a new product appears."* Accept its changes, then click **Dry run** to see the preview.
3. Click **Publish**, then **Run now**. The **Runs** tab shows verdict **OK** and **AI calls: 0**.
4. Open `<URL>/shop/admin`, change a price, then **Run now**. The **Alerts** tab shows "Rs X → Rs Y".
5. In `/shop/admin`, switch to **layout v2**, then **Run now**. The verdict is **BROKEN**: "Site changed: price missing on 12 of 12 items". The **Data** tab still shows the last good prices.
6. In a Fetch Page node, try `http://169.254.169.254` and **Dry run**. It's refused with the reason.

The [judge checks](judge-checks.md) map every check to its test and live steps.

## Test accounts

No accounts: the hackathon build has no login (see Known limitations).

## How it works

```
Sidebar agent ──edits draft (typed tools, validated)──▶ Flow (JSON) ──user clicks Publish──▶ Published flow
                                                                                   │
                         APScheduler / Run now ──▶ Engine (no AI) ──safe_fetch──▶ page
                                                     │
          check_page verdict ─▶ save_records (new / changed / removed) ─▶ conditions ─▶ alerts
```

- **Nodes:** Trigger (schedule), Fetch Page, Paginate, Extract List, For Each (bounded loop), Fetch Item Page, Extract Fields, Condition (true/false branches), Wait, Check Page, Save Records, Alert, Results.
- **Variables:** typed inputs such as a list of links or a price limit, so "alert me when any of these prices drops" works across many product pages.
- **Verdicts:** BLOCKED, UNSUPPORTED (needs JavaScript), BROKEN, SUSPECT, CHANGED, OK, UNKNOWN, checked in that order. A captcha page never looks like "all products removed".

Full design: [docs/design.md](design.md).

## Safety controls

- **No AI at runtime.** The engine never imports the AI module, and a test proves it. Every run records `ai_calls = 0`.
- **The agent can't publish.** It edits a draft; the user reviews and publishes.
- **URL safety.** http/https only; internal, private and metadata addresses refused after DNS lookup and after every redirect; timeouts; 2 MB limit; HTML only; domain allowlist.
- **Flow safety.** Strict schema; fixed node types, field types and operators; no code, no regex, no template strings.
- **No evasion.** No proxies, no CAPTCHA solving, honest User-Agent, per-domain rate limit.
- **No personal data.** Fields like email, phone or CNIC are rejected.

## Related work

Generating selectors once and running without AI is **not new**:
- **Crawlr** and **harvest-agent** (as noted by the committee) generate selectors once.
- **Crawl4AI** `generate_schema` does the same as a library.
- **Parsera** and **Kadoa** (enterprise) do it as paid services.

Crawlr, Kadoa and Scrapewright repair scrapers automatically, without review. Change monitors such as Visualping and Distill are known for false alerts.

ScrapeOnce's difference:
- a **non-developer interface** (canvas, agent, run history, alerts)
- **every change goes through validation, a dry run and the user's publish**
- **every run explained** by one verdict with evidence

The checks are adapted from Zyte's Spidermon (field coverage, item count against past runs).

## Run locally

### Prerequisites

Python 3.12, [uv](https://docs.astral.sh/uv/), Node 20, a Postgres database (Neon free tier works).

### Setup

```
uv sync
cd web && npm install && npm run build && cd ..
cp .env.example .env   # then fill in values
```

### Environment variables

Names only; values go in `.env` (see [.env.example](.env.example)).

`DATABASE_URL`, `AI_PROVIDER`, `AI_MODEL`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `ALLOWED_DOMAINS`, `PUBLIC_BASE_URL`

### Run

```
uv run uvicorn app.main:app --workers 1
```

Open http://localhost:8000.

Locally, the URL guard correctly refuses `localhost`, so a local app can't scrape its own mock shop. Use the deployed mock shop, or run the tests, which serve mock-shop pages through a mock transport.

### Run tests

```
bash scripts/test.sh          # lint + all tests except live (what CI runs)
uv run pytest -m live         # real AI + deployed URL, needs .env
```

## Known limitations

- **No authentication.** Anyone with the URL can edit, publish or delete flows. Demo only.
- **Static HTML only.** Pages that need JavaScript get a clear UNSUPPORTED message. Browser nodes are shown but disabled.
- **Scheduled runs pause** if Render sleeps and the keep-alive ping fails. "Run now" always works.
- **No version history.** Republishing replaces the live flow.
- **Loops** are limited to 25 items, run one at a time, and can't be nested.
- **Price drift** onto a different element (for example an old struck-through price) that still parses is not always caught. We catch structural breakage, not every wrong value.

## What was built vs not

`Pending` (filled at the end: each FR marked Done / Cut in [requirements.md](requirements.md))

## Demo script (3 minutes)

| Time | What we show | Judge check |
|---|---|---|
| 0:00–0:20 | Problem, user, one-line pitch | — |
| 0:20–0:45 | `http://169.254.169.254` and `/shop/redirect-internal` refused with reasons | 1 |
| 0:45–1:30 | Ask the agent to track the shop; pending changes on the canvas; accept; dry run preview; **Publish** | — |
| 1:30–1:55 | **Run now** twice: identical output, **AI calls: 0**, real scheduled runs in history | 2, 4 |
| 1:55–2:30 | Change a price → alert with old → new; switch to layout v2 → **BROKEN**, "Site changed", nothing stored | 3 |
| 2:30–3:00 | Huge page / slow page give clean errors; CI badge; traceability table; an AI mistake our tests caught | 5 |

## Documentation

- [Requirements](requirements.md)
- [Design](design.md)
- [Testing](testing.md)
- [AI usage log](ai-usage-log.md)
- [Judge checks](judge-checks.md)
- [Architecture decisions](adr/)
- [Contracts](contracts.md) · [Workstreams](workstreams.md)

## Team

| Name | Role |
|------|------|
| Muhammad Usama (lead) | Engine, backend, database, scheduler |
| Umar Hassan | AI agent and testing |
| Kaleem Hassan | Frontend (React Flow), mock shop, deployment |
