"""Phase 1 chat-session and note persistence with Postgres/filesystem fallback."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import threading
import uuid
from pathlib import Path
from typing import Any

from storage import STORE

DATA_DIR = Path(os.getenv("APOLLO_DATA_DIR", Path(__file__).resolve().parent / "data"))
WORKSPACE_FILE = DATA_DIR / "workspace.json"
_LOCK = threading.RLock()


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _user_key(user_id: str | None) -> str:
    return (user_id or "default").strip() or "default"


def _load() -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not WORKSPACE_FILE.exists():
        return {"sessions": {}, "messages": {}, "notes": {}}
    try:
        value = json.loads(WORKSPACE_FILE.read_text(encoding="utf-8"))
        value.setdefault("sessions", {})
        value.setdefault("messages", {})
        value.setdefault("notes", {})
        return value
    except Exception:
        return {"sessions": {}, "messages": {}, "notes": {}}


def _save(data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    WORKSPACE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def list_sessions(user_id: str | None, notebook_id: str) -> list[dict[str, Any]]:
    key = _user_key(user_id)
    if STORE:
        return STORE.list_chat_sessions(key, notebook_id)
    with _LOCK:
        data = _load()
        rows = [row for row in data["sessions"].values() if row.get("user_id") == key and row.get("notebook_id") == notebook_id]
        rows.sort(key=lambda row: row.get("updated", ""), reverse=True)
        return rows


def create_session(user_id: str | None, notebook_id: str, title: str = "New chat") -> dict[str, Any]:
    key = _user_key(user_id)
    clean_title = title.strip() or "New chat"
    now = _now()
    record = {"id": "chat_" + uuid.uuid4().hex[:12], "notebook_id": notebook_id, "user_id": key, "title": clean_title[:120], "created": now, "updated": now}
    if STORE:
        return STORE.create_chat_session(record)
    with _LOCK:
        data = _load()
        data["sessions"][record["id"]] = record
        data["messages"][record["id"]] = []
        _save(data)
    return record


def get_session(user_id: str | None, notebook_id: str, session_id: str) -> dict[str, Any] | None:
    key = _user_key(user_id)
    if STORE:
        return STORE.get_chat_session(key, notebook_id, session_id)
    with _LOCK:
        row = _load()["sessions"].get(session_id)
        if row and row.get("user_id") == key and row.get("notebook_id") == notebook_id:
            return row
    return None


def rename_session(user_id: str | None, notebook_id: str, session_id: str, title: str) -> dict[str, Any] | None:
    clean_title = title.strip() or "New chat"
    key = _user_key(user_id)
    if STORE:
        return STORE.rename_chat_session(key, notebook_id, session_id, clean_title[:120], _now())
    with _LOCK:
        data = _load()
        row = data["sessions"].get(session_id)
        if not row or row.get("user_id") != key or row.get("notebook_id") != notebook_id:
            return None
        row["title"] = clean_title[:120]
        row["updated"] = _now()
        _save(data)
        return row


def delete_session(user_id: str | None, notebook_id: str, session_id: str) -> bool:
    key = _user_key(user_id)
    if STORE:
        return STORE.delete_chat_session(key, notebook_id, session_id)
    with _LOCK:
        data = _load()
        row = data["sessions"].get(session_id)
        if not row or row.get("user_id") != key or row.get("notebook_id") != notebook_id:
            return False
        data["sessions"].pop(session_id, None)
        data["messages"].pop(session_id, None)
        _save(data)
        return True


def list_messages(user_id: str | None, notebook_id: str, session_id: str) -> list[dict[str, Any]]:
    session = get_session(user_id, notebook_id, session_id)
    if not session:
        return []
    if STORE:
        return STORE.list_chat_messages(session_id)
    with _LOCK:
        return list(_load()["messages"].get(session_id, []))


def append_message(user_id: str | None, notebook_id: str, session_id: str, role: str, content: str, model: str | None = None, sources: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    session = get_session(user_id, notebook_id, session_id)
    if not session:
        return None
    clean = content.strip()
    if not clean:
        return None
    record = {"id": "msg_" + uuid.uuid4().hex[:12], "session_id": session_id, "role": role, "content": clean, "model": model, "sources": sources or [], "created": _now()}
    if STORE:
        STORE.append_chat_message(record)
        STORE.touch_chat_session(session_id, record["created"], title=None if role != "user" else _derive_session_title(clean))
        return record
    with _LOCK:
        data = _load()
        data["messages"].setdefault(session_id, []).append(record)
        row = data["sessions"].get(session_id)
        if row:
            row["updated"] = record["created"]
            if role == "user" and row.get("title") in {"New chat", "Untitled chat"}:
                row["title"] = _derive_session_title(clean)
        _save(data)
    return record


def _derive_session_title(text: str) -> str:
    one_line = re.sub(r"\\s+", " ", text).strip()
    return (one_line[:72].rstrip() or "New chat")


def _note_record(user_id: str | None, notebook_id: str, title: str, content: str, source_type: str, source_ref: str | None) -> dict[str, Any]:
    now = _now()
    return {"id": "note_" + uuid.uuid4().hex[:12], "notebook_id": notebook_id, "user_id": _user_key(user_id), "title": (title.strip() or "Untitled note")[:160], "content": content.strip(), "source_type": source_type, "source_ref": source_ref, "created": now, "updated": now}


def list_notes(user_id: str | None, notebook_id: str) -> list[dict[str, Any]]:
    key = _user_key(user_id)
    if STORE:
        return STORE.list_notes(key, notebook_id)
    with _LOCK:
        rows = [row for row in _load()["notes"].values() if row.get("user_id") == key and row.get("notebook_id") == notebook_id]
        rows.sort(key=lambda row: row.get("updated", ""), reverse=True)
        return rows


def create_note(user_id: str | None, notebook_id: str, title: str, content: str, source_type: str = "manual", source_ref: str | None = None) -> dict[str, Any]:
    record = _note_record(user_id, notebook_id, title, content, source_type, source_ref)
    if not record["content"]:
        raise ValueError("Note content cannot be empty")
    if STORE:
        return STORE.create_note(record)
    with _LOCK:
        data = _load()
        data["notes"][record["id"]] = record
        _save(data)
    return record


def update_note(user_id: str | None, notebook_id: str, note_id: str, title: str, content: str) -> dict[str, Any] | None:
    key = _user_key(user_id)
    clean_content = content.strip()
    if not clean_content:
        raise ValueError("Note content cannot be empty")
    if STORE:
        return STORE.update_note(key, notebook_id, note_id, title.strip()[:160] or "Untitled note", clean_content, _now())
    with _LOCK:
        data = _load()
        row = data["notes"].get(note_id)
        if not row or row.get("user_id") != key or row.get("notebook_id") != notebook_id:
            return None
        row["title"] = title.strip()[:160] or "Untitled note"
        row["content"] = clean_content
        row["updated"] = _now()
        _save(data)
        return row


def delete_note(user_id: str | None, notebook_id: str, note_id: str) -> bool:
    key = _user_key(user_id)
    if STORE:
        return STORE.delete_note(key, notebook_id, note_id)
    with _LOCK:
        data = _load()
        row = data["notes"].get(note_id)
        if not row or row.get("user_id") != key or row.get("notebook_id") != notebook_id:
            return False
        data["notes"].pop(note_id, None)
        _save(data)
        return True
