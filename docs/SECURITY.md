
# Security

## Controls verified in the active code

| Threat | Protection | Implementation | Relevant path |
|---|---|---|---|
| SSRF to private/local services | public-IP validation | `_validate_public_url` | `backend/source_ingestion.py` |
| DNS rebinding / redirect race | revalidate each redirect + IP pinning | `_PinnedIPAdapter` | `backend/source_ingestion.py` |
| Oversized HTTP body | raw ASGI middleware | `RequestBodyLimitMiddleware` | `backend/request_limits.py` |
| Oversized file upload | bounded body read | `MAX_UPLOAD_BYTES` | `backend/main.py` |
| Path traversal / control bytes | basename + control-byte filtering | `sanitize_source_filename` | `backend/rag_service.py` |
| Concurrent filename collisions | DB uniqueness or filesystem claim | `reserve_source_name` | `storage.py` / `rag_service.py` |
| Filesystem partial-write corruption | temp + fsync + atomic replace | `_save_source_payload_fs` | `backend/rag_service.py` |
| Retry storms | bounded retry classification | `phase3_common.py` / `embeddings.py` | backend |
| SQL injection | parameterized SQL | psycopg parameters | `backend/storage.py` |
| Credential exposure | env-based provider keys | `.env` ignored by Git | deployment |
| Request abuse | in-memory sliding-window limit | `_check_rate_limit` | `backend/main.py` |
| Stream cancellation loss | AbortController + GeneratorExit persistence | chat path | frontend/backend |

## SSRF and DNS rebinding

URL ingestion accepts only HTTP(S), resolves the hostname, rejects private/loopback/link-local/multicast/reserved addresses, then pins connections to the validated public IP. Environment proxies are disabled so a proxy cannot silently perform the DNS resolution elsewhere. Every redirect repeats validation.

This is stronger than a single initial host check because the redirected destination is revalidated before it is requested.

## Upload/request limits

The raw body middleware runs before FastAPI multipart parsing. The default per-file cap is 25 MiB. The body envelope allows a bounded additional 512 KiB for multipart overhead.

Malformed or non-positive configured limits are handled by the implementation's safe default rather than producing an unbounded parser.

Web URL ingestion has a separate 8 MiB download ceiling.

## Filename and atomic-write protection

Source names are reduced to a safe basename and reject control characters. Filesystem source names are claimed under a lock/claim file when needed. Production Postgres uses a unique notebook/source-name constraint plus an atomic reservation loop.

Raw filesystem payloads are written to a temporary file, flushed and fsynced, then atomically replaced.

## Retry classification

`backend/error_classifier.py` identifies transient provider/source failures. Embedding jobs retry retryable failures with bounded exponential backoff. Gemini generation uses one transient retry on the first model and bounded fallback models.

The code does not expose a generic infinite retry wrapper.

## Authentication boundary

The production routes do not implement JWT/OAuth or a server-verifiable user session. The browser creates `apollo-user-id` and the backend uses `user_id` in queries.

Therefore:

**Implemented:** per-user data scoping based on a client-supplied key.

**Not implemented:** cryptographic user authentication/authorization.

This distinction is important for any future security work.

## SQL and provider credentials

The inspected SQL uses parameter placeholders rather than interpolating ordinary user input. Provider keys are read from environment variables and are not embedded in frontend source.

## Streaming

The frontend abort path uses AbortController. The backend catches generator cancellation/disconnect and persists any already-generated assistant text. Provider exceptions are transformed into user-safe error messages rather than raw SDK payloads.

## Security gaps deliberately not claimed

The repository does not provide verified evidence of a JWT identity service, role/permission system, external WAF policy, dedicated audit log, or separate network isolation layer. None is documented as present.
