# ADR 0002: Static HTTP engine, no headless browser

- **Status:** Accepted
- **Date:** 2026-11-10

## Context

We wanted general automation (click, scroll). That needs a headless browser such as Playwright. But:
- Chromium uses about 300–400 MB, and Render free has 512 MB.
- Our approved scope is static HTML only.
- A browser makes requests we don't control (subresources, scripts), which widens the SSRF surface.

## Decision

The engine uses httpx (all requests through `safe_fetch`) and selectolax. Pages that need JavaScript get the UNSUPPORTED verdict with a clear message. Browser nodes (click, scroll, type, wait for element) are visible in the palette but disabled and rejected at publish, which leaves room to add them later.

## Consequences

- Small, fast and testable; fits the free host; every request passes one guard.
- JavaScript-only stores are out of scope. Our primary user is reframed as sellers watching server-rendered stores.
- Adding browser support later means a separate worker and per-request IP checks inside the browser.
