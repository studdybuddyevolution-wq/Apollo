"""Phase 1 workspace routes installed alongside the existing FastAPI app."""

from __future__ import annotations

import json
import weakref
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from rag_service import get_notebook
from workspace_service import append_message, create_note, create_session, delete_note, delete_session, get_session, get_socratic_state, list_messages, list_notes, list_sessions, rename_session, save_socratic_state, update_note


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

            socratic_state = None
            if request.research_mode == "socratic":
                from socratic_engine import (
                    SocraticState,
                    apply_phase,
                    next_phase,
                    state_from_dict,
                    state_to_dict,
                    tier_for_score,
                )
                from socratic_engine import get_mastery
                persisted = get_socratic_state(request.user_id, request.notebook_id, session["id"])
                socratic_state = state_from_dict(persisted)
                topic = (request.socratic_topic or socratic_state.topic or request.notebook_title or "").strip() or last_user[:120]
                if socratic_state.topic == "":
                    mastery = get_mastery(request.user_id, topic)
                    if mastery:
                        socratic_state.mastery_score = float(mastery.get("score", 30.0))
                        socratic_state.mastery_tier = str(mastery.get("tier") or tier_for_score(socratic_state.mastery_score))
                selected_phase = next_phase(
                    socratic_state,
                    last_user,
                    force_advance=request.socratic_force_advance,
                )
                socratic_state = apply_phase(socratic_state, selected_phase, topic)
                raw["socratic_topic"] = topic
                raw["socratic_state"] = state_to_dict(socratic_state)
                raw["socratic_score"] = socratic_state.mastery_score
                yield _event({
                    "type": "socratic_state",
                    "phase": socratic_state.phase,
                    "phase_label": __import__("socratic_engine").phase_label(socratic_state.phase),
                    "status": __import__("socratic_engine").phase_status(socratic_state.phase),
                    "in_dialectic_loop": socratic_state.in_dialectic_loop,
                    "maieutics_count": socratic_state.maieutics_count,
                    "mastery_score": round(socratic_state.mastery_score, 1),
                    "mastery_tier": socratic_state.mastery_tier,
                    "user_response_count": socratic_state.user_response_count,
                    "topic": socratic_state.topic,
                })

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
                if socratic_state is not None:
                    save_socratic_state(request.user_id, request.notebook_id, session["id"], state_to_dict(socratic_state))
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
                if socratic_state is not None:
                    save_socratic_state(request.user_id, request.notebook_id, session["id"], state_to_dict(socratic_state))
                return
            except Exception as exc:
                if generated:
                    append_message(request.user_id, request.notebook_id, session["id"], "assistant", "".join(generated), model_name, sources)
                if socratic_state is not None:
                    save_socratic_state(request.user_id, request.notebook_id, session["id"], state_to_dict(socratic_state))
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

    @app.get("/api/notebooks/{notebook_id}/sessions/{session_id}/socratic-state")
    def session_socratic_state(notebook_id: str, session_id: str, user_id: str = "default"):
        _check_notebook(user_id, notebook_id)
        if not get_session(user_id, notebook_id, session_id):
            raise HTTPException(status_code=404, detail="Chat session not found")
        return {"state": get_socratic_state(user_id, notebook_id, session_id)}

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
