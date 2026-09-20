
# Database and Persistence

## Storage selection

`backend/storage.py` defines `PostgresStore`. It creates the base notebook/chunk tables, detects pgvector, and runs sorted SQL migrations at startup. A configured `DATABASE_URL` is the durable production path. Without it, local JSON/filesystem storage is used.

**Production:** PostgreSQL is required by the deployment documentation because Render's filesystem is not durable.

## Schema

| Entity | Key fields | Relationships |
|---|---|---|
| `apollo_notebooks` | id, user_id, title, created, updated, source_count, node_count | parent of chunks, sources, sessions, notes |
| `apollo_chunks` | id, notebook_id, source, kind, text, chunk_index, content_type, optional embedding | FK notebook |
| `apollo_sources` | id, notebook_id, name, kind, processing_status, error_message, source_url | FK notebook |
| `apollo_source_payloads` | notebook_id, source_name, payload, updated | FK notebook; raw bytes |
| `apollo_source_insights` | id, notebook_id, source_name, insight_type, content, model_used, status | notebook/source scope |
| `apollo_jobs` | id, type, status, progress, notebook_id, user_id, timestamps, error, result_ref | operational metadata |
| `apollo_chat_sessions` | id, notebook_id, user_id, title, created, updated, socratic_state_json | FK notebook |
| `apollo_chat_messages` | id, session_id, role, content, model, sources_json, created | FK session |
| `apollo_notes` | id, notebook_id, user_id, title, content, source_type/ref, timestamps | FK notebook |
| `apollo_socratic_mastery` | user_id + topic_key, score, attempts, correct, updated | user/topic aggregate |

~~~mermaid
erDiagram
  apollo_notebooks ||--o{ apollo_chunks : contains
  apollo_notebooks ||--o{ apollo_sources : owns
  apollo_notebooks ||--o{ apollo_source_payloads : stores
  apollo_notebooks ||--o{ apollo_source_insights : produces
  apollo_notebooks ||--o{ apollo_chat_sessions : scopes
  apollo_chat_sessions ||--o{ apollo_chat_messages : contains
  apollo_notebooks ||--o{ apollo_notes : contains
  apollo_chat_sessions {
    text id PK
    text notebook_id FK
    text user_id
    text title
    text socratic_state_json
  }
  apollo_socratic_mastery {
    text user_id PK
    text topic_key PK
    double score
    int attempts
    int correct
  }
~~~

## Indexing and constraints

The source lifecycle uses a unique constraint on `(notebook_id, name)`. History adds cursor-friendly indexes on `(user_id, updated DESC, id DESC)` and `(session_id, created DESC, id DESC)`. Chunks have a pgvector IVFFlat cosine index only when the `vector` extension is available.

## Migrations

- `001_add_chunking_fields.sql`: chunk fields, optional pgvector, sources, insights, jobs.
- `002_knowledge_workspace.sql`: sessions, messages, notes.
- `003_source_lifecycle.sql`: durable source URL and raw payload.
- `004_socratic_mastery.sql`: Socratic session JSON plus mastery.
- `005_persistence_hardening.sql`: production durability/hardening additions; retain as part of startup migration order.
- `006_history_analytics_indexes.sql`: history cursor indexes.

`storage.py` applies each `*.sql` file in lexical order and logs migration failures as warnings.

## Filesystem fallback

The filesystem path uses `APOLLO_DATA_DIR` and includes notebooks/chunks/source metadata/raw payloads, workspace session records and a separate `socratic_mastery.json`. This is intended for local development and is **not durable production storage** on Render.

## Raw payloads and cleanup

Source deletion removes chunks, source metadata and source payload. Notebook deletion removes the database-owned source/session/note data through the service-layer cleanup paths; filesystem deletion removes its notebook directory.

## Persistence caveat

The Socratic conversation state is stored alongside the session in `socratic_state_json`; the mastery aggregate is a separate user/topic table. Conversation text is not duplicated into the mastery table.
