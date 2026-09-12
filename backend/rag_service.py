"""Lightweight Apollo notebook/RAG service for the FastAPI backend.

Phase 5 moves notebook state and source retrieval out of Streamlit. The service
uses the same MiniLM embedding model family as the original Apollo app and
FAISS for semantic retrieval. Storage is local to the backend instance for now;
a durable database/object-store layer should be added before multi-user
production persistence is required.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any

import faiss
import numpy as np
from docx import Document as DocxDocument
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer


DATA_DIR = Path(os.getenv("APOLLO_DATA_DIR", Path(__file__).resolve().parent / "data"))
NOTEBOOKS_FILE = DATA_DIR / "notebooks.json"
MODEL_NAME = os.getenv("APOLLO_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

_LOCK = threading.RLock()
_MODEL: SentenceTransformer | None = None


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _load_manifest() -> dict[str, list[dict[str, Any]]]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not NOTEBOOKS_FILE.exists():
        return {}
    try:
        return json.loads(NOTEBOOKS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_manifest(manifest: dict[str, list[dict[str, Any]]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    NOTEBOOKS_FILE.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _user_key(user_id: str | None) -> str:
    return (user_id or "default").strip() or "default"


def _notebook_dir(notebook_id: str) -> Path:
    return DATA_DIR / "notebooks" / notebook_id


def _index_path(notebook_id: str) -> Path:
    return _notebook_dir(notebook_id) / "index.faiss"


def _metadata_path(notebook_id: str) -> Path:
    return _notebook_dir(notebook_id) / "chunks.json"


def _get_model() -> SentenceTransformer:
    global _MODEL
    with _LOCK:
        if _MODEL is None:
            _MODEL = SentenceTransformer(MODEL_NAME, device="cpu")
        return _MODEL


def _clean_text(text: str) -> str:
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_text(text: str, chunk_size: int = 1200, overlap: int = 180) -> list[str]:
    text = _clean_text(text)
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(length, start + chunk_size)
        if end < length:
            boundary = text.rfind("\n\n", start + chunk_size // 2, end)
            if boundary == -1:
                boundary = text.rfind(". ", start + chunk_size // 2, end)
            if boundary != -1:
                end = boundary + (2 if text[boundary:boundary + 2] == ". " else 0)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= length:
            break
        start = max(0, end - overlap)
    return chunks


def _extract_text(filename: str, raw: bytes) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        reader = PdfReader(raw)
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    if lower.endswith(".docx"):
        # python-docx requires a file-like object.
        import io
        document = DocxDocument(io.BytesIO(raw))
        parts = [paragraph.text for paragraph in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text for cell in row.cells))
        return "\n".join(parts)
    return raw.decode("utf-8", errors="replace")


def _load_chunks(notebook_id: str) -> list[dict[str, Any]]:
    path = _metadata_path(notebook_id)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_chunks(notebook_id: str, chunks: list[dict[str, Any]]) -> None:
    notebook = _notebook_dir(notebook_id)
    notebook.mkdir(parents=True, exist_ok=True)
    _metadata_path(notebook_id).write_text(json.dumps(chunks, indent=2), encoding="utf-8")


def _build_index(notebook_id: str, chunks: list[dict[str, Any]]) -> None:
    notebook = _notebook_dir(notebook_id)
    notebook.mkdir(parents=True, exist_ok=True)
    if not chunks:
        try:
            _index_path(notebook_id).unlink()
        except FileNotFoundError:
            pass
        return
    texts = [chunk["text"] for chunk in chunks]
    embeddings = _get_model().encode(texts, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
    matrix = np.asarray(embeddings, dtype="float32")
    index = faiss.IndexFlatIP(matrix.shape[1])
    index.add(matrix)
    faiss.write_index(index, str(_index_path(notebook_id)))


def list_notebooks(user_id: str | None = None) -> list[dict[str, Any]]:
    key = _user_key(user_id)
    with _LOCK:
        return list(_load_manifest().get(key, []))


def create_notebook(user_id: str | None, title: str) -> dict[str, Any]:
    key = _user_key(user_id)
    title = title.strip() or "Untitled Notebook"
    now = _now()
    record = {
        "id": "nb_" + uuid.uuid4().hex[:10],
        "title": title,
        "created": now,
        "updated": now,
        "source_count": 0,
        "node_count": 0,
    }
    with _LOCK:
        manifest = _load_manifest()
        manifest.setdefault(key, []).append(record)
        _save_manifest(manifest)
    return record


def get_notebook(user_id: str | None, notebook_id: str) -> dict[str, Any] | None:
    return next((nb for nb in list_notebooks(user_id) if nb["id"] == notebook_id), None)


def rename_notebook(user_id: str | None, notebook_id: str, title: str) -> dict[str, Any] | None:
    key = _user_key(user_id)
    with _LOCK:
        manifest = _load_manifest()
        for notebook in manifest.get(key, []):
            if notebook["id"] == notebook_id:
                notebook["title"] = title.strip() or notebook["title"]
                notebook["updated"] = _now()
                _save_manifest(manifest)
                return notebook
    return None


def delete_notebook(user_id: str | None, notebook_id: str) -> bool:
    key = _user_key(user_id)
    with _LOCK:
        manifest = _load_manifest()
        notebooks = manifest.get(key, [])
        if not any(nb["id"] == notebook_id for nb in notebooks):
            return False
        manifest[key] = [nb for nb in notebooks if nb["id"] != notebook_id]
        _save_manifest(manifest)
        shutil.rmtree(_notebook_dir(notebook_id), ignore_errors=True)
        return True


def list_sources(user_id: str | None, notebook_id: str) -> list[dict[str, Any]]:
    notebook = get_notebook(user_id, notebook_id)
    if not notebook:
        return []
    chunks = _load_chunks(notebook_id)
    grouped: dict[str, dict[str, Any]] = {}
    for chunk in chunks:
        source = chunk["source"]
        grouped.setdefault(source, {"name": source, "kind": chunk.get("kind", "file"), "chunks": 0})
        grouped[source]["chunks"] += 1
    return list(grouped.values())


def add_source(user_id: str | None, notebook_id: str, filename: str, raw: bytes) -> dict[str, Any]:
    if not get_notebook(user_id, notebook_id):
        raise KeyError("Notebook not found")
    text = _extract_text(filename, raw)
    chunks = _split_text(text)
    if not chunks:
        raise ValueError("No readable text found in source")

    with _LOCK:
        existing = [c for c in _load_chunks(notebook_id) if c.get("source") != filename]
        new_chunks = existing + [
            {"id": uuid.uuid4().hex, "source": filename, "kind": "file", "text": chunk}
            for chunk in chunks
        ]
        _save_chunks(notebook_id, new_chunks)
        _build_index(notebook_id, new_chunks)

        key = _user_key(user_id)
        manifest = _load_manifest()
        for notebook in manifest.get(key, []):
            if notebook["id"] == notebook_id:
                notebook["updated"] = _now()
                notebook["source_count"] = len(list_sources(user_id, notebook_id))
                notebook["node_count"] = len(new_chunks)
                break
        _save_manifest(manifest)

    return {"name": filename, "kind": "file", "chunks": len(chunks), "characters": len(text)}


def remove_source(user_id: str | None, notebook_id: str, filename: str) -> bool:
    if not get_notebook(user_id, notebook_id):
        return False
    with _LOCK:
        chunks = [c for c in _load_chunks(notebook_id) if c.get("source") != filename]
        if len(chunks) == len(_load_chunks(notebook_id)):
            return False
        _save_chunks(notebook_id, chunks)
        _build_index(notebook_id, chunks)
    return True


def retrieve(user_id: str | None, notebook_id: str, query: str, top_k: int = 5, source_names: list[str] | None = None) -> list[dict[str, Any]]:
    if not get_notebook(user_id, notebook_id):
        return []
    chunks = _load_chunks(notebook_id)
    index_path = _index_path(notebook_id)
    if not chunks or not index_path.exists():
        return []

    index = faiss.read_index(str(index_path))
    query_vec = _get_model().encode([query], normalize_embeddings=True, convert_to_numpy=True)
    scores, ids = index.search(np.asarray(query_vec, dtype="float32"), min(top_k * 3, len(chunks)))
    allowed = set(source_names or [])
    results = []
    for score, idx in zip(scores[0], ids[0]):
        if idx < 0:
            continue
        chunk = chunks[int(idx)]
        if allowed and chunk["source"] not in allowed:
            continue
        results.append({"source": chunk["source"], "text": chunk["text"], "score": float(score)})
        if len(results) >= top_k:
            break
    return results


def format_context(results: list[dict[str, Any]], max_chars: int = 9000) -> str:
    if not results:
        return ""
    blocks = []
    used = 0
    for idx, result in enumerate(results, 1):
        block = f"[Source {idx}: {result['source']}]\n{result['text']}"
        if used + len(block) > max_chars:
            break
        blocks.append(block)
        used += len(block)
    return "\n\n".join(blocks)
