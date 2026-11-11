# ScrapeOnce web (Workstream B)

React + TypeScript editor for ScrapeOnce flows: flow list, React Flow canvas, step palette, settings panel, assistant sidebar, and the Runs / Alerts / Data tabs.

## Run

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # type-check + build to web/dist (served by FastAPI)
```

## API mode

- `VITE_API_MODE=mock` (opt in, local only): an in-browser fake of the C3 REST API and C5 agent stream (`src/mocks/`). No backend needed. Seed data lives in `localStorage`; run `__resetMock()` in the browser console to restore it.
- `VITE_API_MODE=live` or unset (**default; what production builds use**): calls FastAPI at `/api` (Vite proxies `/api`, `/health` and `/shop` to `:8000` in dev).

## Layout

| Path | What |
|---|---|
| `src/types/contracts.ts` | Hand copy of `specs/contracts.md`. Switch to the generated `src/types/flow.ts` once A4 lands. |
| `src/lib/api.ts` | Typed client (`Api` interface), live implementation, `ApiError` |
| `src/lib/flow.ts` | Op application, pending marks, step numbers, light validation (mock only) |
| `src/lib/layout.ts` | dagre auto-layout, including `for_each` containers |
| `src/store/editor.ts` | Zustand editor state: draft, pending ops, issues, run progress |
| `src/editor/` | Canvas, nodes, edges, palette, settings, variables, assistant, test-run drawer |
| `src/tabs/` | Runs, Alerts, Data |

Fonts: Inter (UI) and JetBrains Mono (selectors, URLs), bundled via Fontsource.
