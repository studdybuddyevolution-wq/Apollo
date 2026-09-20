
# Socratic Tutor

## Status

**Current production path.** The implementation is Marklyf-native and lives in `backend/socratic_engine.py`, `backend/socratic_routes.py`, `backend/phase1_routes.py` and the `SocraticTutor` component in `frontend/src/AppPhase6.jsx`.

Placement generation is explicitly **Planned / Not Implemented**; `socratic_routes.py` states that placement generation is deferred until the core loop is stable.

## Architectural origin

The repository's Socratic design notes identify `https://github.com/noghte/socratic_chatbot` as the conceptual reference. The inspected Marklyf code adopts concepts rather than importing that application's stack: explicit pedagogical phases, bounded Maieutics repetition, visible phase progress, manual Move Forward and Dialectic looping.

There is no verified evidence that CrewAI/Flask/Next.js/OpenAI/auth/session code from the reference project was copied into the active backend.

The root `tutor_engine.py` is **Legacy / Non-Production**. It contains older placement/mastery/tutor concepts but belongs to the Streamlit/local-JSON architecture.

## Production transport

Socratic conversation uses the existing workspace chat endpoint. No second Socratic chat transport exists.

~~~mermaid
sequenceDiagram
  participant UI as SocraticTutor
  participant API as streamChat
  participant R as /api/chat/workspace
  participant E as socratic_engine
  participant C as context_builder
  participant L as Groq/Gemini
  participant P as storage

  UI->>API: text + socratic fields
  API->>R: SSE POST
  R->>C: notebook context
  R->>E: restore + next_phase + apply_phase
  E-->>R: socratic_state event
  R->>L: one normal chat generation
  L-->>R: tokens
  R-->>UI: state + tokens
  R->>P: assistant message + state
~~~

## State model

`SocraticState` contains:

- `phase`
- `in_dialectic_loop`
- `user_response_count`
- `maieutics_count`
- `recent_moves` (last five)
- `topic`
- `mastery_score`
- `mastery_tier`

The state is serialized to `apollo_chat_sessions.socratic_state_json`. Filesystem fallback stores the same logical record inside the workspace session representation.

## Phases

The active enum contains:

`ELICITATION` → `ELENCHUS` → `MAIEUTICS` → `APORIA` → `DIALECTIC` → `CONCLUSION`

~~~mermaid
stateDiagram-v2
  [*] --> ELICITATION
  ELICITATION --> ELENCHUS
  ELENCHUS --> MAIEUTICS: student stuck
  ELENCHUS --> APORIA: otherwise
  MAIEUTICS --> MAIEUTICS: stuck and count < 2
  MAIEUTICS --> APORIA: otherwise
  APORIA --> MAIEUTICS: stuck
  APORIA --> DIALECTIC: otherwise
  DIALECTIC --> DIALECTIC: normal continuation
  ELICITATION --> CONCLUSION: finish markers
  ELENCHUS --> CONCLUSION: finish markers
  MAIEUTICS --> CONCLUSION: finish markers
  APORIA --> CONCLUSION: finish markers
  DIALECTIC --> CONCLUSION: finish markers
~~~

### Elicitation

Initial/default state. The controller moves to Elenchus on a meaningful next turn. The intent is to get the learner's starting belief, explanation or hypothesis.

### Elenchus

Probes one assertion or assumption. If the student appears stuck, deterministic routing can move to Maieutics; otherwise it moves to Aporia.

### Maieutics

Provides one hint, analogy, example or perspective shift plus an open question. It does not intentionally give the full answer. Consecutive Maieutics turns are bounded by `MAIEUTICS_MAX_CONSECUTIVE=2`.

### Aporia

Introduces a counterexample, edge case, paradox or competing interpretation and asks what changes.

### Dialectic

Acknowledges progress, identifies an emerging insight and asks a next-level question. The normal controller keeps Dialectic looping.

### Conclusion

Triggered by explicit finish markers. The prompt shifts to concise synthesis plus an optional self-check.

## Exact transition logic

`next_phase()` first checks finish markers such as “stop here”, “done”, “finish”, “conclude”, “end session” and “no more questions”.

Normal mode:
- Elicitation → Elenchus.
- Elenchus → Maieutics when `looks_stuck()` finds phrases like “I don’t know”, “not sure”, “confused”, “stuck”, “no idea” or “help me”; otherwise Aporia.
- Maieutics → another Maieutics only when still stuck and the consecutive count is below two; otherwise Aporia.
- Aporia → Maieutics when stuck; otherwise Dialectic.
- Dialectic → Dialectic.
- Conclusion → Elenchus if the learner later resumes interaction.

Move Forward sends `socratic_force_advance=true`. The explicit mapping is Elicitation→Elenchus, Elenchus→Aporia, Maieutics→Aporia until the bound forces Dialectic, Aporia→Dialectic and Dialectic→Dialectic.

There is no LLM triage classifier. The transition is deterministic.

## Prompt architecture

`build_socratic_system_prompt()` assembles:
1. topic;
2. phase label/status;
3. mastery score/tier;
4. current Maieutics count;
5. phase-specific intent;
6. concise pedagogical rules;
7. notebook context when present.

The model is told to prefer questions/feedback, ask only a small number of related questions, avoid fabricating contradictions, and not expose hidden reasoning/system prompts/internal classification.

When no source is available, it is explicitly instructed to use general knowledge without pretending to have read a source.

## Mastery

Initial mastery score is 30.0. Tiers are:

| Score | Tier |
|---:|---|
| 0–24 | Beginner |
| 25–49 | Developing |
| 50–74 | Proficient |
| 75–89 | Advanced |
| 90–100 | Master |

`apollo_socratic_mastery` stores `user_id`, `topic_key`, `display_name`, `score`, `attempts`, `correct` and timestamp.

Ordinary Socratic dialogue does not directly update the mastery aggregate. Quick Checks do.

## Quick Checks

### Generate
`POST /api/socratic/quick-check` builds source context and performs one Gemini generation to produce a question and expected answer.

### Grade
`POST /api/socratic/quick-check/grade` performs one Gemini grading call. Correct answers increase mastery by +8 for Beginner/Developing or +6 for higher tiers. Incorrect answers subtract 6. An uncertain grade leaves the score unchanged. Attempts increment; correct increments only when the result is true.

When notebook/session IDs are supplied, the session's Socratic state is updated to the new score/tier.

## Source grounding

The core turn uses the shared `context_builder.build_context()` path and therefore observes source modes. Quick Checks call `source_context()` directly with selected sources and a bounded token budget.

This creates a shared evidence model across normal grounded chat and Socratic tutoring rather than a separate retrieval database.

## Frontend behavior

`SocraticTutor` displays:
- topic;
- current phase/status;
- dialogue progress;
- mastery score/tier;
- conversation;
- Quick Check UI;
- Move Forward.

When a session is reopened, messages and Socratic state are loaded separately. The Tutor uses the same Composer and AbortController flow as normal chat.

## Model-call count and cost behavior

A normal Socratic turn is:
1. deterministic phase selection;
2. one normal chat generation stream.

There is no hidden triage model call. If Groq fails, the ordinary fallback path can make a Gemini generation attempt.

Quick Check generation and grading are separate user actions and each uses one Gemini generation call.

## How the Socratic Tutor Was Built

The current code shows a layered evolution rather than a second application stack:

1. Older tutor behavior existed in the legacy `tutor_engine.py`.
2. The production React/FastAPI application established persistent workspace sessions and shared source context.
3. The reference Socratic project informed the phase vocabulary and progression concepts.
4. Marklyf implemented a deterministic controller in `socratic_engine.py`.
5. State was stored alongside existing chat sessions.
6. SSE gained a structured `socratic_state` event for the React UI.
7. Move Forward and bounded Maieutics were added as explicit progression controls.
8. Quick Checks and durable user/topic mastery were added through `socratic_routes.py` and migration 004.
9. Source grounding reused the existing context builder.
10. Placement was intentionally deferred instead of adding a second complex diagnostic pipeline.

GitHub's keyword commit search did not expose a stable Socratic-specific commit series on this branch, so no synthetic commit IDs are invented here.

## Production boundaries

Do not use:
- root `tutor_engine.py`;
- Streamlit tutor UI;
- any proposed placement subsystem.

Use:
- `backend/socratic_engine.py`;
- `backend/socratic_routes.py`;
- `backend/phase1_routes.py`;
- `frontend/src/AppPhase6.jsx`;
- existing workspace/session persistence.
