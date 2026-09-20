
# Research

## Research modes

The current React UI exposes:

- **Quick** — direct normal model response;
- **Web** — Tavily retrieval + Gemini synthesis;
- **Deep** — multi-section hybrid research;
- **Study** — hybrid research with notebook-aware study synthesis;
- **Socratic** — guided dialogue, documented separately.

## Web path

`main._stream_web()` calls Tavily with advanced search, up to eight results and raw content. It deduplicates URLs for the emitted source list, then builds a synthesis prompt and forwards it to the resilient Gemini stream.

The browser receives an SSE `sources` event followed by token/done events.

## Deep/Study path

`backend/research_engine.py` classifies the question, extracts explicit user headings, decomposes the request, retrieves notebook evidence when a notebook is selected, and retrieves web evidence with Tavily.

The number of planned sections is bounded by `MAX_RESEARCH_SECTIONS=12`. Independent research passes are executed in parallel using a bounded thread pool of up to three workers.

~~~mermaid
flowchart TD
  Q[Student question] --> C[Classify topic]
  C --> O[Build/parse outline]
  O --> P[Parallel research passes]
  P --> N[Notebook retrieval]
  P --> T[Tavily retrieval]
  N --> M[Merge + deduplicate]
  T --> M
  M --> V[Verification metadata]
  V --> G[Gemini synthesis stream]
  G --> X[Grounding-overlap check]
  X --> UI[SSE answer + warning]
~~~

## Evidence merge

The engine deduplicates web evidence by URL and notebook evidence by chunk identity, then computes authority/relevance-style fields used in the synthesis contract. The verification payload counts web sources, notebook chunks and high-authority sources and preserves conflict information instead of silently collapsing it.

## Explicit section behavior

Recent history shows specific hardening around explicit user section requests and nested headings. The research outline now keeps short explicit section names and no longer truncates an otherwise valid requested structure to an arbitrary five-item list.

## Synthesis contract

`build_synthesis_instruction()` requests a direct answer followed by structured sections, inline numeric citations, conflicting-source discussion where needed, and a closing summary or study-oriented takeaways. The deep output budget is 2500 tokens.

## Grounding safeguard

After a Deep/Study stream completes, `main._stream_deep_research()` calculates text overlap between the generated answer and the retrieved evidence. Default threshold is `APOLLO_GROUNDING_MIN_OVERLAP=0.4`. It emits `grounding_check` with verification status, overlap and an optional warning.

This is a heuristic guardrail, not a claim of factual verification.

## Persistence

Research responses inside workspace chat are persisted through the normal session/message path. No separate research-results table exists in the inspected schema.

## Failure and cancellation

Missing Tavily credentials are surfaced as provider errors. If Tavily returns no usable evidence, the web path fails instead of generating an evidence-free web answer. Browser cancellation uses the normal AbortController/SSE path.
