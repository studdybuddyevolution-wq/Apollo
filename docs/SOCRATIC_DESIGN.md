# Apollo Socratic Study — implementation note

## Current Apollo integration points

- The active frontend is `frontend/src/AppPhase6.jsx`; it already exposes a `Socratic Tutor` navigation entry but currently renders migrated-module placeholder content.
- Chat streaming is centralized in `frontend/src/api/apolloApi.js` and routes to `/api/chat/workspace` whenever a notebook is selected.
- Workspace chat is persisted by `backend/phase1_routes.py` and `backend/workspace_service.py` into the existing `apollo_chat_sessions` / `apollo_chat_messages` PostgreSQL tables, with a filesystem fallback for local development.
- Notebook context comes from `backend/context_builder.py`, which already supports the `full`, `summary`, `insights`, and `off` source modes.
- Models/fallbacks are already centralized in Apollo's existing Groq/Gemini path. Socratic mode will use the same selected model and fallback behavior.
- The legacy `tutor_engine.py` contains placement, mastery tiers, quick checks, and source-aware tutoring concepts, but stores state in Streamlit/local JSON and therefore is being reimplemented rather than moved.
- `settings_app.py` has a legacy Socratic learning-style preference, but no active React settings/profile model exists that should become a new Socratic dependency.

## Reference concepts adopted

From `noghte/socratic_chatbot`:

- explicit dialogue phases: Elenchus, Maieutics, Aporia, Dialectic
- a deterministic/manual phase-progression idea plus a Triage-like decision layer
- bounded Maieutics repetition
- a visible phase-progress UI
- a user-controlled Move Forward action
- continued Dialectic looping instead of one-shot answer generation

The reference project's CrewAI/Flask/Next.js/OpenAI/auth/session architecture is not being imported.

## Apollo-native design

- `backend/socratic_service.py` owns mastery, source-aware quiz helpers, phase prompts, and the deterministic phase controller.
- Existing `/api/chat/workspace` remains the Socratic transport. `research_mode="socratic"` selects Socratic prompting without creating a second chat stack.
- Socratic session state is stored alongside the existing chat session in `apollo_chat_sessions.socratic_state_json`; the filesystem fallback stores the same state in the existing workspace session record.
- One model generation is used per normal Socratic turn. The controller selects the pedagogical move before that call; the existing Groq-to-Gemini fallback remains the only normal second attempt.
- A structured `socratic_state` SSE event drives the React phase/progress UI.
- Quick Checks use a separate explicit quiz/grade interaction after the core chat loop and update the same session mastery state.
- Placement generation is intentionally deferred until the core dialogue, Move Forward, Quick Check, and mastery persistence are stable.

## State model

The persisted minimum is:

- current phase
- dialectic-loop flag
- user response count
- consecutive Maieutics count
- recent pedagogical phases
- topic
- mastery score and tier

Conversation text remains in Apollo's existing chat message store and is not duplicated.

## Phase routing

Initial meaningful turn -> Elenchus.

Normal routing then uses bounded deterministic rules:
- Elenchus -> Maieutics when the student appears stuck; otherwise Aporia.
- Maieutics -> another Maieutics only while the student remains stuck and the consecutive bound is below two; otherwise Aporia.
- Aporia -> Maieutics when the student is stuck; otherwise Dialectic.
- Dialectic stays in the Dialectic loop unless the student explicitly asks to finish.
- Explicit completion requests produce a concise conclusion state.
- Move Forward bypasses uncertainty and advances only through valid transitions.

This keeps the main turn at one Apollo model generation and avoids a separate triage LLM call.