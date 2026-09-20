
# Design Decisions

This document separates choices verified in code from reasons inferred from the implementation.

## React/Vite + FastAPI

**Documented by code:** the active entrypoints are React/Vite and FastAPI.

**Inferred rationale:** this separates browser UI from Python services while leaving older Streamlit modules outside the production runtime.

## PostgreSQL + local filesystem fallback

**Documented:** `storage.py` chooses Postgres when `DATABASE_URL` is available and otherwise the application uses local JSON/filesystem state.

**Inferred rationale:** production needs durable storage while local development benefits from a simple fallback.

## Hybrid BM25 + vector retrieval

**Documented:** `retrieve_hybrid()` fuses BM25 and optional pgvector ranks with RRF.

**Inferred rationale:** lexical retrieval keeps the feature operational when embeddings/pgvector are unavailable; vectors add semantic retrieval when configured.

## SSE streaming

**Documented:** chat uses FastAPI StreamingResponse with SSE and browser-side stream readers.

**Inferred rationale:** SSE fits one-way model-token delivery without introducing a websocket server.

## Cancellation with partial persistence

**Documented:** browser AbortController pairs with backend GeneratorExit handling and partial-message persistence.

**Inferred rationale:** a useful prefix should survive a student hitting Stop rather than disappearing.

## Source modes

**Documented:** `context_builder.py` defines full/summary/insights/off.

**Inferred rationale:** students can control source emphasis without requiring multiple retrieval APIs.

## Deterministic Socratic controller

**Documented:** `socratic_engine.next_phase()` is rule-based; no separate LLM triage call exists.

**Inferred rationale:** inspectable deterministic transitions reduce call count, simplify tests and make pedagogy easier to reason about.

## Bounded Gemini fallback

**Documented:** first model gets one transient retry, later fallback models are attempted once.

**Inferred rationale:** resilience without unbounded provider call multiplication.

## In-process jobs

**Documented:** `jobs.py` uses `asyncio.create_task` for embedding work and persists status.

**Inferred rationale:** the project keeps infrastructure small and avoids an external queue while background work remains modest.

## Free/zero-cost deployment constraint

**Documented:** Render is configured with the free plan and no external paid queue/vector service is provisioned.

**Inferred rationale:** minimizes fixed infrastructure cost. This does not guarantee every provider call is free under every quota/account.

## Atomic uploads

**Documented:** filesystem payloads use temp+fsync+replace; Postgres uses uniqueness-backed source reservations.

**Inferred rationale:** prevents partial file replacement and concurrent filename overwrites.

## Why the Socratic reference architecture was not copied

**Documented:** Marklyf reuses existing workspace chat/session/RAG/SSE infrastructure instead of adding the reference project's CrewAI/Flask/Next.js/auth/session stack.

**Inferred rationale:** the current application already supplies the boundaries the Tutor needs, so a second stack would add duplication and cost without evidence it is necessary.
