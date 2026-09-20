
# Marklyf Technical Documentation

This directory is the implementation record for the Marklyf product as it exists on `phase8/production-hardening` at commit `87558a1d9d9ef34429cadf9de51020d0c18d63c5` (20 September 2026 audit). GitHub still names the repository **Apollo**; the active product UI and backend copy are **Marklyf**.

## Status vocabulary

- **Current production path** — code wired into `frontend/src/main.jsx → AppPhase6.jsx` and `backend/phase2_app.py → FastAPI`.
- **Legacy / Non-Production** — retained code that is not part of the Cloudflare + Render path.
- **Partially Implemented** — UI or backend exists, but the requested capability is incomplete.
- **Planned / Not Implemented** — code or docs explicitly indicate the feature is deferred or the UI is a placeholder.
- **Experimental** — present but not the normal production workflow.

## Architecture at a glance

~~~mermaid
flowchart LR
  U[Student] --> F[React/Vite\nfrontend/src/main.jsx\nAppPhase6.jsx]
  F -->|HTTP + SSE| B[FastAPI\nbackend/phase2_app.py]
  B --> C[Chat + Sessions]
  B --> R[RAG + Sources]
  B --> S[Socratic Engine]
  B --> Q[Research]
  B --> T[Studio]
  B --> P[Progress]
  C --> D[(PostgreSQL)]
  R --> D
  S --> D
  Q --> D
  T --> D
  D --> X[Filesystem fallback\nlocal/dev only]
  B --> G[Groq]
  B --> G2[Gemini]
  B --> TV[Tavily]
~~~

## Documentation map

| Area | Document |
|---|---|
| Whole-system architecture | [ARCHITECTURE.md](./ARCHITECTURE.md) |
| Product and request lifecycles | [SYSTEM_OVERVIEW.md](./SYSTEM_OVERVIEW.md) |
| React/Vite frontend | [FRONTEND.md](./FRONTEND.md) |
| FastAPI backend | [BACKEND.md](./BACKEND.md) |
| HTTP/SSE API | [API.md](./API.md) |
| PostgreSQL / filesystem persistence | [DATABASE.md](./DATABASE.md) |
| Model/provider integration | [AI_AND_MODELS.md](./AI_AND_MODELS.md) |
| RAG and source ingestion | [RAG_AND_SOURCES.md](./RAG_AND_SOURCES.md) |
| Chat/session lifecycle | [CHAT_AND_SESSIONS.md](./CHAT_AND_SESSIONS.md) |
| Research | [RESEARCH.md](./RESEARCH.md) |
| Socratic Tutor | [SOCRATIC_TUTOR.md](./SOCRATIC_TUTOR.md) |
| Studio | [STUDIO.md](./STUDIO.md) |
| Progress/analytics | [PROGRESS_AND_ANALYTICS.md](./PROGRESS_AND_ANALYTICS.md) |
| Planner | [STUDY_PLANNER.md](./STUDY_PLANNER.md) |
| Security hardening | [SECURITY.md](./SECURITY.md) |
| Deployment | [DEPLOYMENT.md](./DEPLOYMENT.md) |
| Tests | [TESTING.md](./TESTING.md) |
| Environment/config | [CONFIGURATION.md](./CONFIGURATION.md) |
| Developer workflow | [DEVELOPMENT.md](./DEVELOPMENT.md) |
| Architectural rationale | [DESIGN_DECISIONS.md](./DESIGN_DECISIONS.md) |
| Failure modes | [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) |
| Historical milestones | [CHANGELOG.md](./CHANGELOG.md) |

## Feature status

| Feature | Status | Frontend | Backend | Persistence | Tests | Notes |
|---|---|---:|---:|---:|---:|---|
| Chat | Current production path | ✓ | ✓ | ✓ | ✓ | SSE |
| Notebook/workspace | Current production path | ✓ | ✓ | ✓ | ✓ | Postgres or local fallback |
| Source upload | Current production path | ✓ | ✓ | ✓ | ✓ | File/URL/YouTube |
| Hybrid RAG | Current production path | ✓ | ✓ | ✓ | ✓ | BM25 + optional pgvector |
| Chat/session history | Current production path | ✓ | ✓ | ✓ | ✓ | Cursor pagination |
| Deep Research | Current production path | ✓ | ✓ | ✓ | ✓ | Tavily + notebook evidence |
| Study Research | Current production path | ✓ | ✓ | ✓ | ✓ | Same hybrid research engine |
| Socratic Tutor | Current production path | ✓ | ✓ | ✓ | ✓ | Uses normal workspace chat transport |
| Quick Checks/mastery | Current production path | ✓ | ✓ | ✓ | ✓ | Placement is deferred |
| Studio: slides/report/podcast/transform | Current production path | ✓ | ✓ | ✓ | ✓ | Source-grounded |
| Studio: mind maps/diagrams | Current production path | ✓ | ✓ | ✓ | ✓ | SVG generation/rendering |
| Studio: video | Partially Implemented | ✓ | ✓ | ✓ | ✓ | Storyboard only |
| Progress dashboard | Current production path | ✓ | ✓ | ✓ | ✓ | Chat activity + Socratic mastery |
| Study Planner | Planned / Not Implemented | Placeholder | No active API | No planner schema | No | React nav placeholder |
| Settings/Profile | Planned / Not Implemented | Placeholder | No active API | No | No | React nav placeholder |
| Legacy Streamlit tutor/studio | Legacy / Non-Production | — | — | Local/legacy | — | Do not use as current architecture |

## Production entry points

The production frontend starts at `frontend/src/main.jsx`, which renders `AppPhase6`. The production backend starts at `backend/phase2_app.py`, which imports `main.app` and registers Phase 1/2/3, Socratic, and history routes.

The root `streamlit_app.py`, `tutor_engine.py`, `video_generator.py`, and other root-level Python UI modules remain in the repository but are not the production Cloudflare/Render path.

## Constraints

The repository is intentionally small: FastAPI + React/Vite, PostgreSQL when configured, an in-process async job runner, bounded provider fallbacks, and free Render deployment configuration. The code does not introduce an external queue or multi-agent framework for Socratic tutoring.

**Authentication note:** there is no application-level user authentication layer in the inspected production routes. The frontend generates a persistent `apollo-user-id` in browser localStorage and sends it as `user_id`; this is data scoping, not verified identity or authorization.

## Canonical rule

When source code and older docs disagree, trust the code on the audited branch. In particular, `docs/SOCRATIC_DESIGN.md` was written against an older intermediate name (`socratic_service.py`); the active implementation is `backend/socratic_engine.py`.
