# ADR 0004: One service with an in-process scheduler; the schedule lives in the flow

- **Status:** Accepted
- **Date:** 2026-11-10

## Context

Free hosts limit background jobs: Vercel Hobby cron runs once a day, and Render free services sleep after about 15 minutes idle. We want the simplest deploy: one backend service.

## Decision

- One Render web service runs FastAPI, serves the React build and the mock shop, and runs **APScheduler** in process with **one uvicorn worker**. More workers would each start a scheduler and fire runs twice.
- The schedule is the flow's **Trigger node** (`manual`, `interval` ≥ 1 min, `daily`). There's no separate schedule table. At startup, and on every publish, pause or unpublish, jobs are rebuilt from the published flows.
- A free cron-job.org ping to `/health` every 5 minutes keeps the service awake. **Run now** always works.
- A per-flow lock prevents overlapping runs.

## Consequences

- One deploy, one log, nothing to keep in sync.
- If the ping fails while Render sleeps, scheduled runs pause until the next request. We list this in the known limitations.
- Doesn't scale past one worker. Fine for the demo; a real deployment would move the scheduler to a separate worker.
