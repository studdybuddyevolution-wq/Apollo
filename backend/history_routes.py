from __future__ import annotations

import weakref

from fastapi import FastAPI, HTTPException

from analytics_service import get_progress_dashboard
from session_history import list_messages_page, list_sessions_page

_REGISTERED: weakref.WeakSet[FastAPI] = weakref.WeakSet()


def register(app: FastAPI) -> None:
    if app in _REGISTERED:
        return

    @app.get("/api/sessions")
    def sessions(
        user_id: str = "default",
        limit: int = 30,
        cursor: str | None = None,
        search: str | None = None,
        notebook_id: str | None = None,
        kind: str = "all",
    ):
        if kind not in {"all", "chat", "socratic"}:
            raise HTTPException(status_code=400, detail="kind must be all, chat, or socratic")
        return list_sessions_page(
            user_id,
            limit=limit,
            cursor=cursor,
            search=search,
            notebook_id=notebook_id,
            kind=kind,
        )

    @app.get("/api/notebooks/{notebook_id}/sessions/{session_id}/messages/page")
    def session_message_page(
        notebook_id: str,
        session_id: str,
        user_id: str = "default",
        limit: int = 40,
        cursor: str | None = None,
    ):
        result = list_messages_page(
            user_id,
            notebook_id,
            session_id,
            limit=limit,
            cursor=cursor,
        )
        if result["limit"] == 0:
            raise HTTPException(status_code=404, detail="Chat session not found")
        return result

    @app.get("/api/progress/dashboard")
    def progress_dashboard(user_id: str = "default", days: int = 30):
        return get_progress_dashboard(user_id, days=days)

    _REGISTERED.add(app)
