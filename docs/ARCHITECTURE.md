
# Architecture

## Current production topology

The active deployment is a two-service application. Cloudflare serves the built React/Vite SPA through `frontend/src/worker.js`; Render runs the FastAPI application from `backend/phase2_app.py`. PostgreSQL is selected whenever `DATABASE_URL` is present. The filesystem implementation remains a local-development fallback.

~~~mermaid
flowchart TB
  subgraph Browser
    UI[React AppPhase6]
    APIJS[frontend/src/api/*.js]
  end
  subgraph Backend
    EP[phase2_app.py]
    APP[main.py FastAPI app]
    WS[workspace/session routes]
    RAG[rag_service + context_builder]
    SOC[socratic_engine]
    RES[research_engine]
    STU[phase3_routes + transformations]
    ANA[analytics_service]
  end
  subgraph Providers
    GROQ[Groq streaming]
    GEM[Gemini generation/embeddings]
    TAV[Tavily search]
  end
  subgraph Persistence
    PG[(PostgreSQL)]
    FS[(Filesystem fallback)]
  end
  UI --> APIJS -->|HTTP/SSE| EP --> APP
  APP --> WS
  APP --> RAG
  APP --> SOC
  APP --> RES
  APP --> STU
  APP --> ANA
  APP --> GROQ
  APP --> GEM
  RES --> TAV
  WS --> PG
  RAG --> PG
  SOC --> PG
  ANA --> PG
  APP --> FS
~~~

## Request boundary

The backend keeps route registration in small modules rather than FastAPI routers. `phase2_app.py` registers modules against the same `main.app` object. `main.py` owns health, notebooks, basic chat, uploads, jobs, diagrams and provider streaming. `phase1_routes.py` adds workspace chat, sessions and notes; `phase2_routes.py` adds URL/YouTube source lifecycle; `phase3_routes.py` adds Studio; `socratic_routes.py` adds mastery and Quick Checks; `history_routes.py` adds cross-session history and analytics.

## Normal chat / workspace flow

~~~mermaid
sequenceDiagram
  participant UI as AppPhase6
  participant API as apolloApi.js
  participant WS as /api/chat/workspace
  participant CTX as context_builder
  participant LLM as Groq/Gemini
  participant DB as workspace_service/storage

  UI->>API: streamChat()
  API->>WS: POST JSON
  WS->>DB: create/find session
  WS->>DB: append user message
  WS->>CTX: build_context()
  CTX->>DB: retrieve chunks/insights
  WS->>LLM: _stream_model()
  LLM-->>WS: SSE tokens
  WS-->>API: SSE events
  API-->>UI: token/state/source updates
  WS->>DB: persist assistant text
~~~

## Streaming

The browser uses `fetch(..., {signal})`, reads the response body with a `ReadableStream` reader, parses `data:` SSE frames, and updates React state incrementally. Backend streaming is implemented with `StreamingResponse(..., media_type="text/event-stream")`.

The workspace generator accumulates emitted token text. It persists the assembled assistant response after successful completion and also in `GeneratorExit` / exception paths, which is why partial replies survive a cancelled connection.

## Persistence boundary

~~~mermaid
flowchart LR
  NB[Notebook] --> CH[Chunks]
  SRC[Source metadata] --> CH
  SRC --> PAY[Raw payload]
  SES[Chat session] --> MSG[Chat messages]
  SES --> SOC[Socratic state JSON]
  TOPIC[User + topic] --> MST[Mastery]
  SRC --> INS[Insights / Studio outputs]
  JOB[Job] --> EMB[Embedding progress]
~~~

Postgres is not mandatory at import time: `storage.py` chooses `PostgresStore` only when a usable `DATABASE_URL` connection is available. Otherwise the application falls back to local JSON/filesystem storage.

## Source pipeline

~~~mermaid
flowchart LR
  IN[File / URL / YouTube] --> V[Validation + size limits]
  V --> RAW[Raw source payload]
  RAW --> EXT[Text extraction]
  EXT --> CL[Cleaning]
  CL --> CK[Token-aware chunking]
  CK --> BM[BM25 index in application memory/query path]
  CK --> EM[Gemini embedding job]
  EM --> PV[(pgvector, optional)]
  BM --> RET[Hybrid retrieval]
  PV --> RET
  RET --> CTX[Context builder]
  CTX --> LLM[Chat / Socratic / Research / Studio]
~~~

## Failure and retry boundaries

Gemini text generation is bounded by a primary attempt, one retry for transient failures on the first model, then configured fallback models. Embedding generation retries up to three times per batch. Source errors are classified for retryability. There is no external task queue; embedding jobs use `asyncio.create_task` in the current worker.

## Legacy boundary

The root Streamlit application and older Python UI helpers remain useful as historical evidence but should not be treated as components of the Cloudflare + Render runtime. The current React app is the production UI.
