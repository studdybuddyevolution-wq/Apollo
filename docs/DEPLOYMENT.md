
# Deployment

## Production topology

~~~mermaid
flowchart LR
  U[Browser] --> CF[Cloudflare Worker + SPA assets]
  U --> R[Render FastAPI]
  R --> PG[(PostgreSQL)]
  R --> G[Groq]
  R --> GM[Gemini]
  R --> T[Tavily]
~~~

The repository's production composition is two application services:
- frontend: React/Vite static assets served through Cloudflare Worker;
- backend: FastAPI on Render.

## Frontend deployment

From `frontend/`:

~~~powershell
npm.cmd install
npm.cmd run build
npx.cmd wrangler deploy
~~~

`frontend/wrangler.jsonc` uses `frontend/src/worker.js` as the Worker and `dist` as the asset directory.

Set `VITE_API_BASE_URL` to the public Render API URL for production builds.

## Backend deployment

`render.yaml` configures:

- service: `apollo-api`;
- runtime: Python;
- plan: `free`;
- root directory: `backend`;
- build: `pip install -r requirements.txt`;
- start: `uvicorn phase2_app:app --host 0.0.0.0 --port $PORT`;
- health: `/api/health`;
- automatic deployment enabled.

## Database

Production requires `DATABASE_URL`. `backend/storage.py` switches to Postgres when configured and the deployment docs explicitly treat the filesystem fallback as development-only because Render's local filesystem is not durable.

Startup applies the SQL migrations in `backend/migrations` in lexical filename order.

The current branch contains migrations 001, 002, 003, 004 and 006; there is no migration 005 file in the audited tree.

## Required production variables

From `render.yaml`:
- `GROQ_API_KEY`
- `GEMINI_API_KEY`
- `TAVILY_API_KEY`
- `DATABASE_URL`
- `APOLLO_CORS_ORIGINS`

Important optional settings include model overrides, upload limits, rate limits, embedding parameters and timeout controls.

## CORS

FastAPI uses `APOLLO_CORS_ORIGINS`. The application default also knows the local Vite origin and the production Cloudflare Worker origin.

## Health verification

`GET /api/health` reports:
- provider configuration flags;
- primary/fallback model names;
- embedding model/dimensions;
- upload/request limits;
- storage backend;
- storage durability.

A production instance with `DATABASE_URL` should report database-backed durable storage rather than the filesystem fallback.

## Smoke verification

After a deployment, the codebase supports a practical smoke sequence:
1. health endpoint;
2. create/list notebook;
3. upload a small source;
4. list source status;
5. send a quick chat request;
6. open/reload a session;
7. exercise a Socratic Quick Check if its provider is configured.

These are operational verification steps derived from the available routes; no automated production smoke job is claimed.

## Recovery

For failed sources, use retry/refresh or delete/re-add. For provider incidents, allow the bounded Gemini fallback behavior and retry the user operation. For persistence failures, restore the production Postgres configuration before considering the service durable again.

## Legacy deployment

`streamlit_app.py` and the root Python UI modules are **Legacy / Non-Production**. They are not the command used by `render.yaml` and should not be treated as the current deployment target.
