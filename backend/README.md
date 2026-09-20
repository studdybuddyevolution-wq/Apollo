# Marklyf FastAPI backend

Phase 3 introduces a small FastAPI boundary in front of the existing Marklyf Python stack.

## Run locally on Windows

From the `backend` directory:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:GROQ_API_KEY="gsk_..."
uvicorn main:app --reload --port 8000
```

Keep that terminal running.

Then, in a second terminal, run the React app:

```powershell
cd ..\frontend
npm.cmd install
npm.cmd run dev
```

The Vite development server proxies `/api/*` to `http://127.0.0.1:8000`, so the React app can call the backend without hard-coding a development port.

## Endpoints

- `GET /api/health` — backend health/configuration check.
- `POST /api/chat` — Server-Sent Events stream for chat responses.

The chat endpoint currently uses the Groq API with `qwen/qwen3.6-27b`. RAG, memory, notebooks, voice, vision, citations, and the rest of Marklyf's existing Python services are deliberately not migrated in this phase yet.
