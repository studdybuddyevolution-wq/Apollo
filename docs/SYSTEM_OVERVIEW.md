
# System Overview

## What Marklyf is

Marklyf is a notebook-centered AI study application. A student can create a notebook, attach sources, select source context modes, chat with an AI over the notebook, run web/deep research, create source-grounded Studio artifacts, use a stateful Socratic Tutor, and view learning telemetry.

## Major capabilities actually present

### Workspace and knowledge
Notebooks, sources, notes, persisted chat sessions, source-level insights and searchable history are implemented in the current React/FastAPI path.

### Sources and RAG
The active source stack supports uploaded files, public URL ingestion, and YouTube transcripts. PDF and DOCX extraction are explicit in `rag_service.py`; other file payloads are decoded as UTF-8. Retrieval is strict to the selected notebook and optionally to selected source names.

### Research
Quick, web, deep and study research modes exist in the main chat UI. Deep/Study research uses `research_engine.run_hybrid_research`, combining notebook retrieval and Tavily, then Gemini synthesis with a grounding-overlap check.

### Socratic Tutor
Socratic mode uses the existing workspace chat stream rather than a separate chat transport. The pedagogical state is persisted in `apollo_chat_sessions.socratic_state_json`, while topic mastery is persisted separately.

### Studio
The active Studio supports slides, reports, podcasts, transformations and video storyboards, plus a mind-map endpoint. PPTX export exists for slides in the older direct route in `main.py`; the current Studio drawer's `slides` path is the Phase 3 generation output. Video is storyboard generation, not video rendering.

### Progress
The progress dashboard derives streaks, message activity, session counts and Socratic mastery from persisted data.

### Planner
**Planned / Not Implemented.** `AppPhase6.jsx` contains a Study Planner navigation item, but the current branch renders the generic migration placeholder and no planner API/schema was found.

## End-to-end flows

### 1. Normal chat
`AppPhase6 → frontend/src/api/apolloApi.js → POST /api/chat or /api/chat/workspace → main._stream_chat/_stream_model → Groq, or Gemini fallback → SSE → React state → session persistence`

### 2. Grounded notebook question
`AppPhase6 → /api/chat/workspace → context_builder.build_context
→ rag_service.retrieve_hybrid → BM25 + optional vector
→ source/insight context → provider stream → SSE → stored assistant message`

### 3. Socratic session
`SocraticTutor → streamChat(researchMode=socratic)
→ /api/chat/workspace
→ next_phase()/apply_phase()
→ socratic_state SSE event
→ _system_message() / build_socratic_system_prompt()
→ one provider stream
→ partial/full persistence
→ save_socratic_state()`

### 4. Research
Quick answers stay on the normal provider path. Web mode calls Tavily directly and streams Gemini synthesis. Deep/Study mode decomposes the question into adaptive sections, runs parallel notebook/Tavily retrieval passes, deduplicates evidence, synthesizes with Gemini and emits a post-stream grounding check.

### 5. Studio artifact
`StudioPanel → studioApi.js → /studio/generate or /studio/slides
→ context_builder → Gemini generation → validation/grounding checks
→ apollo_source_insights / response payload`

### 6. Reloading a session
The frontend loads session metadata and persisted messages through `listSessions` / `getSessionMessages`, and the Socratic page separately requests `getSocraticState`. The backend reads from Postgres or the filesystem representation.

### 7. Uploading a source
`SourcePanel / sourceIngestionApi
→ upload or URL/YouTube endpoint
→ request/file limit checks
→ filename/URL security validation
→ raw payload persistence
→ text extraction → chunking → source record
→ optional async embedding job
→ status indexed/failed`

## Important implementation distinction

The repository contains more features than the active UI exposes. In particular, legacy Streamlit code has broader historical Studio/tutor behavior, but the canonical production behavior is the React/FastAPI path documented here.
