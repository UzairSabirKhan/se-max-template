# ADR 0003: AI at design time only; only the user publishes

- **Status:** Accepted
- **Date:** 2026-11-10

## Context

LLM-per-run scrapers cost money on every run, are slower, and can give different or invented values for the same page. The judges check that no AI call happens during a run. An agent that could publish or run flows would be one prompt-injected page away from scheduling something nobody reviewed.

## Decision

- The sidebar agent edits only the **draft**, through typed tools. Each edit is validated and shown as a pending change the user accepts or rejects.
- The agent has no tool to publish, run, pause, delete or execute code. Publishing is a user action.
- `app/engine/` never imports `app/ai/`. Runs record `ai_calls = 0`, and a test runs the engine with the AI client patched to raise.
- The AI provider sits behind one adapter (`AI_PROVIDER=gemini|claude`), so the demo survives one provider failing.

## Consequences

- Runs are free of AI cost, deterministic and work when the AI is down.
- Users must review and publish; there is no silent auto-repair. This is our differentiator against Crawlr and Scrapewright.
- Two SDKs to test; the contract tests use a recorded reply so CI doesn't need an API key.
