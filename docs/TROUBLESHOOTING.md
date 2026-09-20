
# Troubleshooting

## Frontend build failure

**Symptom:** Vite/npm install/build fails.

**Inspect:** `frontend/package.json`, `vite.config.js`, Node/npm version and dependency install output.

**Safe action:** run `npm.cmd install` followed by `npm.cmd run build`. Do not change backend code to solve a frontend bundle failure.

## Backend startup failure

**Inspect:** `backend/requirements.txt`, import traceback, `DATABASE_URL` and provider environment names.

Run:
`uvicorn phase2_app:app --reload --port 8000`

The application can start without provider secrets, but provider-dependent requests will fail clearly.

## Database connection / durability

**Symptom:** health reports filesystem storage rather than durable database storage.

**Inspect:** `DATABASE_URL` and `backend/storage.py`.

**Safe action:** restore the correct Postgres URL. Do not use filesystem fallback as a production persistence fix.

## Source upload returns 413

Check:
- `APOLLO_MAX_UPLOAD_BYTES`;
- the request body middleware;
- actual file size;
- multipart envelope size.

Default per-file limit is 25 MiB.

## Web URL source rejected

Inspect `backend/source_ingestion.py`.

Common causes:
- non-HTTP(S) URL;
- private/local/reserved address;
- redirect to an unsafe address;
- more than four redirects;
- download larger than 8 MiB;
- page has no readable text.

## YouTube source fails

Check that the URL resolves to a supported 11-character video ID and that an English transcript (or requested language) is actually available.

## Retrieval is empty or weak

Check:
1. source status is `indexed`;
2. selected source mode is not `off`;
3. notebook/user scope is correct;
4. `GEMINI_API_KEY` is set if vector retrieval is expected;
5. pgvector is available if vector search is expected.

BM25 should continue to work without vectors.

## Gemini/provider failures

Inspect `backend/phase3_common.py` and `error_classifier.py`. Transient provider errors can trigger bounded retries/fallbacks. Persistent configuration errors usually indicate a bad/missing key or invalid model.

## Stream is interrupted

Frontend:
- inspect the browser network stream;
- inspect AbortController usage in `frontend/src/api/apolloApi.js`.

Backend:
- inspect SSE event type `error`;
- inspect provider logs;
- confirm a session was created/scoped.

Workspace chat persists a partial response if tokens were received before the connection closed.

## Socratic phase/state mismatch

Inspect:
- `GET /api/notebooks/{notebook_id}/sessions/{session_id}/socratic-state`;
- `apollo_chat_sessions.socratic_state_json`;
- `backend/socratic_engine.py`.

Remember that session state and durable topic mastery are separate stores.

## Quick Check mastery looks wrong

Inspect the grade request's `current_score`, topic key and the result returned by `grade_quick_check`. Correct answers use +8 for Beginner/Developing and +6 for higher tiers; incorrect answers subtract 6.

## Studio fails

A source-grounded Studio call requires indexed source content.

- 400 → invalid/missing source context or transformation;
- 502/503 → provider/structured output failure;
- 504 → request timeout.

Video is storyboard-only in the production Phase 3 path.

## Planner appears blank

That is expected in the audited branch: Planner is a placeholder and is **Planned / Not Implemented**. Do not search for a missing endpoint; no production planner API/schema exists.

## Legacy code confusion

If root Streamlit code appears richer than the current UI, confirm the runtime entrypoint against `render.yaml` and `frontend/src/main.jsx`. Root `streamlit_app.py`, `tutor_engine.py` and `video_generator.py` are legacy/non-production.
