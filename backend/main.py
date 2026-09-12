"""Apollo FastAPI backend.

Phase 6 web research uses Tavily for retrieval and Gemini for synthesis,
independent of Groq web-search token quotas. Gemini synthesis now has a
resilient fallback chain: 3.8 Flash -> 3.5 Flash -> 3.1 Flash-Lite.
Phase 5 notebook/RAG remains active.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from groq import Groq
from pydantic import BaseModel, Field
from tavily import TavilyClient

from rag_service import (
    add_source,
    create_notebook,
    delete_notebook,
    format_context,
    get_notebook,
    list_notebooks,
    list_sources,
    remove_source,
    rename_notebook,
    retrieve,
)


_REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_REPO_ROOT / ".env", override=False)

PRIMARY_MODEL = os.getenv("APOLLO_PRIMARY_MODEL", "openai/gpt-oss-120b")
GROQ_VISION_MODEL = os.getenv("APOLLO_VISION_MODEL", "qwen/qwen3.6-27b")
GEMINI_FALLBACK_MODEL = os.getenv("APOLLO_GEMINI_FALLBACK_MODEL", "gemini-3.8-flash")
WEB_SYNTHESIS_MODEL = os.getenv("APOLLO_WEB_SYNTHESIS_MODEL", "gemini-3.8-flash")
GEMINI_FALLBACK_MODELS = [
    model.strip()
    for model in os.getenv(
        "APOLLO_GEMINI_FALLBACK_MODELS",
        "gemini-3.8-flash,gemini-3.5-flash,gemini-3.1-flash-lite",
    ).split(",")
    if model.strip()
]
MAX_OUTPUT_TOKENS = 1000
DEEP_OUTPUT_TOKENS = 3000
WEB_OUTPUT_TOKENS = 1400
PRODUCTION_WEB_ORIGIN = "https://apollo.studdybuddyevolution.workers.dev"


def _cors_origins() -> list[str]:
    raw = os.getenv("APOLLO_CORS_ORIGINS", f"http://localhost:5173,{PRODUCTION_WEB_ORIGIN}")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app = FastAPI(title="Apollo API", version="0.7.0")
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
    model: str | None = None
    notebook_id: str | None = None
    notebook_title: str | None = None
    active_sources: list[str] = Field(default_factory=list)
    user_id: str | None = None
    web_enabled: bool = False
    research_mode: Literal["quick", "web", "deep", "study"] = "quick"


class NotebookCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    user_id: str | None = None


class NotebookRenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    user_id: str | None = None


class RAGQueryRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=10)
    source_names: list[str] = Field(default_factory=list)
    user_id: str | None = None


def _event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _load_overview_context(notebook_id: str, source_names: list[str], max_chunks: int = 6) -> tuple[str, list[str]]:
    data_dir = Path(os.getenv("APOLLO_DATA_DIR", Path(__file__).resolve().parent / "data"))
    chunks_path = data_dir / "notebooks" / notebook_id / "chunks.json"
    if not chunks_path.exists():
        return "", source_names
    try:
        chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    except Exception:
        return "", source_names
    allowed = set(source_names or [])
    filtered = [chunk for chunk in chunks if not allowed or chunk.get("source") in allowed]
    if not filtered:
        return "", source_names
    selected: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    for chunk in filtered:
        source = chunk.get("source", "unknown source")
        if source not in seen_sources:
            selected.append(chunk)
            seen_sources.add(source)
            if len(selected) >= max_chunks:
                break
    if len(selected) < max_chunks:
        selected_ids = {chunk.get("id") for chunk in selected}
        for chunk in filtered:
            if chunk.get("id") in selected_ids:
                continue
            selected.append(chunk)
            if len(selected) >= max_chunks:
                break
    context = format_context(
        [{"source": c.get("source", "unknown source"), "text": c.get("text", ""), "score": 0.0} for c in selected],
        max_chars=9000,
    )
    return context, list(dict.fromkeys(c.get("source", "unknown source") for c in selected))


def _system_message(request: ChatRequest, context: str, source_names: list[str]) -> dict[str, str]:
    notebook = request.notebook_title or "the active notebook"
    sources = ", ".join(source_names) if source_names else "no active sources"
    content = (
        "You are Apollo Omni AI, a helpful academic AI companion. "
        f"The current notebook is {notebook}. Available sources: {sources}. "
        "Answer directly and naturally. Keep private chain-of-thought/reasoning hidden; "
        "return only the answer, conclusions, and useful explanations. "
        "Use supplied source context when it is relevant, and distinguish it from your own knowledge. "
        "When the user asks what a source is about, summarize the supplied source context instead of "
        "saying you lack access to the file. "
        "Do not claim to have searched or read a source unless the backend supplied that context."
    )
    if request.web_enabled:
        if request.research_mode in {"deep", "study"}:
            content += (
                " You are in Deep Research mode. Multiple independent web searches will be supplied. "
                "Synthesize them into a comprehensive, well-structured answer rather than summarizing each search. "
                "Resolve contradictions where possible, prefer primary or authoritative sources, and call out uncertainty. "
                "For school-level questions, explain concepts clearly from foundations through important examples. "
                "Use normal Markdown headings and bullets where helpful, but NEVER use Markdown tables, raw HTML, <br> tags, "
                "search-engine citation syntax, or pasted search-result snippets."
            )
        else:
            content += (
                " Live web research is enabled. Web results are supplied by Tavily. "
                "Use those results as evidence, synthesize them into a direct answer, and do not paste search results. "
                "Do not use Markdown tables, raw HTML, <br> tags, or internal citation markers. "
                "Prefer authoritative sources and clearly distinguish web findings from notebook material."
            )
    if context:
        content += f"\n\nSOURCE CONTEXT:\n{context}"
    return {"role": "system", "content": content}


def _conversation_text(messages: list[ChatMessage], system_content: str) -> str:
    lines = [f"SYSTEM:\n{system_content}"]
    for message in messages:
        lines.append(f"{message.role.upper()}:\n{message.content}")
    return "\n\n".join(lines)


def _stream_groq(request: ChatRequest, messages: list[dict[str, str]], model: str):
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not configured")
    client = Groq(api_key=api_key)
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "stream": True,
    }
    if model.startswith("openai/gpt-oss") or model.startswith("qwen/"):
        kwargs["reasoning_format"] = "hidden"
        if model.startswith("openai/gpt-oss"):
            kwargs["reasoning_effort"] = "medium"
    stream = client.chat.completions.create(**kwargs)
    yield _event({"type": "start", "model": model, "provider": "groq", "web": False, "research": "quick"})
    for chunk in stream:
        token = chunk.choices[0].delta.content or ""
        if token:
            yield _event({"type": "token", "text": token})
    yield _event({"type": "done"})


def _search_tavily(query: str, deep: bool = False) -> tuple[str, list[dict[str, str]]]:
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY is not configured")
    client = TavilyClient(api_key=api_key)
    response = client.search(
        query=query,
        search_depth="advanced" if deep else "basic",
        topic="general",
        max_results=8 if deep else 5,
        chunks_per_source=3,
        include_answer=False,
        include_raw_content=deep,
    )
    sources: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    context_parts: list[str] = []
    total_chars = 0
    max_chars = 15000 if deep else 11000
    for index, item in enumerate(response.get("results", []) or [], start=1):
        url = str(item.get("url") or "").strip()
        title = str(item.get("title") or url).strip()
        text = str(item.get("raw_content") or item.get("content") or "").strip()
        if url and url not in seen_urls:
            sources.append({"title": title[:180], "url": url})
            seen_urls.add(url)
        if not text:
            continue
        block = f"SOURCE {index}: {title}\nURL: {url}\n{text}"
        remaining = max_chars - total_chars
        if remaining <= 0:
            break
        block = block[:remaining]
        context_parts.append(block)
        total_chars += len(block)
    return "\n\n---\n\n".join(context_parts), sources[:8]


def _deep_research_queries(question: str, study: bool) -> list[str]:
    if study:
        return [
            f"{question} official sources and current evidence; focus on facts that complement or challenge a student's notes",
            f"{question} authoritative explanation, examples, major dates or definitions, and common misconceptions",
            f"{question} primary or institutional sources plus recent context and important caveats",
        ]
    return [
        f"{question} authoritative overview primary sources current evidence",
        f"{question} detailed explanation examples historical or technical context and important caveats",
        f"{question} competing perspectives primary sources limitations and facts that would change the conclusion",
    ]


def _gemini_model_chain(primary: str) -> list[str]:
    chain = [primary] + [model for model in GEMINI_FALLBACK_MODELS if model != primary]
    return list(dict.fromkeys(chain))


def _stream_gemini_resilient(
    *,
    prompt: str,
    system_instruction: str,
    output_tokens: int,
    primary_model: str,
    event_meta: dict[str, Any],
):
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    models = _gemini_model_chain(primary_model)
    last_error: Exception | None = None

    for index, model in enumerate(models):
        emitted = False
        try:
            stream = client.models.generate_content_stream(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=output_tokens,
                    system_instruction=system_instruction,
                ),
            )
            yield _event({
                "type": "start",
                "model": model,
                **event_meta,
            })
            for chunk in stream:
                text = getattr(chunk, "text", None) or ""
                if text:
                    emitted = True
                    yield _event({"type": "token", "text": text})
            yield _event({"type": "done", "model": model, **{k: v for k, v in event_meta.items() if k != "web" or v}})
            return
        except Exception as exc:
            last_error = exc
            if emitted:
                yield _event({"type": "error", "message": f"Gemini {model} stream failed after output: {exc}"})
                return
            if index < len(models) - 1:
                next_model = models[index + 1]
                yield _event({
                    "type": "fallback",
                    "from_model": model,
                    "to_model": next_model,
                    "reason": str(exc),
                })
                continue
            break

    raise RuntimeError(f"All Gemini synthesis models failed: {last_error}")


def _stream_web_with_tavily(request: ChatRequest, system_content: str):
    question = next((m.content for m in reversed(request.messages) if m.role == "user"), "")
    if not question:
        raise RuntimeError("No user query supplied for web research")

    deep = request.research_mode in {"deep", "study"}
    queries = _deep_research_queries(question, request.research_mode == "study") if deep else [question]
    dossiers: list[str] = []
    all_sources: list[dict[str, str]] = []

    for query in queries:
        web_context, sources = _search_tavily(query, deep=deep)
        if web_context:
            dossiers.append(f"RESEARCH QUERY: {query}\n{web_context}")
        all_sources.extend(sources)

    if not dossiers:
        raise RuntimeError("Tavily returned no usable web results")

    unique_sources = list({source["url"]: source for source in all_sources if source.get("url")}.values())[:12]
    web_context = "\n\n========== RESEARCH PASS ==========\n\n".join(dossiers)

    if deep:
        synthesis_instruction = (
            system_content
            + "\n\nYou are Apollo's Deep Research synthesizer. The following dossier contains multiple independent web research passes. "
            + "Write the final answer yourself. Do not mention the dossier or the research process. "
            + "For a request for extreme detail, be thorough and educational: define the topic, build the explanation chronologically or logically, "
            + "cover major events/ideas, explain causes and effects, provide concrete examples, and finish with key takeaways. "
            + "Aim for a substantial answer, not a brief summary. Do not stop after the introduction. "
            + "Do not pad the answer with repetition. Use clean Markdown headings and bullet points. "
            + "Never emit Markdown tables, raw HTML, <br>, pipe-separated tables, or search-result syntax."
        )
        output_tokens = DEEP_OUTPUT_TOKENS
    else:
        synthesis_instruction = (
            system_content
            + "\n\nYou are Apollo's web-answer synthesizer. Write the answer yourself from the Tavily evidence. "
            + "Do not paste snippets. Use clean Markdown headings or bullets only where useful. "
            + "Never emit Markdown tables, raw HTML, <br>, or search-result citation syntax."
        )
        output_tokens = WEB_OUTPUT_TOKENS

    prompt = _conversation_text(request.messages, synthesis_instruction)
    prompt += f"\n\nTAVILY RESEARCH DOSSIER:\n{web_context}"

    yield _event({"type": "sources", "sources": unique_sources}) if unique_sources else ""
    yield from _stream_gemini_resilient(
        prompt=prompt,
        system_instruction=synthesis_instruction,
        output_tokens=output_tokens,
        primary_model=WEB_SYNTHESIS_MODEL,
        event_meta={
            "provider": "gemini+tavily",
            "web": True,
            "deep": deep,
            "research": request.research_mode,
        },
    )


def _stream_gemini(request: ChatRequest, system_content: str, model: str):
    prompt = _conversation_text(request.messages, system_content)
    yield from _stream_gemini_resilient(
        prompt=prompt,
        system_instruction=system_content,
        output_tokens=MAX_OUTPUT_TOKENS,
        primary_model=model,
        event_meta={
            "provider": "gemini",
            "fallback": True,
            "web": False,
            "research": "quick",
        },
    )


def _stream_model(request: ChatRequest, context: str, source_names: list[str]):
    system = _system_message(request, context, source_names)
    messages = [system] + [{"role": message.role, "content": message.content} for message in request.messages]
    if request.web_enabled:
        yield from _stream_web_with_tavily(request, system["content"])
        return

    groq_model = request.model or PRIMARY_MODEL
    try:
        yield from _stream_groq(request, messages, groq_model)
        return
    except Exception as primary_exc:
        if not os.getenv("GEMINI_API_KEY", "").strip():
            raise primary_exc
        yield _event({"type": "fallback", "from_model": groq_model, "to_model": GEMINI_FALLBACK_MODEL, "reason": str(primary_exc)})
        yield from _stream_gemini(request, system["content"], GEMINI_FALLBACK_MODEL)


def _stream_chat(request: ChatRequest):
    try:
        active_source_names = list(request.active_sources)
        context = ""
        if request.notebook_id:
            last_user_message = next((message.content for message in reversed(request.messages) if message.role == "user"), "")
            if last_user_message:
                results = retrieve(request.user_id, request.notebook_id, last_user_message, top_k=5, source_names=active_source_names)
                context = format_context(results)
                if results:
                    active_source_names = list(dict.fromkeys(result["source"] for result in results))
                else:
                    context, overview_sources = _load_overview_context(request.notebook_id, active_source_names)
                    if overview_sources:
                        active_source_names = overview_sources
        yield from _stream_model(request, context, active_source_names)
    except Exception as exc:
        yield _event({"type": "error", "message": str(exc)})


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "apollo-api",
        "version": "0.7.0",
        "groq_configured": bool(os.getenv("GROQ_API_KEY", "").strip()),
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY", "").strip()),
        "tavily_configured": bool(os.getenv("TAVILY_API_KEY", "").strip()),
        "primary_model": PRIMARY_MODEL,
        "vision_model": GROQ_VISION_MODEL,
        "fallback_model": GEMINI_FALLBACK_MODEL,
        "gemini_fallback_chain": GEMINI_FALLBACK_MODELS,
        "web_search": "tavily",
    }


@app.get("/api/notebooks")
def notebooks(user_id: str = "default"):
    return {"notebooks": list_notebooks(user_id)}


@app.post("/api/notebooks")
def notebook_create(request: NotebookCreateRequest):
    return create_notebook(request.user_id, request.title)


@app.get("/api/notebooks/{notebook_id}")
def notebook_detail(notebook_id: str, user_id: str = "default"):
    notebook = get_notebook(user_id, notebook_id)
    if notebook is None:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return notebook


@app.patch("/api/notebooks/{notebook_id}")
def notebook_rename(notebook_id: str, request: NotebookRenameRequest):
    notebook = rename_notebook(request.user_id, notebook_id, request.title)
    if notebook is None:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return notebook


@app.delete("/api/notebooks/{notebook_id}")
def notebook_delete(notebook_id: str, user_id: str = "default"):
    if not delete_notebook(user_id, notebook_id):
        raise HTTPException(status_code=404, detail="Notebook not found")
    return {"deleted": True, "id": notebook_id}


@app.get("/api/notebooks/{notebook_id}/sources")
def notebook_sources(notebook_id: str, user_id: str = "default"):
    if get_notebook(user_id, notebook_id) is None:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return {"sources": list_sources(user_id, notebook_id)}


@app.post("/api/notebooks/{notebook_id}/sources")
async def notebook_source_upload(
    notebook_id: str,
    file: UploadFile = File(...),
    user_id: str = Query("default"),
):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    try:
        return add_source(user_id, notebook_id, file.filename or "source.txt", raw)
    except KeyError:
        raise HTTPException(status_code=404, detail="Notebook not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/notebooks/{notebook_id}/sources/{source_name}")
def notebook_source_delete(notebook_id: str, source_name: str, user_id: str = "default"):
    if get_notebook(user_id, notebook_id) is None:
        raise HTTPException(status_code=404, detail="Notebook not found")
    if not remove_source(user_id, notebook_id, source_name):
        raise HTTPException(status_code=404, detail="Source not found")
    return {"deleted": True, "name": source_name}


@app.post("/api/notebooks/{notebook_id}/search")
def notebook_search(notebook_id: str, request: RAGQueryRequest):
    if get_notebook(request.user_id, notebook_id) is None:
        raise HTTPException(status_code=404, detail="Notebook not found")
    results = retrieve(request.user_id, notebook_id, request.query, top_k=request.top_k, source_names=request.source_names)
    return {"results": results}


@app.post("/api/chat")
def chat(request: ChatRequest) -> StreamingResponse:
    return StreamingResponse(
        _stream_chat(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
