
# AI and Model Architecture

## Provider split

The active backend uses two model providers plus Tavily search:

- **Groq** — normal streaming chat. `APOLLO_PRIMARY_MODEL` defaults to `openai/gpt-oss-120b`.
- **Gemini** — fallback chat, web/deep/study synthesis, Studio, Socratic Quick Checks and embeddings.
- **Tavily** — web evidence retrieval for web/deep/study research.

Provider resilience is intentionally centralized in `backend/phase3_common.py` for Gemini.

## Model configuration

| Variable | Role | Default |
|---|---|---|
| `APOLLO_PRIMARY_MODEL` | normal Groq chat | `openai/gpt-oss-120b` |
| `APOLLO_GEMINI_FALLBACK_MODEL` | first chat fallback | `gemini-3.8-flash` |
| `APOLLO_GEMINI_FALLBACK_MODELS` | Gemini fallback chain | configurable list |
| `APOLLO_WEB_SYNTHESIS_MODEL` | web/deep/Studio base Gemini model | `gemini-3.8-flash` |
| `APOLLO_STUDIO_MODEL` | preferred Studio override | web synthesis model |
| `APOLLO_TRANSFORM_MODEL` | transformation model | web synthesis model |
| `APOLLO_SLIDE_MODEL` | direct slide endpoint | web synthesis model |
| `APOLLO_EMBEDDING_MODEL` | embedding model | `gemini-embedding-2` |
| `APOLLO_EMBEDDING_DIMENSIONS` | embedding size | 768 |
| `APOLLO_EMBEDDING_BATCH_SIZE` | embedding batch | 50 |
| `APOLLO_EMBEDDING_MAX_RETRIES` | embedding retries | 3 |

## Normal chat

`main._stream_model()` selects one of three paths:

1. Deep/Study → hybrid research + Gemini synthesis.
2. Web (when enabled) → Tavily + Gemini.
3. Normal/Socratic → Groq stream using `request.model` or the configured primary model.

If the Groq stream raises and a Gemini key is configured, the backend emits a `fallback` event and starts the configured Gemini fallback model.

Groq streaming uses the provider SDK's streaming API and limits output using the main output-token budget. The Groq setup also requests hidden reasoning formats where supported; private chain-of-thought is not returned to the client.

## Gemini fallback

`generate_gemini_text()` gives the first model at most one exponential-backoff retry when the error is transient, then tries later configured models once. This bounds both failure latency and model-call multiplication.

Transient markers include 429/503/unavailable/high-demand/resource-exhausted/internal/deadline style failures.

## Embeddings

`backend/embeddings.py` calls Gemini embeddings in batches of 50 and requests 768-dimensional vectors by default. Per-batch generation retries up to three times with exponential waits.

When pgvector is unavailable, the application continues with lexical BM25 retrieval. Vector retrieval is therefore an enhancement rather than a hard dependency.

## Feature-level model calls

### Socratic
A normal Socratic turn makes one ordinary chat generation after deterministic phase selection. There is no extra LLM triage call. A Groq failure can trigger the normal Gemini fallback.

Quick Check generation is a separate one-call action. Quick Check grading is another one-call action. Those calls are explicit follow-up interactions, not hidden sub-agents.

### Web research
One Tavily search request produces the evidence set, then a Gemini streaming synthesis consumes the returned source blocks.

### Deep/Study
The research engine runs bounded parallel retrieval passes (not one model per pass). It then performs a Gemini synthesis stream. This is intentionally more expensive than normal chat because the product is explicitly doing retrieval/decomposition work.

### Studio
Most Studio generation uses Gemini through `phase3_common.generate_gemini_text`. Some source-grounding validators can cause one stricter regeneration attempt (report and mind-map paths).

## Prompt boundaries

The application assembles prompts from system/feature intent, user conversation, selected notebook context, and provider-specific output contracts. Socratic prompts add phase, mastery tier, topic and bounded pedagogical behavior.

The implementation deliberately does not expose private reasoning, hidden system prompts or internal phase classification to the browser.

## Zero-cost architecture constraint

The repository avoids introducing paid fixed infrastructure: Render is configured on its free plan, embedding storage is optional pgvector in the existing Postgres, and jobs are in-process. Provider API usage still depends on external provider quotas and credentials; the repo does not guarantee unlimited free model calls.

## Failure and fallback behavior

Provider failures are converted into safe user-facing messages. Web research explicitly errors when `TAVILY_API_KEY` is missing. Studio and Quick Check APIs return provider-specific 5xx statuses rather than leaking raw provider SDK objects.
