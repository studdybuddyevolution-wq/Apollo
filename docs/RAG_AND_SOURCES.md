
# RAG and Sources

## Source lifecycle

~~~mermaid
flowchart TD
  A[File upload / URL / YouTube] --> B[Request + source validation]
  B --> C[Safe unique source name]
  C --> D[Raw payload persistence]
  D --> E[Text extraction]
  E --> F[Cleaning + content type detection]
  F --> G[400-token chunks\n60-token overlap default]
  G --> H[Chunk persistence]
  H --> I[Embedding job when pgvector exists]
  G --> J[BM25 retrieval]
  I --> K[Vector retrieval]
  J --> L[RRF fusion]
  K --> L
  L --> M[Context builder]
  M --> N[Chat / Research / Socratic / Studio]
~~~

## Supported sources

The current production backend supports:

- uploaded files;
- public HTTP(S) web URLs;
- YouTube transcript URLs.

PDF and DOCX extraction are explicit in `rag_service.py`. Other uploaded payloads use UTF-8 decoding with replacement. URL PDF downloads are kept as PDF payloads; HTML pages are converted to text and stored as a text source.

YouTube ingestion uses `youtube-transcript-api` and fails clearly if the dependency is unavailable or a transcript cannot be fetched.

## Chunking

`backend/chunking.py`:
- normalizes whitespace/newlines;
- recognizes Markdown, HTML and plain content;
- preserves structured boundaries;
- prefers `tiktoken` with `cl100k_base` when available;
- defaults to 400 tokens per chunk with 60-token overlap.

Chunk records retain `chunk_index` and `content_type`.

## Persistence

Every source can have:
- metadata/status;
- raw payload;
- chunks;
- generated insight records.

Postgres uses `apollo_sources` and `apollo_source_payloads`. Filesystem fallback uses JSON metadata and hashed payload files below `APOLLO_DATA_DIR/notebooks/<notebook>/payloads`.

## Retrieval

`rag_service.retrieve_hybrid()` first computes BM25 scores over notebook-scoped chunks. It then optionally embeds the query and executes vector cosine search through pgvector. Candidate ranks are fused with reciprocal-rank fusion using `rrf_k=60`.

If vector search fails, BM25 results remain available.

The retrieval boundary enforces notebook ownership through `get_notebook(user_id, notebook_id)` before exposing chunks.

## Context modes

`backend/context_builder.py` supports exactly four source modes:

- `full`: retrieved chunks plus saved insights;
- `summary`: saved `summary` insights;
- `insights`: saved AI insights;
- `off`: excludes the source.

Context is token-budgeted. The same context contract is reused by chat, Socratic Quick Checks, research and Studio.

## Upload safety

File names are reduced to a basename, reject path/control bytes, and are reserved uniquely before indexing. Filesystem payload writes use a temporary file, flush + fsync, then atomic `os.replace`.

Postgres uses a unique `(notebook_id, name)` boundary and an atomic reservation routine for concurrent names.

## Web ingestion safety

`backend/source_ingestion.py`:
- accepts only HTTP/HTTPS;
- resolves the hostname and rejects private, loopback, link-local, multicast and reserved addresses;
- disables environment proxies so an external proxy cannot bypass the local pin;
- follows at most four redirects;
- revalidates each redirect;
- connects through an adapter pinned to the validated public IP while retaining the original host for Host/SNI semantics;
- caps downloaded URL content at 8 MiB.

This is the repository's explicit SSRF/DNS-rebinding protection.

## Source status and refresh

Source records move through pending/processing/indexed/failed states. Error text is retained for UI display. URL and YouTube sources retain `source_url`, so retry/refresh endpoints can reconstruct the source.

Refresh deliberately rejects a changed content type rather than silently switching parsers.

## What happens when no source is available

General chat can run without notebook context. Socratic prompts explicitly tell the model not to pretend it read a source when none is supplied. Studio requires indexed source context and returns a 400-class response when selected notebook content is unavailable.
