from __future__ import annotations

import hashlib
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
        self._vector_available = False
        self._ensure_schema()
        migrated = self.run_migrations()
        self._vector_available = self._detect_vector()
        if migrated:
            try:
                self._migrate_filesystem()
            except Exception as exc:
                print(f"[Apollo storage] filesystem migration warning: {exc}")

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

    def run_migrations(self) -> bool:
        """Apply all additive SQL migrations in order; failures degrade gracefully."""
        migration_dir = Path(__file__).resolve().parent / "migrations"
        migrated = False
        for migration_path in sorted(migration_dir.glob("*.sql")):
            try:
                sql = migration_path.read_text(encoding="utf-8")
                with self._connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(sql)
                migrated = True
            except Exception as exc:
                print(f"[Apollo storage] migration warning ({migration_path.name}): {exc}")
        return migrated

    def _detect_vector(self) -> bool:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'vector')")
                    row = cur.fetchone()
            return bool(row and row[0])
        except Exception:
            return False

    def vector_available(self) -> bool:
        return self._vector_available

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
                        cur.execute(
                            "INSERT INTO apollo_notebooks (id,user_id,title,created,updated,source_count,node_count) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",
                            (notebook_id, user_id, notebook.get("title", "Untitled Notebook"), notebook.get("created", ""), notebook.get("updated", ""), int(notebook.get("source_count", 0)), int(notebook.get("node_count", 0))),
                        )
                        notebook_dir = data_dir / "notebooks" / notebook_id
                        chunks_path = notebook_dir / "chunks.json"
                        if chunks_path.exists():
                            try:
                                chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
                            except Exception:
                                chunks = []
                            for index, chunk in enumerate(chunks or []):
                                if not chunk.get("id"):
                                    continue
                                cur.execute(
                                    "INSERT INTO apollo_chunks (id,notebook_id,source,kind,text,chunk_index,content_type) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",
                                    (chunk["id"], notebook_id, chunk.get("source", "unknown"), chunk.get("kind", "file"), chunk.get("text", ""), int(chunk.get("chunk_index", index)), chunk.get("content_type", "plain")),
                                )
                        metadata_path = notebook_dir / "sources.json"
                        if metadata_path.exists():
                            try:
                                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                            except Exception:
                                metadata = {}
                            for source_name, meta in (metadata.items() if isinstance(metadata, dict) else []):
                                kind = str(meta.get("kind") or "file")
                                status = str(meta.get("status") or "indexed")
                                error = meta.get("error")
                                source_url = meta.get("source_url")
                                cur.execute(
                                    "INSERT INTO apollo_sources (id,notebook_id,name,kind,processing_status,error_message,source_url,created,updated) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (notebook_id,name) DO UPDATE SET kind=EXCLUDED.kind, processing_status=EXCLUDED.processing_status, error_message=EXCLUDED.error_message, source_url=EXCLUDED.source_url, updated=EXCLUDED.updated",
                                    (f"src_{notebook_id}_{source_name}", notebook_id, source_name, kind, status, error, source_url, str(meta.get("updated") or ""), str(meta.get("updated") or "")),
                                )
                                digest = hashlib.sha256(source_name.encode("utf-8")).hexdigest()
                                payload_path = notebook_dir / "payloads" / f"{digest}.bin"
                                if payload_path.exists():
                                    cur.execute(
                                        "INSERT INTO apollo_source_payloads(notebook_id,source_name,payload,updated) VALUES (%s,%s,%s,%s) ON CONFLICT (notebook_id,source_name) DO NOTHING",
                                        (notebook_id, source_name, payload_path.read_bytes(), str(meta.get("updated") or "")),
                                    )
                        cur.execute("UPDATE apollo_notebooks SET source_count=(SELECT COUNT(DISTINCT source) FROM apollo_chunks WHERE notebook_id=%s), node_count=(SELECT COUNT(*) FROM apollo_chunks WHERE notebook_id=%s) WHERE id=%s", (notebook_id, notebook_id, notebook_id))

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
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COALESCE(s.name, c.source) AS name,
                           COALESCE(s.kind, c.kind, 'file') AS kind,
                           COALESCE(s.processing_status, 'indexed') AS processing_status,
                           s.error_message,
                           s.source_url,
                           COALESCE(c.chunks, 0) AS chunks
                    FROM (
                      SELECT source, MIN(kind) AS kind, COUNT(*) AS chunks
                      FROM apollo_chunks
                      WHERE notebook_id=%s
                      GROUP BY source
                    ) c
                    FULL OUTER JOIN apollo_sources s
                      ON s.notebook_id=%s AND s.name=c.source
                    WHERE s.notebook_id=%s OR c.source IS NOT NULL
                    ORDER BY name
                """, (notebook_id, notebook_id, notebook_id))
                rows = cur.fetchall()
        return [{"name": n, "kind": k, "status": status, "error": error, "source_url": source_url, "chunks": chunks} for n, k, status, error, source_url, chunks in rows]

    def get_source_metadata(self, notebook_id: str, filename: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT name, kind, processing_status, error_message, source_url FROM apollo_sources WHERE notebook_id=%s AND name=%s",
                    (notebook_id, filename),
                )
                row = cur.fetchone()
        if not row:
            return None
        return {"name": row[0], "kind": row[1], "status": row[2], "error": row[3], "source_url": row[4]}

    def save_source_payload(self, notebook_id: str, filename: str, payload: bytes, updated: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO apollo_source_payloads(notebook_id,source_name,payload,updated)
                    VALUES (%s,%s,%s,%s)
                    ON CONFLICT (notebook_id,source_name) DO UPDATE SET payload=EXCLUDED.payload, updated=EXCLUDED.updated
                    """,
                    (notebook_id, filename, payload, updated),
                )

    def get_source_payload(self, notebook_id: str, filename: str) -> bytes | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT payload FROM apollo_source_payloads WHERE notebook_id=%s AND source_name=%s",
                    (notebook_id, filename),
                )
                row = cur.fetchone()
        return bytes(row[0]) if row and row[0] is not None else None

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
        if self._vector_available:
            query = "SELECT id,source,kind,text,chunk_index,content_type,embedding IS NOT NULL FROM apollo_chunks WHERE notebook_id=%s ORDER BY source,chunk_index,id"
        else:
            query = "SELECT id,source,kind,text,chunk_index,content_type FROM apollo_chunks WHERE notebook_id=%s ORDER BY source,chunk_index,id"
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (notebook_id,))
                rows = cur.fetchall()
        if self._vector_available:
            return [{"id": row[0], "source": row[1], "kind": row[2], "text": row[3], "chunk_index": row[4], "content_type": row[5], "has_embedding": row[6]} for row in rows]
        return [{"id": row[0], "source": row[1], "kind": row[2], "text": row[3], "chunk_index": row[4], "content_type": row[5], "has_embedding": False} for row in rows]

    def list_unembedded_chunks(self, notebook_id: str | None = None, source_name: str | None = None) -> list[dict[str, Any]]:
        if not self._vector_available:
            return []
        clauses = ["embedding IS NULL"]
        params: list[Any] = []
        if notebook_id:
            clauses.append("notebook_id=%s")
            params.append(notebook_id)
        if source_name:
            clauses.append("source=%s")
            params.append(source_name)
        query = "SELECT id,source,text FROM apollo_chunks WHERE " + " AND ".join(clauses) + " ORDER BY notebook_id,source,chunk_index"
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(params))
                rows = cur.fetchall()
        return [{"id": row[0], "source": row[1], "text": row[2]} for row in rows]

    def upsert_chunk_embedding(self, chunk_id: str, embedding: list[float]) -> bool:
        if not self._vector_available or not embedding:
            return False
        vector_literal = "[" + ",".join(f"{float(value):.10g}" for value in embedding) + "]"
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE apollo_chunks SET embedding=%s::vector WHERE id=%s", (vector_literal, chunk_id))
                return cur.rowcount > 0

    def vector_search(self, notebook_id: str, embedding: list[float], top_k: int = 8, source_names: list[str] | None = None) -> list[dict[str, Any]]:
        if not self._vector_available or not embedding:
            return []
        vector_literal = "[" + ",".join(f"{float(value):.10g}" for value in embedding) + "]"
        allowed = [name for name in (source_names or []) if name]
        params: list[Any] = [vector_literal, notebook_id]
        source_clause = ""
        if allowed:
            source_clause = " AND source = ANY(%s)"
            params.append(allowed)
        params.append(max(1, min(int(top_k), 50)))
        query = f"""
            SELECT id,source,text,1 - (embedding <=> %s::vector) AS similarity
            FROM apollo_chunks
            WHERE notebook_id=%s AND embedding IS NOT NULL{source_clause}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        if allowed:
            params = [vector_literal, notebook_id, allowed, vector_literal, params[-1]]
        else:
            params = [vector_literal, notebook_id, vector_literal, params[-1]]
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(params))
                rows = cur.fetchall()
        return [{"id": row[0], "source": row[1], "text": row[2], "vector_score": float(row[3] or 0.0)} for row in rows]

    def delete_source(self, notebook_id: str, filename: str) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM apollo_chunks WHERE notebook_id=%s AND source=%s", (notebook_id, filename))
                deleted = cur.rowcount > 0
                cur.execute("DELETE FROM apollo_sources WHERE notebook_id=%s AND name=%s", (notebook_id, filename))
                cur.execute("DELETE FROM apollo_source_payloads WHERE notebook_id=%s AND source_name=%s", (notebook_id, filename))
                return deleted

    def update_counts(self, notebook_id: str, updated: str, source_count: int, node_count: int) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE apollo_notebooks SET updated=%s, source_count=%s, node_count=%s WHERE id=%s", (updated, source_count, node_count, notebook_id))

    def upsert_source_status(self, notebook_id: str, name: str, kind: str, status: str, error: str | None = None, now: str | None = None, source_url: str | None = None) -> None:
        stamp = now or ""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO apollo_sources (id,notebook_id,name,kind,processing_status,error_message,created,updated)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (notebook_id,name) DO UPDATE SET
                      kind=EXCLUDED.kind,
                      processing_status=EXCLUDED.processing_status,
                      error_message=EXCLUDED.error_message,
                      updated=EXCLUDED.updated
                """, (f"src_{notebook_id}_{name}", notebook_id, name, kind, status, error, stamp, stamp))

    def create_insight(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO apollo_source_insights (id,notebook_id,source_name,insight_type,content,model_used,status,error,created,updated)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (record["id"], record["notebook_id"], record["source_name"], record["insight_type"], record["content"], record.get("model_used"), record.get("status", "completed"), record.get("error"), record["created"], record["updated"]))
        return record

    def list_insights(self, notebook_id: str, source_name: str | None = None, insight_type: str | None = None) -> list[dict[str, Any]]:
        clauses = ["notebook_id=%s"]
        params: list[Any] = [notebook_id]
        if source_name:
            clauses.append("source_name=%s")
            params.append(source_name)
        if insight_type:
            clauses.append("insight_type=%s")
            params.append(insight_type)
        query = "SELECT id,notebook_id,source_name,insight_type,content,model_used,status,error,created,updated FROM apollo_source_insights WHERE " + " AND ".join(clauses) + " ORDER BY created DESC"
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(params))
                rows = cur.fetchall()
        keys = ("id", "notebook_id", "source_name", "insight_type", "content", "model_used", "status", "error", "created", "updated")
        return [dict(zip(keys, row)) for row in rows]

    def delete_insights(self, notebook_id: str, source_name: str | None = None) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                if source_name:
                    cur.execute("DELETE FROM apollo_source_insights WHERE notebook_id=%s AND source_name=%s", (notebook_id, source_name))
                else:
                    cur.execute("DELETE FROM apollo_source_insights WHERE notebook_id=%s", (notebook_id,))
                return cur.rowcount

    def create_job(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO apollo_jobs (id,type,status,progress,notebook_id,user_id,created_at,started_at,completed_at,error,result_ref)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (record["id"], record["type"], record.get("status", "queued"), int(record.get("progress", 0)), record.get("notebook_id"), record.get("user_id"), record["created_at"], record.get("started_at"), record.get("completed_at"), record.get("error"), record.get("result_ref")))
        return record

    def update_job(self, job_id: str, **updates: Any) -> None:
        if not updates:
            return
        allowed = {"status", "progress", "started_at", "completed_at", "error", "result_ref"}
        updates = {k: v for k, v in updates.items() if k in allowed}
        if not updates:
            return
        clause = ", ".join(f"{key}=%s" for key in updates)
        values = list(updates.values()) + [job_id]
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE apollo_jobs SET {clause} WHERE id=%s", tuple(values))

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        row = self._connect_row("SELECT id,type,status,progress,notebook_id,user_id,created_at,started_at,completed_at,error,result_ref FROM apollo_jobs WHERE id=%s", (job_id,))
        keys = ("id", "type", "status", "progress", "notebook_id", "user_id", "created_at", "started_at", "completed_at", "error", "result_ref")
        return dict(zip(keys, row)) if row else None


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if DATABASE_URL:
    try:
        STORE = PostgresStore(DATABASE_URL)
        print(f"[Apollo storage] PostgreSQL store connected (pgvector={STORE.vector_available()})")
    except Exception as exc:
        STORE = None
        print(f"[Apollo storage] PostgreSQL unavailable; using filesystem fallback: {exc}")
else:
    STORE = None
    print("[Apollo storage] DATABASE_URL not configured; using filesystem storage")
