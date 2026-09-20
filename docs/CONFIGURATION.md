
# Configuration

The following variables are observed in the active backend/frontend code and deployment configuration. No real secret values are recorded here.

| Name | Purpose | Required | Default | Production | Used by |
|---|---|---:|---|---|---|
| `DATABASE_URL` | durable PostgreSQL | Yes for production | unset | Secret/config | storage |
| `GROQ_API_KEY` | normal chat provider | Chat path | unset | Secret | main |
| `GEMINI_API_KEY` | fallback/research/Studio/embedding | Provider-dependent | unset | Secret | main/phase3_common/embeddings |
| `TAVILY_API_KEY` | web/deep/study retrieval | Research | unset | Secret | main/research_engine |
| `APOLLO_CORS_ORIGINS` | browser origins | Yes in Render config | localhost | Config | main |
| `APOLLO_PRIMARY_MODEL` | normal Groq model | No | `openai/gpt-oss-120b` | Config | main |
| `APOLLO_GEMINI_FALLBACK_MODEL` | first chat fallback | No | `gemini-3.8-flash` | Config | main |
| `APOLLO_GEMINI_FALLBACK_MODELS` | fallback chain | No | built-in list | Config | main/phase3_common |
| `APOLLO_WEB_SYNTHESIS_MODEL` | web/deep/Studio synthesis | No | `gemini-3.8-flash` | Config | main/phase3_common |
| `APOLLO_STUDIO_MODEL` | Studio preferred model | No | web synthesis | Config | phase3_routes |
| `APOLLO_TRANSFORM_MODEL` | transformations | No | web synthesis | Config | transformations |
| `APOLLO_SLIDE_MODEL` | direct slides | No | web synthesis | Config | main |
| `APOLLO_EMBEDDING_MODEL` | embedding model | No | `gemini-embedding-2` | Config | embeddings |
| `APOLLO_EMBEDDING_DIMENSIONS` | vector dimension | No | 768 | Config | embeddings/storage |
| `APOLLO_EMBEDDING_BATCH_SIZE` | embedding batch | No | 50 | Config | embeddings |
| `APOLLO_EMBEDDING_MAX_RETRIES` | embedding retries | No | 3 | Config | embeddings |
| `APOLLO_MAX_UPLOAD_BYTES` | per-file upload limit | No | 25 MiB | Config | main/request_limits |
| `APOLLO_RATE_LIMIT_MAX` | rate limit count | No | 20 | Config | main |
| `APOLLO_RATE_LIMIT_WINDOW_SECONDS` | rate-limit window | No | 600 | Config | main |
| `APOLLO_GROUNDING_MIN_OVERLAP` | Deep/Study grounding threshold | No | 0.4 | Config | main |
| `APOLLO_DATA_DIR` | filesystem fallback root | No | backend/data | Dev/local | rag/workspace/Socratic |
| `VITE_API_BASE_URL` | frontend API origin | No | current Render URL in helper | Public build config | frontend API |
| `APOLLO_SOCRATIC_GEMINI_TIMEOUT_MS` | Quick Check Gemini timeout | No | 12000 | Config | socratic_engine |
| `APOLLO_STUDIO_REQUEST_TIMEOUT` | Studio request timeout | No | 55 s | Config | phase3_routes |

Additional timeout/model environment variables exist for specific paths; inspect the owning module before adding new configuration.

## Secrets

Provider API keys and Postgres URLs are server-side environment variables. `.env` is ignored by Git. Do not put secrets into Vite-exposed variables or documentation.
