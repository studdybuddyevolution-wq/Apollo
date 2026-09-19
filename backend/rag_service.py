"""Apollo notebook/RAG service with token-aware chunks and hybrid retrieval."""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import math
import os
import re
import shutil
import tempfile
import threading
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from docx import Document as DocxDocument
from pypdf import PdfReader

from chunking import chunk_text, token_count
from embeddings import embed_text_sync
from storage import STORE

DATA_DIR = Path(os.getenv("APOLLO_DATA_DIR", Path(__file__).resolve().parent / "data"))
NOTEBOOKS_FILE = DATA_DIR / "notebooks.json"
_LOCK = threading.RLock()
_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


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


def _metadata_path(notebook_id: str) -> Path:
    return _notebook_dir(notebook_id) / "chunks.json"

def _source_meta_path(notebook_id: str) -> Path:
    return _notebook_dir(notebook_id) / "sources.json"

def _source_payload_path(notebook_id: str, filename: str) -> Path:
    digest = hashlib.sha256(filename.encode("utf-8")).hexdigest()
    return _notebook_dir(notebook_id) / "payloads" / (digest + ".bin")

def sanitize_source_filename(filename: str) -> str:
    """Return a safe source name with no path components or control bytes."""
    raw = str(filename or "").replace("\\", "/").strip()
    safe = os.path.basename(raw)
    if not safe or safe in {".", ".."}:
        raise ValueError("Invalid source filename")
    if "\x00" in safe or any(ord(char) < 32 for char in safe):
        raise ValueError("Invalid source filename")
    return safe


def _source_candidate(filename: str, counter: int) -> str:
    if counter == 0:
        return filename
    path = Path(filename)
    return f"{path.stem} ({counter}){path.suffix}"


def _reserve_filesystem_source_name(notebook_id: str, requested_name: str) -> tuple[str, Path]:
    """Atomically claim a unique local source name for a development fallback."""
    notebook_dir = _notebook_dir(notebook_id)
    claims_dir = notebook_dir / ".claims"
    claims_dir.mkdir(parents=True, exist_ok=True)

    metadata = _load_source_meta(notebook_id)
    chunks = _load_chunks(notebook_id)
    used = set(metadata)
    used.update(str(item.get("source") or "") for item in chunks)

    counter = 0
    while True:
        candidate = _source_candidate(requested_name, counter)
        if candidate in used:
            counter += 1
            continue
        claim_path = claims_dir / (hashlib.sha256(candidate.encode("utf-8")).hexdigest() + ".claim")
        try:
            with claim_path.open("x", encoding="utf-8") as handle:
                handle.write(candidate)
            return candidate, claim_path
        except FileExistsError:
            counter += 1


def reserve_source_name(
    user_id: str | None,
    notebook_id: str,
    filename: str,
    *,
    kind: str = "file",
    source_url: str | None = None,
) -> tuple[str, Path | None]:
    """Reserve a unique source name before a new upload is processed."""
    if not get_notebook(user_id, notebook_id):
        raise KeyError("Notebook not found")
    requested = sanitize_source_filename(filename)
    if STORE:
        return STORE.reserve_source_name(notebook_id, requested, kind, _now(), source_url), None
    with _LOCK:
        return _reserve_filesystem_source_name(notebook_id, requested)


def _load_source_meta(notebook_id: str) -> dict[str, dict[str, Any]]:
    path = _source_meta_path(notebook_id)
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}

def _save_source_meta(notebook_id: str, meta: dict[str, dict[str, Any]]) -> None:
    notebook = _notebook_dir(notebook_id)
    notebook.mkdir(parents=True, exist_ok=True)
    _source_meta_path(notebook_id).write_text(json.dumps(meta, indent=2), encoding="utf-8")

def _save_source_payload_fs(notebook_id: str, filename: str, raw: bytes) -> None:
    path = _source_payload_path(notebook_id, filename)
    root = _notebook_dir(notebook_id).resolve()
    resolved = path.resolve()
    if not (resolved == root or root in resolved.parents):
        raise ValueError("Invalid source payload path")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".payload-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise

def _load_source_payload_fs(notebook_id: str, filename: str) -> bytes | None:
    path = _source_payload_path(notebook_id, filename)
    return path.read_bytes() if path.exists() else None

def _delete_source_payload_fs(notebook_id: str, filename: str) -> None:
    _source_payload_path(notebook_id, filename).unlink(missing_ok=True)


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN_RE.findall(text)]


def _clean_text(text: str) -> str:
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_text(text: str, chunk_size: int = 400, overlap: int = 60) -> list[str]:
    """Backward-compatible wrapper around the token-aware chunker."""
    return [chunk.text for chunk in chunk_text(text, chunk_tokens=chunk_size, overlap_tokens=overlap)]


def _extract_text(filename: str, raw: bytes) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(raw))
        extracted = "\n\n".join((page.extract_text() or "") for page in reader.pages)
        # Selectively render only unreadable/garbled pages through vision.
        # This keeps ordinary PDFs on the cheap text path while rescuing scans
        # and legacy-font documents.
        try:
            from pdf_vision import extract_pdf_text_with_vision
            vision_text, meta = extract_pdf_text_with_vision(raw)
            if meta.get("vision_used") and len(vision_text.strip()) >= len(extracted.strip()):
                return vision_text
        except Exception:
            # PDF indexing should still use any readable native text if the
            # optional vision path is temporarily unavailable.
            pass
        return extracted
    if lower.endswith(".docx"):
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


def list_notebooks(user_id: str | None = None) -> list[dict[str, Any]]:
    key = _user_key(user_id)
    if STORE:
        return STORE.list_notebooks(key)
    with _LOCK:
        return list(_load_manifest().get(key, []))


def create_notebook(user_id: str | None, title: str) -> dict[str, Any]:
    key = _user_key(user_id)
    title = title.strip() or "Untitled Notebook"
    now = _now()
    record = {"id": "nb_" + uuid.uuid4().hex[:10], "title": title, "created": now, "updated": now, "source_count": 0, "node_count": 0}
    if STORE:
        STORE.create_notebook(record, key)
        return record
    with _LOCK:
        manifest = _load_manifest()
        manifest.setdefault(key, []).append(record)
        _save_manifest(manifest)
    return record


def get_notebook(user_id: str | None, notebook_id: str) -> dict[str, Any] | None:
    key = _user_key(user_id)
    if STORE:
        return STORE.get_notebook(key, notebook_id)
    return next((nb for nb in list_notebooks(user_id) if nb["id"] == notebook_id), None)


def rename_notebook(user_id: str | None, notebook_id: str, title: str) -> dict[str, Any] | None:
    key = _user_key(user_id)
    clean_title = title.strip()
    if STORE:
        return STORE.rename_notebook(key, notebook_id, clean_title or "Untitled Notebook", _now())
    with _LOCK:
        manifest = _load_manifest()
        for notebook in manifest.get(key, []):