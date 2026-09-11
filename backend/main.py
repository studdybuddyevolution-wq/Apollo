"""Apollo FastAPI backend - Phase 3.

Phase 3 deliberately keeps the API boundary small: health + streaming chat.
The existing Streamlit application remains untouched while the React frontend
moves onto the new backend incrementally.
"""

from __future__ import annotations

import json
import os
from typing import Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from groq import Groq
from pydantic import BaseModel, Field


DEFAULT_MODEL = "qwen/qwen3.6-27b"
MAX_OUTPUT_TOKENS = 900  # Keep below the current 1,000 OTPM free-tier limit.


def _cors_origins() -> list[str]:
    raw = os.getenv("APOLLO_CORS_ORIGINS", "http://localhost:5173")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app = FastAPI(title="Apollo API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    model: str = DEFAULT_MODEL
    notebook_id: str | None = None
    notebook_title: str | None = None
    active_sources: list[str] = Field(default_factory=list)


def _event(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _system_message(request: ChatRequest) -> dict[str, str]:
    notebook = request.notebook_title or "the active notebook"
    sources = ", ".join(request.active_sources) if request.active_sources else "no active sources"
    return {
        "role": "system",
        "content": (
            "You are Apollo Omni AI, a helpful academic AI companion. "
            f"The current notebook is {notebook}. Active sources: {sources}. "
            "Answer clearly and accurately. Do not claim to have searched or read a source "
            "unless the backend actually supplies that context."
        ),
    }


def _stream_groq(request: ChatRequest):
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        yield _event({
            "type": "error",
            "message": "GROQ_API_KEY is not configured for the FastAPI backend.",
        })
        return

    try:
        client = Groq(api_key=api_key)
        messages = [_system_message(request)] + [
            {"role": message.role, "content": message.content}
            for message in request.messages
        ]

        stream = client.chat.completions.create(
            model=request.model or DEFAULT_MODEL,
            messages=messages,
            temperature=0.3,
            max_tokens=MAX_OUTPUT_TOKENS,
            stream=True,
        )

        yield _event({"type": "start", "model": request.model or DEFAULT_MODEL})

        for chunk in stream:
            token = chunk.choices[0].delta.content or ""
            if token:
                yield _event({"type": "token", "text": token})

        yield _event({"type": "done"})
    except Exception as exc:  # surface useful backend diagnostics to the frontend
        yield _event({"type": "error", "message": str(exc)})


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "apollo-api",
        "groq_configured": bool(os.getenv("GROQ_API_KEY", "").strip()),
    }


@app.post("/api/chat")
def chat(request: ChatRequest) -> StreamingResponse:
    return StreamingResponse(
        _stream_groq(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
