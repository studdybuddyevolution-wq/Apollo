# Marklyf deployment

Marklyf runs as two services:

- `frontend/` — React + Vite + Cloudflare Worker/static assets.
- `backend/` — FastAPI on Render.

The backend uses PostgreSQL when `DATABASE_URL` is configured. The filesystem store remains a local-development fallback.

## Frontend — Cloudflare Workers

From the repository root:

```cmd
cd frontend
npm.cmd install
npm.cmd run build
npx.cmd wrangler deploy
```

Wrangler reads `frontend/wrangler.jsonc`. The worker serves the Vite build from `dist` and uses SPA fallback handling.

For local development:

```cmd
cd frontend
npm.cmd run dev
```

Set the build-time API origin when the backend is not reached through the local Vite proxy:

```text
VITE_API_BASE_URL=https://YOUR-RENDER-SERVICE.onrender.com
```

Never put API secrets in `VITE_*` variables; they are exposed to browser code.

## Backend — Render

Use the repository `render.yaml` Blueprint, or configure the service with:

- Root Directory: `backend`
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn phase2_app:app --host 0.0.0.0 --port $PORT`
- Health Check Path: `/api/health`

Required environment variables:

```text
GROQ_API_KEY=...
GEMINI_API_KEY=...
TAVILY_API_KEY=...
DATABASE_URL=...
APOLLO_CORS_ORIGINS=https://YOUR-APOLLO-WORKER.workers.dev
```

Optional hardening/configuration:

```text
APOLLO_MAX_UPLOAD_BYTES=26214400
APOLLO_GEMINI_FALLBACK_MODELS=...
APOLLO_TRANSFORM_MODEL=...
APOLLO_WEB_SYNTHESIS_MODEL=...
```

`DATABASE_URL` is the durable storage path for notebooks, sources, raw source payloads, jobs, insights, chat sessions and notes. When it is not configured, Marklyf falls back to local filesystem storage for development.

Marklyf applies SQL files in `backend/migrations/` at backend startup. The source-lifecycle migration adds refreshable source URLs and durable source payloads used by retry/refresh.

## CORS

Set `APOLLO_CORS_ORIGINS` to the exact production worker origin, then redeploy/restart the Render service.

Local development commonly uses:

```text
APOLLO_CORS_ORIGINS=http://localhost:5173
```

## Health check

After deployment:

```text
https://YOUR-RENDER-SERVICE.onrender.com/api/health
```

The health response includes provider configuration flags and the configured upload limit.

## Local backend

```cmd
cd backend
uvicorn phase2_app:app --reload --port 8000
```

Then open the frontend at `http://localhost:5173`.

## Operational notes

Web URL ingestion validates every redirect and pins the HTTP connection to the validated public IP. Uploaded files are bounded by `APOLLO_MAX_UPLOAD_BYTES` before indexing. Long embedding work is tracked through Marklyf jobs, and source failures expose retry controls in the Sources drawer.

## Phase 8 production hardening

Marklyf enforces uploads at two layers. `APOLLO_MAX_UPLOAD_BYTES` is the per-file limit (25 MiB by default), and the raw ASGI request-body middleware rejects an oversized HTTP body before FastAPI multipart parsing. Malformed or non-positive upload-limit configuration falls back to the safe default. The request-body limit allows a bounded 512 KiB multipart envelope above the file limit.

Uploaded source names are sanitized and collision-safe. Concurrent uploads of the same filename receive distinct source names instead of overwriting one another. Filesystem-fallback payload writes use a temporary file plus atomic replacement and clean up temporary files after failures. Production Postgres reservations are atomic at the notebook/source-name uniqueness boundary.

Source lifecycle and embedding failures distinguish permanent validation failures from transient provider/network failures. Transient embedding failures receive bounded in-process retries with exponential backoff; permanent validation failures fail immediately. Manual URL/YouTube refresh and source retry endpoints return retry-oriented status information for transient failures.

The backend health response exposes both `max_upload_bytes` and `max_request_body_bytes`, along with the existing `storage_backend` and `durable_storage` fields. Production should report `storage_backend=postgres` and `durable_storage=true` when `DATABASE_URL` is configured correctly.


## Production entrypoints and legacy code

The active production entrypoints are:

- Frontend: `frontend/src/main.jsx` → `AppPhase6.jsx`
- Backend: `backend/phase2_app.py` → FastAPI application

The root-level Streamlit files and older Python UI modules are legacy code kept for historical/reference purposes. They are not part of the current Cloudflare + Render production path and should not be used as deployment entrypoints.

## Persistence requirement

For production, `DATABASE_URL` is required. With PostgreSQL configured, Marklyf stores notebooks, chunks, source lifecycle metadata, raw source payloads, chat sessions/messages, notes, insights and jobs in the database. The filesystem store is a development fallback and is not a durable production store on an ephemeral Render filesystem.

The backend health endpoint reports:

- `storage_backend=postgres` when PostgreSQL is active
- `durable_storage=true` when the database-backed store is active

Check this after deployment before relying on persisted workspace data.
