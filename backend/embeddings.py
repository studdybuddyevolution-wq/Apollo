"""Embedding service for Apollo's semantic retrieval layer."""
from __future__ import annotations

import asyncio
import os
import time
from typing import Iterable

EMBEDDING_MODEL = os.getenv("APOLLO_EMBEDDING_MODEL", "gemini-embedding-2")
EMBEDDING_DIM = int(os.getenv("APOLLO_EMBEDDING_DIM", "768"))
EMBED_BATCH_SIZE = int(os.getenv("APOLLO_EMBED_BATCH_SIZE", "50"))
MAX_RETRIES = int(os.getenv("APOLLO_EMBEDDING_RETRIES", "3"))


def _client():
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    from google import genai
    return genai.Client(api_key=key)


def embed_texts(texts: Iterable[str]) -> list[list[float]]:
    values = [str(text or "").strip() for text in texts]
    if not values:
        return []
    client = _client()
    from google.genai import types

    embeddings: list[list[float]] = []
    for start in range(0, len(values), EMBED_BATCH_SIZE):
        batch = values[start:start + EMBED_BATCH_SIZE]
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                response = client.models.embed_content(
                    model=EMBEDDING_MODEL,
                    contents=batch,
                    config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIM),
                )
                batch_embeddings = [list(getattr(item, "values", []) or []) for item in (response.embeddings or [])]
                if len(batch_embeddings) != len(batch):
                    raise RuntimeError(
                        f"Embedding response count mismatch: expected {len(batch)}, got {len(batch_embeddings)}"
                    )
                embeddings.extend(batch_embeddings)
                break
            except Exception as exc:  # pragma: no cover - depends on external API
                last_error = exc
                if attempt + 1 >= MAX_RETRIES:
                    raise
                time.sleep(2 ** attempt)
        if last_error and len(embeddings) < start + len(batch):
            raise last_error
    return embeddings


def embed_text(text: str) -> list[float]:
    results = embed_texts([text])
    return results[0] if results else []


async def embed_texts_async(texts: Iterable[str]) -> list[list[float]]:
    return await asyncio.to_thread(embed_texts, list(texts))
