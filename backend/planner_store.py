from __future__ import annotations

import datetime as dt
import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any

from storage import STORE


ENTITY_FIELDS = {
    "goals": ("id", "user_id", "title", "description", "goal_type", "subject", "exam_date", "desired_outcome", "priority", "status", "created_at", "updated_at"),
    "topics": ("id", "user_id", "goal_id", "parent_id", "subject", "title", "description", "estimated_minutes", "difficulty", "status", "sort_order", "created_at", "updated_at"),
    "blocks": ("id", "user_id", "goal_id", "topic_id", "title", "planned_date", "start_time", "duration_minutes", "status", "priority", "generated_by", "locked", "notebook_id", "source_id", "session_id", "actual_minutes", "completed_at", "created_at", "updated_at"),
    "availability": ("id", "user_id", "weekday", "start_time", "end_time", "enabled"),
}


class PlannerStore:
    """Postgres-backed planner store with the existing local filesystem fallback."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        data_dir = Path(os.getenv("APOLLO_DATA_DIR", Path(__file__).resolve().parent / "data"))
        self._path = data_dir / "study_planner.json"
        self._tables = {name: {} for name in ENTITY_FIELDS}
        if not STORE:
            self._load_fs()

    @property
    def using_postgres(self) -> bool:
        return bool(STORE)

    def _load_fs(self) -> None:
        try:
            if self._path.exists():
                data = json.loads(self._path.read_text(encoding="utf-8"))
                for name in self._tables:
                    if isinstance(data.get(name), dict):
                        self._tables[name] = data[name]
        except Exception:
            self._tables = {name: {} for name in ENTITY_FIELDS}

    def _save_fs(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._tables, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def _pg_rows(self, table: str, user_id: str) -> list[dict[str, Any]]:
        fields = ENTITY_FIELDS[table]
        sql = f"SELECT {','.join(fields)} FROM study_{table if table != 'blocks' else 'plan_blocks'} WHERE user_id=%s"
        if table == "goals":
            sql += " ORDER BY exam_date NULLS LAST, priority DESC, created_at DESC"
        elif table == "topics":
            sql += " ORDER BY goal_id NULLS FIRST, parent_id NULLS FIRST, sort_order, title"
        elif table == "blocks":
            sql += " ORDER BY planned_date, start_time NULLS LAST, created_at"
        else:
            sql += " ORDER BY weekday, start_time, id"
        with STORE._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (user_id,))
                rows = cur.fetchall()
        return [self._normalize_row(table, dict(zip(fields, row))) for row in rows]

    def _normalize_row(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        for key in ("created_at", "updated_at", "completed_at"):
            value = row.get(key)
            if isinstance(value, (dt.datetime, dt.date)):
                row[key] = value.isoformat()
        for key in ("exam_date", "planned_date"):
            value = row.get(key)
            if isinstance(value, dt.datetime):
                row[key] = value.date().isoformat()
            elif isinstance(value, dt.date):
                row[key] = value.isoformat()
        for key in ("start_time", "end_time"):
            value = row.get(key)
            if isinstance(value, dt.time):
                row[key] = value.strftime("%H:%M:%S")
        return row

    def list(self, table: str, user_id: str) -> list[dict[str, Any]]:
        if self.using_postgres:
            return self._pg_rows(table, user_id)
        with self._lock:
            self._load_fs()
            rows = [dict(v) for v in self._tables[table].values() if v.get("user_id") == user_id]
        if table == "goals":
            rows.sort(key=lambda r: (r.get("exam_date") or "9999-12-31", -int(r.get("priority", 3)), r.get("created_at", "")))
        elif table == "topics":
            rows.sort(key=lambda r: (r.get("goal_id") or "", r.get("parent_id") or "", int(r.get("sort_order", 0)), r.get("title", "").lower()))
        elif table == "blocks":
            rows.sort(key=lambda r: (r.get("planned_date") or "", r.get("start_time") or "99:99", r.get("created_at", "")))
        else:
            rows.sort(key=lambda r: (int(r.get("weekday", 0)), r.get("start_time", ""), r.get("id", "")))
        return rows

    def get(self, table: str, user_id: str, record_id: str) -> dict[str, Any] | None:
        if self.using_postgres:
            fields = ENTITY_FIELDS[table]
            sql_table = f"study_{'plan_blocks' if table == 'blocks' else table}"
            with STORE._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT {','.join(fields)} FROM {sql_table} WHERE id=%s AND user_id=%s", (record_id, user_id))
                    row = cur.fetchone()
            return self._normalize_row(table, dict(zip(fields, row))) if row else None
        with self._lock:
            self._load_fs()
            row = self._tables[table].get(record_id)
            return dict(row) if row and row.get("user_id") == user_id else None

    def create(self, table: str, record: dict[str, Any]) -> dict[str, Any]:
        if self.using_postgres:
            fields = ENTITY_FIELDS[table]
            sql_table = f"study_{'plan_blocks' if table == 'blocks' else table}"
            values = [record.get(field) for field in fields]
            placeholders = ",".join(["%s"] * len(fields))
            with STORE._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"INSERT INTO {sql_table} ({','.join(fields)}) VALUES ({placeholders})",
                        tuple(values),
                    )
            return self.get(table, record["user_id"], record["id"]) or dict(record)
        with self._lock:
            self._load_fs()
            self._tables[table][record["id"]] = dict(record)
            self._save_fs()
            return dict(record)

    def update(self, table: str, user_id: str, record_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
        if not changes:
            return self.get(table, user_id, record_id)
        if self.using_postgres:
            allowed = [key for key in changes if key in ENTITY_FIELDS[table] and key not in {"id", "user_id", "created_at"}]
            if not allowed:
                return self.get(table, user_id, record_id)
            sql_table = f"study_{'plan_blocks' if table == 'blocks' else table}"
            assignments = ", ".join(f"{key}=%s" for key in allowed)
            values = [changes[key] for key in allowed]
            if "updated_at" in ENTITY_FIELDS[table] and "updated_at" not in changes:
                assignments += ", updated_at=%s"
                values.append(dt.datetime.now(dt.UTC))
            values.extend([record_id, user_id])
            with STORE._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(f"UPDATE {sql_table} SET {assignments} WHERE id=%s AND user_id=%s", tuple(values))
                    if cur.rowcount == 0:
                        return None
            return self.get(table, user_id, record_id)
        with self._lock:
            self._load_fs()
            record = self._tables[table].get(record_id)
            if not record or record.get("user_id") != user_id:
                return None
            record.update(changes)
            if "updated_at" in ENTITY_FIELDS[table]:
                record["updated_at"] = dt.datetime.now(dt.UTC).isoformat()
            self._save_fs()
            return dict(record)

    def delete(self, table: str, user_id: str, record_id: str) -> bool:
        if self.using_postgres:
            sql_table = f"study_{'plan_blocks' if table == 'blocks' else table}"
            with STORE._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(f"DELETE FROM {sql_table} WHERE id=%s AND user_id=%s", (record_id, user_id))
                    return cur.rowcount > 0
        with self._lock:
            self._load_fs()
            row = self._tables[table].get(record_id)
            if not row or row.get("user_id") != user_id:
                return False
            del self._tables[table][record_id]
            self._save_fs()
            return True

    def apply_plan(self, user_id: str, delete_ids: list[str], new_blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self.using_postgres:
            fields = ENTITY_FIELDS["blocks"]
            values = [row for row in new_blocks if row.get("user_id") == user_id]
            with STORE._connect() as conn:
                with conn.cursor() as cur:
                    if delete_ids:
                        cur.execute(
                            "DELETE FROM study_plan_blocks WHERE user_id=%s AND id=ANY(%s) AND status='planned' AND generated_by IN ('generated','replanned') AND locked=FALSE",
                            (user_id, delete_ids),
                        )
                    for row in values:
                        placeholders = ",".join(["%s"] * len(fields))
                        cur.execute(
                            f"INSERT INTO study_plan_blocks ({','.join(fields)}) VALUES ({placeholders})",
                            tuple(row.get(field) for field in fields),
                        )
            return [dict(v) for v in values]
        with self._lock:
            self._load_fs()
            for record_id in delete_ids:
                record = self._tables["blocks"].get(record_id)
                if record and record.get("user_id") == user_id and record.get("status") == "planned" and record.get("generated_by") in {"generated", "replanned"} and not record.get("locked"):
                    del self._tables["blocks"][record_id]
            values = [row for row in new_blocks if row.get("user_id") == user_id]
            for row in values:
                self._tables["blocks"][row["id"]] = dict(row)
            self._save_fs()
            return [dict(v) for v in values]

    def owned_topic(self, user_id: str, topic_id: str) -> dict[str, Any]:
        record = self.get("topics", user_id, topic_id)
        if not record:
            raise KeyError(topic_id)
        return record

    def owned_goal(self, user_id: str, goal_id: str) -> dict[str, Any]:
        record = self.get("goals", user_id, goal_id)
        if not record:
            raise KeyError(goal_id)
        return record

    def owned_block(self, user_id: str, block_id: str) -> dict[str, Any]:
        record = self.get("blocks", user_id, block_id)
        if not record:
            raise KeyError(block_id)
        return record


PLANNER_STORE = PlannerStore()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"
