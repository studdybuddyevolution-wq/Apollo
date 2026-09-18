# Apollo deployment

Apollo runs as two services:

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

`DATABASE_URL` is the durable storage path for notebooks, sources, raw source payloads, jobs, insights, chat sessions and notes. When it is not configured, Apollo falls back to local filesystem storage for development.

Apollo applies SQL files in `backend/migrations/` at backend startup. The source-lifecycle migration adds refreshable source URLs and durable source payloads used by retry/refresh.

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

Web URL ingestion validates every redirect and pins the HTTP connection to the validated public IP. Uploaded files are bounded by `APOLLO_MAX_UPLOAD_BYTES` before indexing. Long embedding work is tracked through Apollo jobs, and source failures expose retry controls in the Sources drawer.
