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

## Reflection

### Where AI helped most

`Pending`

### Where AI was wrong or misleading

`Pending` (record every AI mistake our tests or reviews caught, with the test name)

### What we did not delegate to AI

`Pending`
