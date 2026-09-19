"""Phase 1 workspace routes installed alongside the existing FastAPI app."""

from __future__ import annotations

import json
import weakref
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from rag_service import get_notebook
from workspace_service import append_message, create_note, create_session, delete_note, delete_session, get_session, list_messages, list_notes, list_sessions, rename_session, update_note


class Phase1ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class Phase1ChatRequest(BaseModel):
    messages: list[Phase1ChatMessage] = Field(min_length=1)
    model: str | None = None
    notebook_id: str | None = None
    notebook_title: str | None = None
    active_sources: list[str] = Field(default_factory=list)
    source_modes: dict[str, str] = Field(default_factory=dict)
    user_id: str | None = None
    web_enabled: bool = False
    research_mode: Literal["quick", "web", "deep", "study", "socratic"] = "quick"
    socratic_topic: str | None = None
    socratic_tier: str | None = None
    socratic_score: float | None = None
    session_id: str | None = None


class SessionRequest(BaseModel):
    title: str = Field(default="New chat", min_length=1, max_length=120)
    user_id: str | None = None


class NoteRequest(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1)
    source_type: str = Field(default="manual", min_length=1, max_length=40)
    source_ref: str | None = None
    user_id: str | None = None


class NoteUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1)
    user_id: str | None = None


_REGISTERED_APPS: weakref.WeakSet[FastAPI] = weakref.WeakSet()


def _check_notebook(user_id: str | None, notebook_id: str) -> None:
    if get_notebook(user_id, notebook_id) is None:
        raise HTTPException(status_code=404, detail="Notebook not found")


def _event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _register_chat(app: FastAPI) -> None:
    @app.post("/api/chat/workspace")
    def workspace_chat(request: Phase1ChatRequest, http_request: Request) -> StreamingResponse:
        from context_builder import build_context
        from main import _check_rate_limit, _stream_model

        if not request.notebook_id:
            raise HTTPException(status_code=400, detail="A notebook is required for workspace chat")
        _check_notebook(request.user_id, request.notebook_id)
        if request.session_id and not get_session(request.user_id, request.notebook_id, request.session_id):
            raise HTTPException(status_code=404, detail="Chat session not found")
        session = get_session(request.user_id, request.notebook_id, request.session_id) if request.session_id else create_session(request.user_id, request.notebook_id)
        last_user = next((message.content for message in reversed(request.messages) if message.role == "user"), "").strip()
        if not last_user:
            raise HTTPException(status_code=400, detail="No user message supplied")

        rate_key = request.user_id or (http_request.client.host if http_request.client else "anonymous")
        allowed, retry_after = _check_rate_limit(rate_key)
        if not allowed:
            raise HTTPException(status_code=429, detail=f"Rate limit exceeded. Try again in {retry_after} seconds.", headers={"Retry-After": str(retry_after)})

        def stream():
            if not request.session_id:
                yield _event({"type": "session", "session": session})
            append_message(request.user_id, request.notebook_id, session["id"], "user", last_user)
            built = build_context(
                request.user_id,
                request.notebook_id,
                request.active_sources,
                last_user,
                token_budget=1800,
                top_k=8,
                include_insights=True,
                source_modes=request.source_modes,
            )
            context = built["context"]
            source_names = built["full_sources"]
            raw = request.model_dump()
            raw["messages"] = [type("Msg", (), item.model_dump())() for item in request.messages]
            main_request = type("WorkspaceChat", (), raw)()
            generated: list[str] = []
            sources: list[dict[str, Any]] = []
            model_name: str | None = None
            try:
                for event in _stream_model(main_request, context, source_names):
                    if event.startswith("data: "):
                        try:
                            payload = json.loads(event[6:].strip())
                        except Exception:
                            payload = {}
                        if payload.get("type") == "token":
                            generated.append(payload.get("text", ""))
                        elif payload.get("type") == "sources":
                            sources = payload.get("sources") or []
                        elif payload.get("type") == "start":
                            model_name = payload.get("model")
                    yield event
                if generated:
                    append_message(request.user_id, request.notebook_id, session["id"], "assistant", "".join(generated), model_name, sources)
            except GeneratorExit:
                if generated:
                    append_message(
                        request.user_id,
                        request.notebook_id,
                        session["id"],
                        "assistant",
                        "".join(generated),
                        model_name,
                        sources,
                    )
                return
            except Exception as exc:
                if generated:
                    append_message(request.user_id, request.notebook_id, session["id"], "assistant", "".join(generated), model_name, sources)
                yield _event({"type": "error", "message": str(exc)})

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no-cache"})


def _register_sessions(app: FastAPI) -> None:
    @app.get("/api/notebooks/{notebook_id}/sessions")
    def sessions(notebook_id: str, user_id: str = "default"):
        _check_notebook(user_id, notebook_id)
        return {"sessions": list_sessions(user_id, notebook_id)}

    @app.post("/api/notebooks/{notebook_id}/sessions")
    def session_create(notebook_id: str, request: SessionRequest):
        _check_notebook(request.user_id, notebook_id)
        return create_session(request.user_id, notebook_id, request.title)

    @app.patch("/api/notebooks/{notebook_id}/sessions/{session_id}")
    def session_rename(notebook_id: str, session_id: str, request: SessionRequest):
        _check_notebook(request.user_id, notebook_id)
        row = rename_session(request.user_id, notebook_id, session_id, request.title)
        if row is None:
            raise HTTPException(status_code=404, detail="Chat session not found")
        return row

    @app.delete("/api/notebooks/{notebook_id}/sessions/{session_id}")
    def session_delete(notebook_id: str, session_id: str, user_id: str = "default"):
        _check_notebook(user_id, notebook_id)
        if not delete_session(user_id, notebook_id, session_id):
            raise HTTPException(status_code=404, detail="Chat session not found")
        return {"deleted": True, "id": session_id}

    @app.get("/api/notebooks/{notebook_id}/sessions/{session_id}/messages")
    def session_messages(notebook_id: str, session_id: str, user_id: str = "default"):
        _check_notebook(user_id, notebook_id)
        if not get_session(user_id, notebook_id, session_id):
            raise HTTPException(status_code=404, detail="Chat session not found")
        return {"messages": list_messages(user_id, notebook_id, session_id)}


def _register_notes(app: FastAPI) -> None:
    @app.get("/api/notebooks/{notebook_id}/notes")
    def notes(notebook_id: str, user_id: str = "default"):
        _check_notebook(user_id, notebook_id)
        return {"notes": list_notes(user_id, notebook_id)}

    @app.post("/api/notebooks/{notebook_id}/notes")
    def note_create(notebook_id: str, request: NoteRequest):
        _check_notebook(request.user_id, notebook_id)
        try:
            return create_note(request.user_id, notebook_id, request.title, request.content, request.source_type, request.source_ref)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.patch("/api/notebooks/{notebook_id}/notes/{note_id}")
    def note_update_route(notebook_id: str, note_id: str, request: NoteUpdateRequest):
        _check_notebook(request.user_id, notebook_id)
        try:
            note = update_note(request.user_id, notebook_id, note_id, request.title, request.content)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if note is None:
            raise HTTPException(status_code=404, detail="Note not found")
        return note

    @app.delete("/api/notebooks/{notebook_id}/notes/{note_id}")
    def note_delete(notebook_id: str, note_id: str, user_id: str = "default"):
        _check_notebook(user_id, notebook_id)
        if not delete_note(user_id, notebook_id, note_id):
            raise HTTPException(status_code=404, detail="Note not found")
        return {"deleted": True, "id": note_id}


def register(app: FastAPI) -> None:
    if app in _REGISTERED_APPS:
        return
    _register_chat(app)
    _register_sessions(app)
    _register_notes(app)
    _REGISTERED_APPS.add(app)
