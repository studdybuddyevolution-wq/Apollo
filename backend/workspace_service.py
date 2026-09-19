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


def _ensure_workspace_schema() -> None:
    if not STORE:
        return
    migration_path = Path(__file__).resolve().parent / "migrations" / "002_knowledge_workspace.sql"
    if not migration_path.exists():
        return
    try:
        with STORE._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(migration_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[Apollo workspace] schema migration warning: {exc}")


_ensure_workspace_schema()


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


def _pg_session(user_id: str, notebook_id: str, session_id: str | None = None):
    if not STORE:
        return None
    query = "SELECT id,notebook_id,user_id,title,created,updated,socratic_state_json FROM apollo_chat_sessions WHERE user_id=%s AND notebook_id=%s"
    params: list[Any] = [user_id, notebook_id]
    if session_id:
        query += " AND id=%s"
        params.append(session_id)
    query += " LIMIT 1"
    with STORE._connect() as conn:
        with conn.cursor() as cur:
            cur.execute(query, tuple(params))
            row = cur.fetchone()
    if not row:
        return None
    result = dict(zip(("id", "notebook_id", "user_id", "title", "created", "updated", "socratic_state_json"), row))
    try:
        result["socratic_state"] = json.loads(result.pop("socratic_state_json") or "null")
    except Exception:
        result["socratic_state"] = None
    return result


def list_sessions(user_id: str | None, notebook_id: str) -> list[dict[str, Any]]:
    key = _user_key(user_id)
    if STORE:
        with STORE._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id,notebook_id,user_id,title,created,updated,socratic_state_json FROM apollo_chat_sessions WHERE user_id=%s AND notebook_id=%s ORDER BY updated DESC", (key, notebook_id))
                rows = cur.fetchall()
        result = []
        for row in rows:
            item = dict(zip(("id", "notebook_id", "user_id", "title", "created", "updated", "socratic_state_json"), row))
            try:
                item["socratic_state"] = json.loads(item.pop("socratic_state_json") or "null")
            except Exception:
                item["socratic_state"] = None
            result.append(item)
        return result
    with _LOCK:
        data = _load()
        rows = []
        for row in data["sessions"].values():
            if row.get("user_id") != key or row.get("notebook_id") != notebook_id:
                continue
            item = dict(row)
            item.setdefault("socratic_state", None)
            rows.append(item)
        rows.sort(key=lambda row: row.get("updated", ""), reverse=True)
        return rows


def create_session(user_id: str | None, notebook_id: str, title: str = "New chat") -> dict[str, Any]:
    key = _user_key(user_id)
    clean_title = title.strip() or "New chat"
    now = _now()
    record = {"id": "chat_" + uuid.uuid4().hex[:12], "notebook_id": notebook_id, "user_id": key, "title": clean_title[:120], "created": now, "updated": now, "socratic_state": None}
    if STORE:
        with STORE._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO apollo_chat_sessions (id,notebook_id,user_id,title,created,updated) VALUES (%s,%s,%s,%s,%s,%s)", (record["id"], record["notebook_id"], record["user_id"], record["title"], record["created"], record["updated"]))
        return record
    with _LOCK:
        data = _load()
        data["sessions"][record["id"]] = record
        data["messages"][record["id"]] = []
        _save(data)
    return record


def list_all_sessions(user_id: str | None, limit: int = 200) -> list[dict[str, Any]]:
    key = _user_key(user_id)
    safe_limit = max(1, min(int(limit), 500))
    if STORE:
        with STORE._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        s.id,
                        s.notebook_id,
                        s.user_id,
                        s.title,
                        s.created,
                        s.updated,
                        s.socratic_state_json,
                        COUNT(m.id) AS message_count
                    FROM apollo_chat_sessions s
                    LEFT JOIN apollo_chat_messages m ON m.session_id = s.id
                    WHERE s.user_id = %s
                    GROUP BY s.id, s.notebook_id, s.user_id, s.title, s.created, s.updated, s.socratic_state_json
                    ORDER BY s.updated DESC
                    LIMIT %s
                    """,
                    (key, safe_limit),
                )
                rows = cur.fetchall()
        keys = ("id", "notebook_id", "user_id", "title", "created", "updated", "socratic_state_json", "message_count")
        result = []
        for row in rows:
            item = dict(zip(keys, row))
            try:
                item["socratic_state"] = json.loads(item.pop("socratic_state_json") or "null")
            except Exception:
                item["socratic_state"] = None
            item["message_count"] = int(item.get("message_count") or 0)
            result.append(item)
        return result

    with _LOCK:
        data = _load()
        rows = []
        messages = data["messages"]
        for row in data["sessions"].values():
            if row.get("user_id") != key:
                continue
            item = dict(row)
            item.setdefault("socratic_state", None)
            item["message_count"] = len(messages.get(item["id"], []))
            rows.append(item)
        rows.sort(key=lambda row: row.get("updated", ""), reverse=True)
        return rows[:safe_limit]


def get_session(user_id: str | None, notebook_id: str, session_id: str) -> dict[str, Any] | None:
    key = _user_key(user_id)
    if STORE:
        return _pg_session(key, notebook_id, session_id)
    with _LOCK:
        row = _load()["sessions"].get(session_id)
        if row and row.get("user_id") == key and row.get("notebook_id") == notebook_id:
            return row
    return None





def get_socratic_state(user_id: str | None, notebook_id: str, session_id: str) -> dict[str, Any] | None:
    session = get_session(user_id, notebook_id, session_id)
    if not session:
        return None
    return session.get("socratic_state")


def save_socratic_state(user_id: str | None, notebook_id: str, session_id: str, state: dict[str, Any]) -> bool:
    key = _user_key(user_id)
    payload = json.dumps(state, ensure_ascii=False)
    now = _now()
    if STORE:
        with STORE._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE apollo_chat_sessions SET socratic_state_json=%s, updated=%s WHERE user_id=%s AND notebook_id=%s AND id=%s",
                    (payload, now, key, notebook_id, session_id),
                )
                return cur.rowcount > 0
    with _LOCK:
        data = _load()
        row = data["sessions"].get(session_id)
        if not row or row.get("user_id") != key or row.get("notebook_id") != notebook_id:
            return False
        row["socratic_state"] = state
        row["updated"] = now
        _save(data)
        return True

def rename_session(user_id: str | None, notebook_id: str, session_id: str, title: str) -> dict[str, Any] | None:
    clean_title = title.strip() or "New chat"
    key = _user_key(user_id)
    now = _now()
    if STORE:
        with STORE._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE apollo_chat_sessions SET title=%s,updated=%s WHERE user_id=%s AND notebook_id=%s AND id=%s RETURNING id,notebook_id,user_id,title,created,updated", (clean_title[:120], now, key, notebook_id, session_id))
                row = cur.fetchone()
        return dict(zip(("id", "notebook_id", "user_id", "title", "created", "updated"), row)) if row else None
    with _LOCK:
        data = _load()
        row = data["sessions"].get(session_id)
        if not row or row.get("user_id") != key or row.get("notebook_id") != notebook_id:
            return None
        row["title"] = clean_title[:120]
        row["updated"] = now
        _save(data)
        return row


def delete_session(user_id: str | None, notebook_id: str, session_id: str) -> bool:
    key = _user_key(user_id)
    if STORE:
        with STORE._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM apollo_chat_sessions WHERE user_id=%s AND notebook_id=%s AND id=%s", (key, notebook_id, session_id))
                return cur.rowcount > 0
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
    if not get_session(user_id, notebook_id, session_id):
        return []
    if STORE:
        with STORE._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id,session_id,role,content,model,sources_json,created FROM apollo_chat_messages WHERE session_id=%s ORDER BY created,id", (session_id,))
                rows = cur.fetchall()
        messages: list[dict[str, Any]] = []
        for row in rows:
            try:
                sources = json.loads(row[5] or "[]")
            except Exception:
                sources = []
            messages.append({"id": row[0], "session_id": row[1], "role": row[2], "content": row[3], "model": row[4], "sources": sources, "created": row[6]})
        return messages
    with _LOCK:
        return list(_load()["messages"].get(session_id, []))


def append_message(user_id: str | None, notebook_id: str, session_id: str, role: str, content: str, model: str | None = None, sources: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    if not get_session(user_id, notebook_id, session_id):
        return None
    clean = content.strip()
    if not clean:
        return None
    created = _now()
    record = {"id": "msg_" + uuid.uuid4().hex[:12], "session_id": session_id, "role": role, "content": clean, "model": model, "sources": sources or [], "created": created}
    title = _derive_session_title(clean) if role == "user" else None
    key = _user_key(user_id)
    if STORE:
        with STORE._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO apollo_chat_messages (id,session_id,role,content,model,sources_json,created) VALUES (%s,%s,%s,%s,%s,%s,%s)", (record["id"], session_id, role, clean, model, json.dumps(sources or [], ensure_ascii=False), created))
                if title:
                    cur.execute("UPDATE apollo_chat_sessions SET updated=%s,title=CASE WHEN title IN ('New chat','Untitled chat') THEN %s ELSE title END WHERE id=%s AND user_id=%s AND notebook_id=%s", (created, title, session_id, key, notebook_id))
                else:
                    cur.execute("UPDATE apollo_chat_sessions SET updated=%s WHERE id=%s AND user_id=%s AND notebook_id=%s", (created, session_id, key, notebook_id))
        return record
    with _LOCK:
        data = _load()
        data["messages"].setdefault(session_id, []).append(record)
        row = data["sessions"].get(session_id)
        if row:
            row["updated"] = created
            if title and row.get("title") in {"New chat", "Untitled chat"}:
                row["title"] = title
        _save(data)
    return record


def _derive_session_title(text: str) -> str:
    one_line = re.sub(r"\s+", " ", text).strip()
    return (one_line[:72].rstrip() or "New chat")


def list_notes(user_id: str | None, notebook_id: str) -> list[dict[str, Any]]:
    key = _user_key(user_id)
    if STORE:
        with STORE._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id,notebook_id,user_id,title,content,source_type,source_ref,created,updated FROM apollo_notes WHERE user_id=%s AND notebook_id=%s ORDER BY updated DESC", (key, notebook_id))
                rows = cur.fetchall()
        keys = ("id", "notebook_id", "user_id", "title", "content", "source_type", "source_ref", "created", "updated")
        return [dict(zip(keys, row)) for row in rows]
    with _LOCK:
        rows = [row for row in _load()["notes"].values() if row.get("user_id") == key and row.get("notebook_id") == notebook_id]
        rows.sort(key=lambda row: row.get("updated", ""), reverse=True)
        return rows


def create_note(user_id: str | None, notebook_id: str, title: str, content: str, source_type: str = "manual", source_ref: str | None = None) -> dict[str, Any]:
    clean_content = content.strip()
    if not clean_content:
        raise ValueError("Note content cannot be empty")
    now = _now()
    record = {"id": "note_" + uuid.uuid4().hex[:12], "notebook_id": notebook_id, "user_id": _user_key(user_id), "title": (title.strip() or "Untitled note")[:160], "content": clean_content, "source_type": source_type, "source_ref": source_ref, "created": now, "updated": now}
    if STORE:
        with STORE._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO apollo_notes (id,notebook_id,user_id,title,content,source_type,source_ref,created,updated) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", tuple(record.values()))
        return record
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
    now = _now()
    if STORE:
        with STORE._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE apollo_notes SET title=%s,content=%s,updated=%s WHERE user_id=%s AND notebook_id=%s AND id=%s RETURNING id,notebook_id,user_id,title,content,source_type,source_ref,created,updated", ((title.strip() or "Untitled note")[:160], clean_content, now, key, notebook_id, note_id))
                row = cur.fetchone()
        keys = ("id", "notebook_id", "user_id", "title", "content", "source_type", "source_ref", "created", "updated")
        return dict(zip(keys, row)) if row else None
    with _LOCK:
        data = _load()
        row = data["notes"].get(note_id)
        if not row or row.get("user_id") != key or row.get("notebook_id") != notebook_id:
            return None
        row["title"] = (title.strip() or "Untitled note")[:160]
        row["content"] = clean_content
        row["updated"] = now
        _save(data)
        return row


def delete_note(user_id: str | None, notebook_id: str, note_id: str) -> bool:
    key = _user_key(user_id)
    if STORE:
        with STORE._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM apollo_notes WHERE user_id=%s AND notebook_id=%s AND id=%s", (key, notebook_id, note_id))
                return cur.rowcount > 0
    with _LOCK:
        data = _load()
        row = data["notes"].get(note_id)
        if not row or row.get("user_id") != key or row.get("notebook_id") != notebook_id:
            return False
        data["notes"].pop(note_id, None)
        _save(data)
        return True
