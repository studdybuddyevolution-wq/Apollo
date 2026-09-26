import base64
import json
from typing import Any

from storage import STORE
from workspace_service import _LOCK, _load, _user_key, get_session


def encode_cursor(updated: str, item_id: str) -> str:
    payload = json.dumps({"updated": updated, "id": item_id}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_cursor(cursor: str | None) -> tuple[str, str] | None:
    if not cursor:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        updated = str(payload["updated"])
        item_id = str(payload["id"])
        return (updated, item_id) if updated and item_id else None
    except (ValueError, KeyError, TypeError):
        return None


def _session_item(row: tuple[Any, ...]) -> dict[str, Any]:
    keys = ("id", "notebook_id", "user_id", "title", "created", "updated", "socratic_state_json", "message_count")
    item = dict(zip(keys, row))
    try:
        item["socratic_state"] = json.loads(item.pop("socratic_state_json") or "null")
    except Exception:
        item.pop("socratic_state_json", None)
        item["socratic_state"] = None
    item["message_count"] = int(item.get("message_count") or 0)
    return item


def list_sessions_page(
    user_id: str | None,
    *,
    limit: int = 30,
    cursor: str | None = None,
    search: str | None = None,
    notebook_id: str | None = None,
    kind: str = "all",
) -> dict[str, Any]:
    key = _user_key(user_id)
    safe_limit = max(1, min(int(limit), 100))
    decoded = decode_cursor(cursor)

    if STORE:
        clauses = ["s.user_id=%s"]
        params: list[Any] = [key]
        if notebook_id:
            clauses.append("s.notebook_id=%s")
            params.append(notebook_id)
        if kind == "socratic":
            clauses.append("s.socratic_state_json IS NOT NULL")
        elif kind == "chat":
            clauses.append("s.socratic_state_json IS NULL")
        if search and search.strip():
            needle = "%" + search.strip()[:120] + "%"
            clauses.append("(s.title ILIKE %s OR COALESCE(s.socratic_state_json, '') ILIKE %s)")
            params.extend([needle, needle])
        if decoded:
            cursor_updated, cursor_id = decoded
            clauses.append("(s.updated < %s OR (s.updated=%s AND s.id < %s))")
            params.extend([cursor_updated, cursor_updated, cursor_id])
        where = " AND ".join(clauses)
        with STORE._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT s.id,s.notebook_id,s.user_id,s.title,s.created,s.updated,s.socratic_state_json,COUNT(m.id) AS message_count "
                    "FROM apollo_chat_sessions s LEFT JOIN apollo_chat_messages m ON m.session_id=s.id "
                    "WHERE " + where + " "
                    "GROUP BY s.id,s.notebook_id,s.user_id,s.title,s.created,s.updated,s.socratic_state_json "
                    "ORDER BY s.updated DESC,s.id DESC LIMIT %s",
                    tuple(params + [safe_limit + 1]),
                )
                rows = cur.fetchall()
        has_more = len(rows) > safe_limit
        sessions = [_session_item(row) for row in rows[:safe_limit]]
    else:
        with _LOCK:
            data = _load()
            needle = (search or "").strip().lower()
            rows = []
            for row in data["sessions"].values():
                if row.get("user_id") != key:
                    continue
                if notebook_id and row.get("notebook_id") != notebook_id:
                    continue
                has_socratic = bool(row.get("socratic_state"))
                if kind == "socratic" and not has_socratic:
                    continue
                if kind == "chat" and has_socratic:
                    continue
                haystack = " ".join(
                    [str(row.get("title") or ""), str((row.get("socratic_state") or {}).get("topic") or "")]
                ).lower()
                if needle and needle not in haystack:
                    continue
                if decoded:
                    cursor_updated, cursor_id = decoded
                    updated = str(row.get("updated") or "")
                    if not (
                        updated < cursor_updated
                        or (updated == cursor_updated and str(row.get("id")) < cursor_id)
                    ):
                        continue
                item = dict(row)
                item.setdefault("socratic_state", None)
                item["message_count"] = len(data["messages"].get(item["id"], []))
                rows.append(item)
            rows.sort(
                key=lambda item: (
                    str(item.get("updated") or ""),
                    str(item.get("id") or ""),
                ),
                reverse=True,
            )
        has_more = len(rows) > safe_limit
        sessions = rows[:safe_limit]

    next_cursor = None
    if has_more and sessions:
        next_cursor = encode_cursor(
            str(sessions[-1].get("updated") or ""),
            str(sessions[-1]["id"]),
        )
    return {
        "sessions": sessions,
        "next_cursor": next_cursor,
        "has_more": has_more,
        "limit": safe_limit,
    }


def list_messages_page(
    user_id: str | None,
    notebook_id: str,
    session_id: str,
    *,
    limit: int = 40,
    cursor: str | None = None,
) -> dict[str, Any]:
    if not get_session(user_id, notebook_id, session_id):
        return {"messages": [], "next_cursor": None, "has_more": False, "limit": 0}

    safe_limit = max(1, min(int(limit), 100))
    decoded = decode_cursor(cursor)

    if STORE:
        clauses = ["m.session_id=%s"]
        params: list[Any] = [session_id]
        if decoded:
            cursor_created, cursor_id = decoded
            clauses.append("(m.created < %s OR (m.created=%s AND m.id < %s))")
            params.extend([cursor_created, cursor_created, cursor_id])
        with STORE._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT m.id,m.session_id,m.role,m.content,m.model,m.sources_json,m.created "
                    "FROM apollo_chat_messages m WHERE " + " AND ".join(clauses) + " "
                    "ORDER BY m.created DESC,m.id DESC LIMIT %s",
                    tuple(params + [safe_limit + 1]),
                )
                rows = cur.fetchall()
        has_more = len(rows) > safe_limit
        selected = rows[:safe_limit]
        messages = []
        for row in reversed(selected):
            try:
                sources = json.loads(row[5] or "[]")
            except Exception:
                sources = []
            messages.append({
                "id": row[0],
                "session_id": row[1],
                "role": row[2],
                "content": row[3],
                "model": row[4],
                "sources": sources,
                "created": row[6],
            })
        oldest = selected[-1] if selected else None
        next_cursor = (
            encode_cursor(str(oldest[6]), str(oldest[0]))
            if has_more and oldest
            else None
        )
    else:
        with _LOCK:
            rows = list(_load()["messages"].get(session_id, []))
        rows.sort(
            key=lambda item: (
                str(item.get("created") or ""),
                str(item.get("id") or ""),
            ),
            reverse=True,
        )
        if decoded:
            cursor_created, cursor_id = decoded
            rows = [
                item
                for item in rows
                if str(item.get("created") or "") < cursor_created
                or (
                    str(item.get("created") or "") == cursor_created
                    and str(item.get("id")) < cursor_id
                )
            ]
        has_more = len(rows) > safe_limit
        selected = rows[:safe_limit]
        messages = list(reversed(selected))
        oldest = selected[-1] if selected else None
        next_cursor = (
            encode_cursor(
                str(oldest.get("created") or ""),
                str(oldest.get("id")),
            )
            if has_more and oldest
            else None
        )

    return {
        "messages": messages,
        "next_cursor": next_cursor,
        "has_more": has_more,
        "limit": safe_limit,
    }
