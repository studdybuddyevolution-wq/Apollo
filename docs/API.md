
# API

All routes below are taken from the FastAPI code on the audited branch. There is no JWT/session auth layer in these route definitions; `user_id` is used for application-level scoping.

## Health and capabilities

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Provider/storage/configuration health metadata |
| GET | `/api/capabilities` | Frontend capability/model information |

## Chat

| Method | Path | Behavior |
|---|---|---|
| POST | `/api/chat` | Non-notebook chat; SSE |
| POST | `/api/chat/workspace` | Notebook-scoped persisted chat; SSE; Socratic mode also uses this route |

Core workspace request fields include `messages`, `model`, `notebook_id`, `notebook_title`, `active_sources`, `source_modes`, `session_id`, `user_id`, `web_enabled`, `research_mode`, `socratic_topic`, `socratic_score`, `socratic_force_advance` and `socratic_state`.

SSE event types emitted by the active chat stack include session/start/token/sources/done plus fallback/restart/grounding_check/socratic_state/error depending on path.

## Notebooks

| Method | Path |
|---|---|
| GET | `/api/notebooks` |
| POST | `/api/notebooks` |
| GET | `/api/notebooks/{notebook_id}` |
| PATCH | `/api/notebooks/{notebook_id}` |
| DELETE | `/api/notebooks/{notebook_id}` |

Notebook CRUD is scoped by `user_id`.

## Sources

| Method | Path |
|---|---|
| GET | `/api/notebooks/{notebook_id}/sources` |
| POST | `/api/notebooks/{notebook_id}/sources` |
| DELETE | `/api/notebooks/{notebook_id}/sources/{source_name}` |
| POST | `/api/notebooks/{notebook_id}/sources/url` |
| POST | `/api/notebooks/{notebook_id}/sources/youtube` |
| POST | `/api/notebooks/{notebook_id}/sources/{source_name:path}/retry` |
| POST | `/api/notebooks/{notebook_id}/sources/{source_name:path}/refresh` |
| POST | `/api/notebooks/{notebook_id}/search` |
| POST | `/api/notebooks/{notebook_id}/sources/{source_name}/insights` |
| GET | `/api/notebooks/{notebook_id}/sources/{source_name}/insights` |

The generic upload route accepts multipart file input. URL/YouTube routes call the explicit ingestion layer. Source search returns retrieved chunk metadata/context.

## Sessions and notes

| Method | Path |
|---|---|
| GET | `/api/notebooks/{notebook_id}/sessions` |
| POST | `/api/notebooks/{notebook_id}/sessions` |
| PATCH | `/api/notebooks/{notebook_id}/sessions/{session_id}` |
| DELETE | `/api/notebooks/{notebook_id}/sessions/{session_id}` |
| GET | `/api/notebooks/{notebook_id}/sessions/{session_id}/messages` |
| GET | `/api/notebooks/{notebook_id}/sessions/{session_id}/socratic-state` |
| GET | `/api/notebooks/{notebook_id}/notes` |
| POST | `/api/notebooks/{notebook_id}/notes` |
| PATCH | `/api/notebooks/{notebook_id}/notes/{note_id}` |
| DELETE | `/api/notebooks/{notebook_id}/notes/{note_id}` |

History pagination adds `GET /api/sessions` and `GET /api/notebooks/{notebook_id}/sessions/{session_id}/messages/page`.

## Socratic Tutor

| Method | Path | Notes |
|---|---|---|
| GET | `/api/socratic/mastery` | All mastery records for a user |
| GET | `/api/socratic/mastery/{topic:path}` | One topic |
| POST | `/api/socratic/quick-check` | Generates one quick-check question |
| POST | `/api/socratic/quick-check/grade` | Grades one answer and adjusts mastery |
| GET | `/api/socratic/config` | Models, tier configuration, Maieutics bound |

The main Socratic conversation does **not** have a dedicated /api/socratic/chat endpoint; it stays on workspace chat with `research_mode="socratic"`.

## Studio and diagrams

| Method | Path |
|---|---|
| POST | `/api/notebooks/{notebook_id}/studio/slides` |
| POST | `/api/notebooks/{notebook_id}/studio/generate` |
| POST | `/api/notebooks/{notebook_id}/mindmap` |
| POST | `/api/portfolio/diagram` |

`studio/generate` accepts one of slides/report/podcast/transform/video. Video returns a storyboard JSON structure.

## Jobs and progress

| Method | Path |
|---|---|
| POST | `/api/jobs` |
| GET | `/api/jobs/{job_id}` |
| GET | `/api/progress/dashboard` |

## Error behavior

Common statuses are 400 for invalid input/state, 404 for missing notebook/session/resource, 413 for body/upload limits, 429 for rate limit, 502/503 for provider/generation failures, and 504 for Studio timeouts. Streaming errors are represented as SSE `error` events.

## Frontend callers

API helper paths live in `frontend/src/api/apolloApi.js`, `notebooksApi.js`, `sourceIngestionApi.js` and `studioApi.js`.
