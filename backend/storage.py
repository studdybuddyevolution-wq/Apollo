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
        self._migrate_filesystem()

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
                        for chunk in chunks or []:
                            if not chunk.get("id"):
                                continue
                            cur.execute(
                                "INSERT INTO apollo_chunks (id,notebook_id,source,kind,text) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",
                                (chunk["id"], notebook_id, chunk.get("source", "unknown"), chunk.get("kind", "file"), chunk.get("text", "")),
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

    def replace_source(self, notebook_id: str, filename: str, chunks: list[dict[str, Any]]) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM apollo_chunks WHERE notebook_id=%s AND source=%s", (notebook_id, filename))
                for chunk in chunks:
                    cur.execute("INSERT INTO apollo_chunks (id,notebook_id,source,kind,text) VALUES (%s,%s,%s,%s,%s)", (chunk["id"], notebook_id, chunk["source"], chunk.get("kind", "file"), chunk["text"]))

    def list_chunks(self, notebook_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id,source,kind,text FROM apollo_chunks WHERE notebook_id=%s ORDER BY id", (notebook_id,))
                rows = cur.fetchall()
        return [{"id": row[0], "source": row[1], "kind": row[2], "text": row[3]} for row in rows]

    def delete_source(self, notebook_id: str, filename: str) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM apollo_chunks WHERE notebook_id=%s AND source=%s", (notebook_id, filename))
                return cur.rowcount > 0

    def update_counts(self, notebook_id: str, updated: str, source_count: int, node_count: int) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE apollo_notebooks SET updated=%s, source_count=%s, node_count=%s WHERE id=%s", (updated, source_count, node_count, notebook_id))


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if DATABASE_URL:
    try:
        STORE = PostgresStore(DATABASE_URL)
        print("[Apollo storage] PostgreSQL store connected")
    except Exception as exc:
        STORE = None
        print(f"[Apollo storage] PostgreSQL unavailable; using filesystem fallback: {exc}")
else:
    STORE = None
    print("[Apollo storage] DATABASE_URL not configured; using filesystem storage")
