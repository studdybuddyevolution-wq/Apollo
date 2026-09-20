# Socratic Tutor — Design Note

This file is a compact design note. The canonical implementation record is [SOCRATIC_TUTOR.md](./SOCRATIC_TUTOR.md).

## Current implementation

- Active engine: \`backend/socratic_engine.py\`
- Conversation transport: \`POST /api/chat/workspace\`
- Session state: \`apollo_chat_sessions.socratic_state_json\`
- Mastery aggregate: \`apollo_socratic_mastery\`
- Frontend: \`SocraticTutor\` in \`frontend/src/AppPhase6.jsx\`
- Phase transitions are deterministic; there is no separate LLM triage classifier.
- Consecutive Maieutics turns are bounded by \`MAIEUTICS_MAX_CONSECUTIVE = 2\`.
- Quick Checks are explicit follow-up API interactions and update durable mastery.
- Placement generation remains **Planned / Not Implemented**.

## Reference

The implementation notes identify \`https://github.com/noghte/socratic_chatbot\` as the conceptual reference for phase/progression ideas. The active Marklyf code does not import that application's CrewAI/Flask/Next.js/auth/session stack.

## Legacy implementation

Root \`tutor_engine.py\` belongs to the older Streamlit/local-JSON architecture. It contains historical tutor, placement and mastery concepts but is not the production Socratic engine.

## State transition summary

~~~text
ELICITATION -> ELENCHUS
ELENCHUS -> MAIEUTICS (stuck) | APORIA
MAIEUTICS -> MAIEUTICS (stuck, count < 2) | APORIA
APORIA -> MAIEUTICS (stuck) | DIALECTIC
DIALECTIC -> DIALECTIC
finish markers -> CONCLUSION
~~~

See [SOCRATIC_TUTOR.md](./SOCRATIC_TUTOR.md) for prompt architecture, mastery scoring, source grounding, frontend behavior, model-call counts and implementation history.
