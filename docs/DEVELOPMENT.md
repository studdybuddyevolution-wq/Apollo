
# Development Guide

## Prerequisites

Use Python, a virtual environment, Node/npm and—when durable persistence is desired—a PostgreSQL database. Provider API keys are only required for features that call the corresponding provider.

## Backend setup

~~~powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn phase2_app:app --reload --port 8000
~~~

The production composition command is `uvicorn phase2_app:app`. `backend/README.md` also documents `uvicorn main:app` for the simpler early FastAPI boundary; that command is not the full production route composition.

## Frontend setup

~~~powershell
cd frontend
npm.cmd install
npm.cmd run dev
~~~

Vite proxies `/api` to localhost:8000 when `VITE_API_BASE_URL` is unset.

## Build and tests

~~~powershell
cd backend
pytest

cd ..\frontend
npm.cmd run lint
npm.cmd run build
~~~

## Adding an endpoint

1. Put the request model/handler in the appropriate active backend module.
2. Register the module through `phase2_app.py` if it is new.
3. Maintain notebook/user ownership checks and current body/rate limits.
4. Add a backend test.
5. Add a frontend API helper rather than fetching ad hoc from UI components.

## Adding a frontend feature

Keep the active shell in `frontend/src/AppPhase6.jsx` and focused API calls in `frontend/src/api/*.js`. The application does not use React Router; navigation is state-driven.

## Adding AI behavior

Reuse the current provider boundaries:
- normal chat → `main._stream_model`;
- Gemini structured generation → `phase3_common.generate_gemini_text`;
- source transformations → `transformations.py`;
- research → `research_engine.py`.

Do not introduce an orchestration framework merely to classify one turn or generate one educational response.

## Adding a source type

Extend validation/ingestion and route the result through `rag_service.add_source()`. That keeps raw payload persistence, status, chunking, storage and source counts consistent. Add security and retry tests with the new parser.

## Modifying Socratic Tutor

The safe source of truth is `backend/socratic_engine.py`. Preserve:
- deterministic phase transition behavior;
- `socratic_state_json` serialization;
- `socratic_state` SSE event fields;
- Quick Check/mastery scoring semantics;
- shared notebook context;
- existing workspace chat transport.

Update `backend/tests/test_socratic_engine.py` and `test_socratic_workspace.py` with behavioral changes.

## Database changes

Add an additive SQL migration under `backend/migrations/NNN_*.sql`. Do not rewrite an already-applied migration for a deployed database. If the feature changes filesystem fallback behavior, add equivalent local persistence logic and tests.

## Debugging

Start with `/api/health`, server logs, request status and source/session state. For streaming issues, inspect the browser network stream and SSE event types before changing model code.
