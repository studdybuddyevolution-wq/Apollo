"""Gemini embedding adapter used by Apollo's notebook retrieval layer."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Sequence

from error_classifier import classify_error

MODEL = os.getenv("APOLLO_EMBEDDING_MODEL", "gemini-embedding-2")
DIMENSIONS = int(os.getenv("APOLLO_EMBEDDING_DIMENSIONS", "768"))
BATCH_SIZE = int(os.getenv("APOLLO_EMBEDDING_BATCH_SIZE", "50"))
MAX_RETRIES = int(os.getenv("APOLLO_EMBEDDING_MAX_RETRIES", "3"))


def _client():
    from google import genai
    return genai.Client(api_key=os.getenv("GEMINI_API_KEY", "").strip())


def _embed_batch_sync(texts: Sequence[str]) -> list[list[float]]:
    clean = [str(text or "").strip() for text in texts]
    if not any(clean):
        return [[] for _ in clean]
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    from google.genai import types

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            result = _client().models.embed_content(
                model=MODEL,
                contents=clean,
                config=types.EmbedContentConfig(output_dimensionality=DIMENSIONS),
            )
            vectors = [list(embedding.values or []) for embedding in (result.embeddings or [])]
            if len(vectors) != len(clean):
                raise RuntimeError(f"Embedding service returned {len(vectors)} vectors for {len(clean)} texts")
            return vectors
        except Exception as exc:
            last_error = exc
            if attempt >= MAX_RETRIES - 1:
                break
            time.sleep(2 ** attempt)
    if last_error is not None:
        _, message = classify_error(last_error)
        raise RuntimeError(message) from last_error
    raise RuntimeError("Embedding generation failed.")


def embed_texts_sync(texts: Sequence[str]) -> list[list[float]]:
    clean = [str(text or "").strip() for text in texts]
    if not clean:
        return []
    vectors: list[list[float]] = []
    for start in range(0, len(clean), BATCH_SIZE):
        batch = clean[start:start + BATCH_SIZE]
        vectors.extend(_embed_batch_sync(batch))
    return vectors


def embed_text_sync(text: str) -> list[float]:
    vectors = embed_texts_sync([text])
    return vectors[0] if vectors else []


async def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    return await asyncio.to_thread(embed_texts_sync, texts)


async def embed_text(text: str) -> list[float]:
    return await asyncio.to_thread(embed_text_sync, text)
