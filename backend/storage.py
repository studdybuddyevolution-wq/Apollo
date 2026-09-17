from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any


class PostgresStore:
    """Optional Postgres store for Apollo notebook and source persistence."""

    def __init__(self, url: str):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("psycopg is required when DATABASE_URL is configured") from exc
        self._psycopg = psycopg
        self._url = url
        self._lock = threading.RLock()
        self._connect_timeout = int(os.getenv("APOLLO_DB_CONNECT_TIMEOUT", "5"))
        self.vector_enabled = False
        self._ensure_schema()

    def _connect(self):
        return self._psycopg.connect(self._url, connect_timeout=self._connect_timeout)

    def _ensure_schema(self) -> None:
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS apollo_notebooks (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        title TEXT NOT NULL,
                        created TEXT NOT NULL,
                        updated TEXT NOT NULL,
                        source_count INTEGER NOT NULL DEFAULT 0,
                        node_count INTEGER NOT NULL DEFAULT 0
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS apollo_chunks (
                        id TEXT PRIMARY KEY,
                        notebook_id TEXT NOT NULL REFERENCES apollo_notebooks(id) ON DELETE CASCADE,
                        source TEXT NOT NULL,
                        kind TEXT NOT NULL DEFAULT 'file',
                        text TEXT NOT NULL
                    )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_apollo_notebooks_user ON apollo_notebooks(user_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_apollo_chunks_notebook ON apollo_chunks(notebook_id)")
        self.run_migrations()
        self._migrate_filesystem()

    def run_migrations(self) -> bool:
        migration_path = Path(__file__).resolve().parent / "migrations" / "001_add_chunking_fields.sql"
        if not migration_path.exists():
            return self.vector_enabled
        statements = [statement.strip() for statement in migration_path.read_text(encoding="utf-8").split(";") if statement.strip()]
        for statement in statements:
            try:
                with self._connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(statement)
            except Exception as exc:
                # Vector-specific statements may fail when pgvector is unavailable.
                # Keep the rest of the migration usable and let retrieval fall back to BM25.
                if "vector" not in statement.lower():
                    print(f"[Apollo storage] migration statement failed: {exc}")
                else:
                    print(f"[Apollo storage] pgvector statement skipped: {exc}")
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM pg_extension WHERE extname='vector'")
                    self.vector_enabled = cur.fetchone() is not None
        except Exception:
            self.vector_enabled = False
        return self.vector_enabled

    def _migrate_filesystem(self) -> None:
        data_dir = Path(os.getenv("APOLLO_DATA_DIR", Path(__file__).resolve().parent / "data"))
        manifest_path = data_dir / "notebooks.json"
        if not manifest_path.exists():
            return
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return
        with self._connect() as conn:
            with conn.cursor() as cur:
                for user_id, notebooks in manifest.items():
                    for notebook in notebooks or []:
                        notebook_id = notebook.get("id")
                        if not notebook_id:
                            continue
                        cur.execute("SELECT 1 FROM apollo_notebooks WHERE id=%s", (notebook_id,))
                        if cur.fetchone():
                            continue
                        cur.execute(
                            "INSERT INTO apollo_notebooks (id,user_id,title,created,updated,source_count,node_count) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                            (notebook_id, user_id, notebook.get("title", "Untitled Notebook"), notebook.get("created", ""), notebook.get("updated", ""), int(notebook.get("source_count", 0)), int(notebook.get("node_count", 0))),
                        )
                        chunks_path = data_dir / "notebooks" / notebook_id / "chunks.json"
                        if not chunks_path.exists():
                            continue
                        try:
                            chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
                        except Exception:
                            continue
                        by_source: dict[str, int] = {}
                        for chunk in chunks or []:
                            if not chunk.get("id"):
                                continue
                            source = chunk.get("source", "unknown")
                            index = by_source.get(source, 0)
                            by_source[source] = index + 1
                            cur.execute(
                                "INSERT INTO apollo_chunks (id,notebook_id,source,kind,text,chunk_index,content_type) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",
                                (chunk["id"], notebook_id, source, chunk.get("kind", "file"), chunk.get("text", ""), int(chunk.get("chunk_index", index)), chunk.get("content_type", "plain")),
                            )

    def _connect_row(self, query: str, params: tuple[Any, ...]):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return cur.fetchone()

    def list_notebooks(self, user_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, title, created, updated, source_count, node_count FROM apollo_notebooks WHERE user_id=%s ORDER BY created", (user_id,))
                rows = cur.fetchall()
        keys = ("id", "title", "created", "updated", "source_count", "node_count")
        return [dict(zip(keys, row)) for row in rows]

    def create_notebook(self, record: dict[str, Any], user_id: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO apollo_notebooks (id,user_id,title,created,updated,source_count,node_count) VALUES (%s,%s,%s,%s,%s,%s,%s)", (record["id"], user_id, record["title"], record["created"], record["updated"], record["source_count"], record["node_count"]))

    def get_notebook(self, user_id: str, notebook_id: str) -> dict[str, Any] | None:
        row = self._connect_row("SELECT id, title, created, updated, source_count, node_count FROM apollo_notebooks WHERE user_id=%s AND id=%s", (user_id, notebook_id))
        keys = ("id", "title", "created", "updated", "source_count", "node_count")
        return dict(zip(keys, row)) if row else None

    def rename_notebook(self, user_id: str, notebook_id: str, title: str, updated: str) -> dict[str, Any] | None:
        row = self._connect_row("UPDATE apollo_notebooks SET title=%s, updated=%s WHERE user_id=%s AND id=%s RETURNING id,title,created,updated,source_count,node_count", (title, updated, user_id, notebook_id))
        keys = ("id", "title", "created", "updated", "source_count", "node_count")
        return dict(zip(keys, row)) if row else None

    def delete_notebook(self, user_id: str, notebook_id: str) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM apollo_notebooks WHERE user_id=%s AND id=%s", (user_id, notebook_id))
                return cur.rowcount > 0

    def list_sources(self, notebook_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT source, MIN(kind), COUNT(*) FROM apollo_chunks WHERE notebook_id=%s GROUP BY source ORDER BY source", (notebook_id,))
                rows = cur.fetchall()
        return [{"name": source, "kind": kind, "chunks": count} for source, kind, count in rows]

    def list_sources_with_status(self, notebook_id: str) -> list[dict[str, Any]]:
        sources = {item["name"]: item for item in self.list_sources(notebook_id)}
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT name,kind,processing_status,error_message FROM apollo_sources WHERE notebook_id=%s", (notebook_id,))
                rows = cur.fetchall()
        for name, kind, status, error in rows:
            sources.setdefault(name, {"name": name, "kind": kind, "chunks": 0})
            sources[name].update({"processing_status": status, "error_message": error})
        for item in sources.values():
            item.setdefault("processing_status", "indexed")
            item.setdefault("error_message", None)
        return list(sources.values())

    def replace_source(self, notebook_id: str, filename: str, chunks: list[dict[str, Any]]) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM apollo_chunks WHERE notebook_id=%s AND source=%s", (notebook_id, filename))
                for chunk in chunks:
                    cur.execute(
                        "INSERT INTO apollo_chunks (id,notebook_id,source,kind,text,chunk_index,content_type) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (chunk["id"], notebook_id, chunk["source"], chunk.get("kind", "file"), chunk["text"], int(chunk.get("chunk_index", 0)), chunk.get("content_type", "plain")),
                    )

    def list_chunks(self, notebook_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id,source,kind,text,chunk_index,content_type FROM apollo_chunks WHERE notebook_id=%s ORDER BY source,chunk_index,id", (notebook_id,))
                rows = cur.fetchall()
        return [
            {"id": row[0], "source": row[1], "kind": row[2], "text": row[3], "chunk_index": row[4], "content_type": row[5]}
            for row in rows
        ]

    def delete_source(self, notebook_id: str, filename: str) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM apollo_source_insights WHERE notebook_id=%s AND source_name=%s", (notebook_id, filename))
                cur.execute("DELETE FROM apollo_sources WHERE notebook_id=%s AND name=%s", (notebook_id, filename))
                cur.execute("DELETE FROM apollo_chunks WHERE notebook_id=%s AND source=%s", (notebook_id, filename))
                return cur.rowcount > 0

    def update_counts(self, notebook_id: str, updated: str, source_count: int, node_count: int) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE apollo_notebooks SET updated=%s, source_count=%s, node_count=%s WHERE id=%s", (updated, source_count, node_count, notebook_id))

    def upsert_source_status(self, notebook_id: str, name: str, kind: str, status: str, error_message: str | None = None) -> None:
        now = __import__("datetime").datetime.now().isoformat(timespec="seconds")
        source_id = f"src_{abs(hash(f'{notebook_id}:{name}')):x}"
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO apollo_sources (id,notebook_id,name,kind,processing_status,error_message,created,updated)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (notebook_id,name) DO UPDATE SET kind=EXCLUDED.kind, processing_status=EXCLUDED.processing_status, error_message=EXCLUDED.error_message, updated=EXCLUDED.updated""",
                    (source_id, notebook_id, name, kind, status, error_message, now, now),
                )

    def upsert_chunk_embedding(self, chunk_id: str, embedding: list[float]) -> None:
        if not self.vector_enabled:
            return
        vector = "[" + ",".join(f"{float(value):.10g}" for value in embedding) + "]"
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE apollo_chunks SET embedding=%s::vector WHERE id=%s", (vector, chunk_id))

    def vector_search(self, notebook_id: str, query_embedding: list[float], top_k: int = 20, source_names: list[str] | None = None) -> list[dict[str, Any]]:
        if not self.vector_enabled or not query_embedding:
            return []
        vector = "[" + ",".join(f"{float(value):.10g}" for value in query_embedding) + "]"
        where = ["notebook_id=%s", "embedding IS NOT NULL"]
        params: list[Any] = [vector, notebook_id]
        if source_names:
            where.append("source = ANY(%s)")
            params.append(source_names)
        params.extend([vector, int(top_k)])
        sql = f"""
            SELECT id, source, kind, text, chunk_index, content_type,
                   1 - (embedding <=> %s::vector) AS similarity
            FROM apollo_chunks
            WHERE {' AND '.join(where)}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
        return [
            {"id": row[0], "source": row[1], "kind": row[2], "text": row[3], "chunk_index": row[4], "content_type": row[5], "similarity": float(row[6])}
            for row in rows
        ]

    def create_insight(self, insight: dict[str, Any]) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO apollo_source_insights (id,notebook_id,source_name,insight_type,content,model_used,status,error,created,updated)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (insight["id"], insight["notebook_id"], insight["source_name"], insight["insight_type"], insight["content"], insight.get("model_used"), insight.get("status", "completed"), insight.get("error"), insight["created"], insight["updated"]),
                )

    def list_insights(self, notebook_id: str, source_names: list[str] | None = None) -> list[dict[str, Any]]:
        where = ["notebook_id=%s"]
        params: list[Any] = [notebook_id]
        if source_names:
            where.append("source_name = ANY(%s)")
            params.append(source_names)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT id,notebook_id,source_name,insight_type,content,model_used,status,error,created,updated FROM apollo_source_insights WHERE {' AND '.join(where)} ORDER BY created DESC",
                    tuple(params),
                )
                rows = cur.fetchall()
        keys = ("id", "notebook_id", "source_name", "insight_type", "content", "model_used", "status", "error", "created", "updated")
        return [dict(zip(keys, row)) for row in rows]

    def delete_insights(self, notebook_id: str, source_name: str) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM apollo_source_insights WHERE notebook_id=%s AND source_name=%s", (notebook_id, source_name))
                return cur.rowcount

    def create_job(self, job: dict[str, Any]) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO apollo_jobs (id,type,status,progress,notebook_id,user_id,created_at,started_at,completed_at,error,result_ref)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (job["id"], job["type"], job["status"], job["progress"], job.get("notebook_id"), job.get("user_id"), job["created_at"], job.get("started_at"), job.get("completed_at"), job.get("error"), job.get("result_ref")),
                )

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id,type,status,progress,notebook_id,user_id,created_at,started_at,completed_at,error,result_ref FROM apollo_jobs WHERE id=%s", (job_id,))
                row = cur.fetchone()
        if not row:
            return None
        keys = ("id", "type", "status", "progress", "notebook_id", "user_id", "created_at", "started_at", "completed_at", "error", "result_ref")
        item = dict(zip(keys, row))
        if item.get("result_ref"):
            try:
                item["result"] = json.loads(item["result_ref"])
            except Exception:
                item["result"] = item["result_ref"]
        return item

    def update_job(self, job_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
        if not fields:
            return self.get_job(job_id)
        allowed = {"type", "status", "progress", "notebook_id", "user_id", "created_at", "started_at", "completed_at", "error", "result_ref"}
        safe = {key: value for key, value in fields.items() if key in allowed}
        if not safe:
            return self.get_job(job_id)
        assignments = ", ".join(f"{key}=%s" for key in safe)
        params = list(safe.values()) + [job_id]
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE apollo_jobs SET {assignments} WHERE id=%s", tuple(params))
        return self.get_job(job_id)


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if DATABASE_URL:
    try:
        STORE = PostgresStore(DATABASE_URL)
        print(f"[Apollo storage] PostgreSQL store connected (pgvector={'on' if STORE.vector_enabled else 'off'})")
    except Exception as exc:
        STORE = None
        print(f"[Apollo storage] PostgreSQL unavailable; using filesystem fallback: {exc}")
else:
    STORE = None
    print("[Apollo storage] DATABASE_URL not configured; using filesystem storage")
