"""Phase 2 research-ingestion and capability routes."""

from __future__ import annotations

import asyncio
import importlib.util
import os
import weakref

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from jobs import enqueue_embedding_job
from rag_service import add_source, get_notebook, get_source_metadata, get_source_payload
from phase3_common import gemini_model_chain
from error_classifier import classify_source_error
from source_ingestion import ingest_url, ingest_youtube, refresh_url_source, refresh_youtube_source
from storage import STORE

_REGISTERED_APPS: weakref.WeakSet[FastAPI] = weakref.WeakSet()


class URLSourceRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    user_id: str | None = None


class YouTubeSourceRequest(BaseModel):
    url: str = Field(min_length=12, max_length=2048)
    languages: list[str] = Field(default_factory=lambda: ["en"], max_length=8)
    user_id: str | None = None


class SourceLifecycleRequest(BaseModel):
    user_id: str | None = None


def _check_notebook(user_id: str | None, notebook_id: str) -> None:
    if get_notebook(user_id, notebook_id) is None:
        raise HTTPException(status_code=404, detail="Notebook not found")


def register(app: FastAPI) -> None:
    if app in _REGISTERED_APPS:
        return

    @app.get("/api/capabilities")
    def capabilities():
        youtube_ready = importlib.util.find_spec("youtube_transcript_api") is not None
        vector_ready = bool(STORE and STORE.vector_available())
        return {
            "source_ingestion": {
                "file": True,
                "url": True,
                "youtube": youtube_ready,
            },
            "retrieval": {
                "bm25": True,
                "hybrid_vector": vector_ready,
            },
            "transformations": {
                "summary": True,
                "key_points": True,
                "study_guide": True,
                "flashcards": True,
            },
            "research": {
                "quick": True,
                "web": True,
                "deep": True,
                "study": True,
            },
            "ai_models": gemini_model_chain(max_models=3),
            "providers": {
                "gemini": {
                    "configured": bool(os.getenv("GEMINI_API_KEY", "").strip()),
                    "models": gemini_model_chain(max_models=8),
                },
                "groq": {
                    "configured": bool(os.getenv("GROQ_API_KEY", "").strip()),
                    "primary_model": os.getenv("APOLLO_PRIMARY_MODEL", "openai/gpt-oss-120b"),
                },
                "tavily": {
                    "configured": bool(os.getenv("TAVILY_API_KEY", "").strip()),
                },
            },
        }

    @app.post("/api/notebooks/{notebook_id}/sources/url")
    async def notebook_url_source(notebook_id: str, request: URLSourceRequest):
        _check_notebook(request.user_id, notebook_id)
        try:
            result = await asyncio.to_thread(ingest_url, request.user_id, notebook_id, request.url)
            result["embedding_job"] = await enqueue_embedding_job(notebook_id, request.user_id, result["name"])
            return result
        except Exception as exc:
            retryable, status_code, message = classify_source_error(exc)
            headers = {"Retry-After": "3"} if retryable else None
            raise HTTPException(status_code=status_code, detail=message, headers=headers) from exc

    @app.post("/api/notebooks/{notebook_id}/sources/{source_name:path}/retry")
    async def notebook_source_retry(notebook_id: str, source_name: str, request: SourceLifecycleRequest):
        _check_notebook(request.user_id, notebook_id)
        try:
            metadata = get_source_metadata(request.user_id, notebook_id, source_name)
            payload = get_source_payload(request.user_id, notebook_id, source_name)
            if not metadata or payload is None:
                raise HTTPException(status_code=404, detail="Source payload is no longer available for retry")
            result = await asyncio.to_thread(
                add_source,
                request.user_id,
                notebook_id,
                source_name,
                payload,
                kind=str(metadata.get("kind") or "file"),
                source_url=metadata.get("source_url"),
            )
            result["embedding_job"] = await enqueue_embedding_job(notebook_id, request.user_id, source_name)
            return result
        except HTTPException:
            raise
        except Exception as exc:
            retryable, status_code, message = classify_source_error(exc)
            headers = {"Retry-After": "3"} if retryable else None
            raise HTTPException(status_code=status_code, detail=message, headers=headers) from exc

    @app.post("/api/notebooks/{notebook_id}/sources/{source_name:path}/refresh")
    async def notebook_source_refresh(notebook_id: str, source_name: str, request: SourceLifecycleRequest):
        _check_notebook(request.user_id, notebook_id)
        metadata = get_source_metadata(request.user_id, notebook_id, source_name) or {}
        kind = str(metadata.get("kind") or "")
        try:
            if kind == "url":
                result = await asyncio.to_thread(refresh_url_source, request.user_id, notebook_id, source_name)
            elif kind == "youtube":
                result = await asyncio.to_thread(refresh_youtube_source, request.user_id, notebook_id, source_name)
            else:
                raise HTTPException(status_code=400, detail="Only web and YouTube sources can be refreshed")
            result["embedding_job"] = await enqueue_embedding_job(notebook_id, request.user_id, source_name)
            return result
        except HTTPException:
            raise
        except Exception as exc:
            retryable, status_code, message = classify_source_error(exc)
            headers = {"Retry-After": "3"} if retryable else None
            raise HTTPException(status_code=status_code, detail=message, headers=headers) from exc

    @app.post("/api/notebooks/{notebook_id}/sources/youtube")
    async def notebook_youtube_source(notebook_id: str, request: YouTubeSourceRequest):
        _check_notebook(request.user_id, notebook_id)
        try:
            result = await asyncio.to_thread(ingest_youtube, request.user_id, notebook_id, request.url, request.languages)
            result["embedding_job"] = await enqueue_embedding_job(notebook_id, request.user_id, result["name"])
            return result
        except Exception as exc:
            retryable, status_code, message = classify_source_error(exc)
            headers = {"Retry-After": "3"} if retryable else None
            raise HTTPException(status_code=status_code, detail=message, headers=headers) from exc

    _REGISTERED_APPS.add(app)
