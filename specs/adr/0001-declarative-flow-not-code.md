# ADR 0001: Flows are declarative JSON, never generated code

- **Status:** Accepted
- **Date:** 2026-11-10

## Context

The AI agent helps build a scraper from page content, which is untrusted input. Other tools (ScrapeGraphAI, llm-scraper, Parsera) generate Python or JavaScript scripts. Scripts are hard to audit, hard to validate, and running them means executing code the AI wrote. The committee requires schema validation, selectors and fixed field types only, no executable code and no unguarded regex.

## Decision

A flow is a JSON document: typed nodes, edges and typed variables. It's validated by Pydantic models with `extra="forbid"`:
- fixed node types
- length-limited CSS selectors that must parse
- fixed field types and condition operators
- variable references as `{"var": name}` objects, never string templates
- no regex and no code anywhere

The engine *interprets* the flow. It never executes anything from it.

## Consequences

- Every agent edit can be validated before it touches the draft, and a hostile page can at most produce a valid but useless flow.
- The flow is readable, diffable and shown on a canvas, so a non-developer can review it before publishing.
- Less expressive than code: no custom transforms or free-form expressions. New capabilities need a new node type.
