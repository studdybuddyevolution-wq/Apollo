
# Chat and Sessions

## Session scope

Workspace chat is identified by:

- `user_id`
- `notebook_id`
- `session_id`

Sessions live in `apollo_chat_sessions`. Messages live in `apollo_chat_messages`. Socratic state is stored on the session as `socratic_state_json`.

## Request lifecycle

~~~mermaid
sequenceDiagram
  participant UI as AppPhase6
  participant API as apolloApi.js
  participant W as /api/chat/workspace
  participant S as workspace_service
  participant C as context_builder
  participant L as model stream
  participant DB as storage

  UI->>API: POST + AbortController.signal
  API->>W: workspace chat
  W->>S: create/find session
  W->>S: append user message
  W->>C: build_context
  W->>L: _stream_model
  L-->>W: SSE tokens/events
  W-->>API: SSE
  API-->>UI: incremental state
  W->>DB: persist assistant response
  W->>DB: save Socratic state if active
~~~

## Session creation

When no session ID is supplied, `phase1_routes.workspace_chat` creates a session and emits a `session` SSE event. The frontend updates its session state and reloads the current session list.

If a session ID is supplied, the backend verifies it belongs to the notebook/user scope before streaming.

## Message persistence

The backend stores the user message before generation begins. During generation it accumulates token text in memory. On normal completion it stores the full assistant message with model name and source metadata.

## Cancellation and interrupted streams

The frontend uses `AbortController`. The backend generator handles three important outcomes:

- normal completion → persist assembled reply;
- `GeneratorExit` from client disconnect/cancel → persist the assembled prefix;
- ordinary exception after token emission → persist the prefix and emit an SSE error.

This is not token-by-token durable streaming. There is one database message record for the generated prefix after the connection closes.

Git history contains explicit cancellation-hardening commits, and `backend/tests/test_chat_cancellation.py` exercises partial workspace reply persistence.

## Reload and continuation

`AppPhase6.jsx` uses `getSessionMessages()` when selecting/reopening a session. The Socratic page also calls `getSocraticState()` so phase/score are restored separately from the message list.

`PastSessionsPage.jsx` uses cursor-based history APIs for large session collections and message previews.

## Source and research context

The frontend sends active sources and a source-mode map with each workspace request. `context_builder.build_context()` converts these into actual evidence and provenance. Research mode controls whether the backend chooses direct chat, Tavily web synthesis, or Deep/Study hybrid research.

## Notes

Messages can be saved as notes through the notebook notes API. Notes are a separate persisted entity and are not an implicit copy of every chat message.

## Important limitation

There is no resumable external stream/job model for chat. A browser refresh during generation does not reattach to a live provider stream; it sees whatever message prefix had already been stored when the backend detected disconnect/error.
