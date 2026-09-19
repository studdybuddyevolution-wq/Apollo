from __future__ import annotations

import asyncio
import base64
import json
import os
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from groq import Groq
from pydantic import BaseModel, Field

from request_limits import RequestBodyLimitMiddleware, get_max_request_body_bytes, get_max_upload_bytes
from auth import AuthIdentityMiddleware

from context_builder import build_context
from diagrams import build_diagram_prompt, generate_and_render, content_overlap_ratio
from jobs import enqueue_job, enqueue_embedding_job, get_job
from rag_service import add_source, create_notebook, delete_notebook, format_context, get_notebook, get_notebook_chunks, list_notebooks, list_sources, remove_source, rename_notebook, retrieve
from research_engine import build_synthesis_instruction, format_evidence, is_detailed_request, run_hybrid_research
from transformations import run_transformation
from storage import STORE
from error_classifier import classify_error
from phase3_common import FriendlyGeminiError, extract_json_object, generate_gemini_text
from pptx_generator import build_source_grounded_pptx

_REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_REPO_ROOT / ".env", override=False)

PRIMARY_MODEL = os.getenv("APOLLO_PRIMARY_MODEL", "openai/gpt-oss-120b")
GROQ_VISION_MODEL = os.getenv("APOLLO_VISION_MODEL", "qwen/qwen3.6-27b")
GEMINI_FALLBACK_MODEL = os.getenv("APOLLO_GEMINI_FALLBACK_MODEL", "gemini-3.8-flash")
WEB_SYNTHESIS_MODEL = os.getenv("APOLLO_WEB_SYNTHESIS_MODEL", "gemini-3.8-flash")
GEMINI_FALLBACK_MODELS = [m.strip() for m in os.getenv("APOLLO_GEMINI_FALLBACK_MODELS", "gemini-3.8-flash,gemini-3.5-flash,gemini-3.1-flash-lite").split(",") if m.strip()]
MAX_OUTPUT_TOKENS = 1000
DEEP_OUTPUT_TOKENS = 2500
WEB_OUTPUT_TOKENS = 1400
PRODUCTION_WEB_ORIGIN = "https://apollo.studdybuddyevolution.workers.dev"
RATE_LIMIT_MAX = int(os.getenv("APOLLO_RATE_LIMIT_MAX", "20"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("APOLLO_RATE_LIMIT_WINDOW_SECONDS", "600"))
MAX_UPLOAD_BYTES = get_max_upload_bytes()
MAX_REQUEST_BODY_BYTES = get_max_request_body_bytes()
_rate_limit_lock = threading.Lock()
_rate_limit_hits: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(key: str) -> tuple[bool, int]:
    """Sliding-window limiter. Returns (allowed, retry_after_seconds)."""
    now = time.time()
    with _rate_limit_lock:
        hits = _rate_limit_hits[key]
        cutoff = now - RATE_LIMIT_WINDOW_SECONDS
        while hits and hits[0] < cutoff:
            hits.pop(0)
        if len(hits) >= RATE_LIMIT_MAX:
            retry_after = int(hits[0] + RATE_LIMIT_WINDOW_SECONDS - now) + 1
            return False, max(retry_after, 1)
        hits.append(now)
        return True, 0


app = FastAPI(title="Apollo API", version="0.9.0")
app.add_middleware(RequestBodyLimitMiddleware, max_body_size=MAX_REQUEST_BODY_BYTES)
app.add_middleware(AuthIdentityMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in os.getenv("APOLLO_CORS_ORIGINS", f"http://localhost:5173,{PRODUCTION_WEB_ORIGIN}").split(",") if o.strip()], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    model: str | None = None
    notebook_id: str | None = None
    notebook_title: str | None = None
    active_sources: list[str] = Field(default_factory=list)
    user_id: str | None = None
    web_enabled: bool = False
    research_mode: Literal["quick", "web", "deep", "study", "socratic"] = "quick"
    socratic_topic: str | None = None
    socratic_tier: str | None = None
    socratic_score: float | None = None
    socratic_force_advance: bool = False