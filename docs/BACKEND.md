
# Backend

## Entrypoint and composition

The active production command is `uvicorn phase2_app:app`. `backend/phase2_app.py` imports `main.app` and registers five route modules:

1. `phase1_routes.register`
2. `phase2_routes.register`
3. `phase3_routes.register`
4. `socratic_routes.register`
5. `history_routes.register`

`main.py` creates the FastAPI application and owns cross-cutting middleware/configuration and the original core route set.

## Module map

| Path | Purpose | Key responsibilities |
|---|---|---|
| `backend/main.py` | Application core | health, notebooks, basic chat, uploads, jobs, diagrams, provider streaming |
| `backend/phase1_routes.py` | Workspace layer | chat/workspace, sessions, notes, Socratic state read |
| `backend/phase2_routes.py` | Source lifecycle | URL/YouTube ingestion, retry, refresh, capabilities |
| `backend/phase3_routes.py` | Studio | report/slide/podcast/transform/video and mindmap |
| `backend/socratic_engine.py` | Tutor engine | state, phases, prompts, mastery, Quick Check helpers |
| `backend/socratic_routes.py` | Tutor API | mastery, Quick Check, config |
| `backend/research_engine.py` | Research orchestration | decomposition, evidence retrieval, dedup, synthesis contract |
| `backend/context_builder.py` | Context contract | source modes, retrieval, insight/summary packing |
| `backend/rag_service.py` | Knowledge service | notebook CRUD, source payloads, chunks, hybrid retrieval |
| `backend/source_ingestion.py` | Web ingestion | SSRF-safe URL fetch, HTML parsing, YouTube transcript |
| `backend/storage.py` | Persistence | PostgresStore, migrations, pgvector detection |
| `backend/workspace_service.py` | Sessions/notes | DB/filesystem CRUD and Socratic state serialization |
| `backend/jobs.py` | Background work | in-process embedding tasks + durable job records |
| `backend/analytics_service.py` | Learning telemetry | streak/activity/mastery aggregation |
| `backend/request_limits.py` | Request hardening | ASGI body-limit middleware |
| `backend/error_classifier.py` | Error policy | status mapping and retryability |
| `backend/phase3_common.py` | Gemini resilience | fallback model chain and structured outputs |

## Request lifecycle

`/api/chat/workspace` validates notebook/session ownership, creates the session when needed, persists the user message, builds context, creates Socratic state if requested, invokes `main._stream_model`, forwards SSE, and persists generated assistant text plus Socratic state.

The same route catches `GeneratorExit` and ordinary exceptions after partial generation and persists the generated prefix, so cancellation does not silently erase the partial reply.

## Input validation

Pydantic request models enforce bounds such as topic lengths, source list sizes, page sizes and numeric ranges. Uploads are separately limited by `request_limits.py` and explicit file-size checks.

## Provider and streaming boundaries

The backend supports Groq streaming as the normal chat path. If Groq fails and Gemini is configured, it emits a fallback event and switches to the configured Gemini fallback model. Web/Deep/Study research use Tavily + Gemini. Studio and Quick Checks use Gemini through `phase3_common.py`/the Socratic engine.

## Persistence

Application services first check `STORE`. When Postgres is configured, SQL operations are used. Otherwise `rag_service.py` and `workspace_service.py` serialize state under `APOLLO_DATA_DIR`.

## Jobs

There is no external queue. `backend/jobs.py` stores job metadata and starts embedding work with `asyncio.create_task`. PostgreSQL persists job state when available; filesystem fallback keeps it in process memory.

## Security and errors

CORS comes from `APOLLO_CORS_ORIGINS`. Rate limiting is a bounded in-memory sliding window. Error classification maps provider/source failures to user-safe HTTP/SSE messages, with special handling for retryable provider failures.

## Known architectural caveat

`backend/context_builder.py` contains a compatibility hook that monkey-patches `FastAPI.__init__` to register Phase 1 routes automatically. The production entrypoint also explicitly calls `register_phase1(app)`. Tests and route registration are written to avoid duplicate registration, but this is an unusual compatibility mechanism and should be treated carefully when refactoring.
