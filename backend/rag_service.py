"""Apollo notebook/RAG service with token-aware chunking and hybrid retrieval."""
from __future__ import annotations

import datetime as dt
import io
import json
import math
import os
import re
import shutil
import threading
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from docx import Document as DocxDocument
from pypdf import PdfReader

from chunking import split_text, token_count
from embeddings import embed_text
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


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN_RE.findall(text)]


def _extract_text(filename: str, raw: bytes) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(raw))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
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
    record = {
        "id": "nb_" + uuid.uuid4().hex[:10],
        "title": title,
        "created": now,
        "updated": now,
        "source_count": 0,
        "node_count": 0,
    }
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
            if notebook["id"] == notebook_id:
                notebook["title"] = clean_title or notebook["title"]
                notebook["updated"] = _now()
                _save_manifest(manifest)
                return notebook
    return None


def delete_notebook(user_id: str | None, notebook_id: str) -> bool:
    key = _user_key(user_id)
    if STORE:
        return STORE.delete_notebook(key, notebook_id)
    with _LOCK:
        manifest = _load_manifest()
        notebooks = manifest.get(key, [])
        if not any(nb["id"] == notebook_id for nb in notebooks):
            return False
        manifest[key] = [nb for nb in notebooks if nb["id"] != notebook_id]
        _save_manifest(manifest)
        shutil.rmtree(_notebook_dir(notebook_id), ignore_errors=True)
        return True


def _normalize_chunk(chunk: dict[str, Any], fallback_index: int = 0) -> dict[str, Any]:
    return {
        **chunk,
        "chunk_index": int(chunk.get("chunk_index", fallback_index)),
        "content_type": chunk.get("content_type", "plain"),
        "text": str(chunk.get("text", "")),
    }


def get_notebook_chunks(user_id: str | None, notebook_id: str, source_names: list[str] | None = None) -> list[dict[str, Any]]:
    """Return indexed chunks strictly scoped to one notebook and optional sources."""
    if not get_notebook(user_id, notebook_id):
        return []
    chunks = STORE.list_chunks(notebook_id) if STORE else _load_chunks(notebook_id)
    allowed = set(source_names or [])
    filtered = [
        _normalize_chunk(chunk, index)
        for index, chunk in enumerate(chunks)
        if not allowed or chunk.get("source") in allowed
    ]
    return sorted(filtered, key=lambda item: (str(item.get("source", "")), int(item.get("chunk_index", 0))))


def list_sources(user_id: str | None, notebook_id: str) -> list[dict[str, Any]]:
    if not get_notebook(user_id, notebook_id):
        return []
    if STORE:
        return STORE.list_sources(notebook_id)
    chunks = get_notebook_chunks(user_id, notebook_id)
    grouped: dict[str, dict[str, Any]] = {}
    for chunk in chunks:
        source = chunk["source"]
        grouped.setdefault(source, {"name": source, "kind": chunk.get("kind", "file"), "chunks": 0, "processing_status": "indexed"})
        grouped[source]["chunks"] += 1
    return list(grouped.values())


def list_sources_with_status(user_id: str | None, notebook_id: str) -> list[dict[str, Any]]:
    if not get_notebook(user_id, notebook_id):
        return []
    if STORE:
        return STORE.list_sources_with_status(notebook_id)
    return list_sources(user_id, notebook_id)


def add_source(user_id: str | None, notebook_id: str, filename: str, raw: bytes) -> dict[str, Any]:
    if not get_notebook(user_id, notebook_id):
        raise KeyError("Notebook not found")
    text = _extract_text(filename, raw)
    chunk_records = split_text(text, filename=filename)
    if not chunk_records:
        raise ValueError("No readable text found in source")
    new_chunks = [
        {
            "id": uuid.uuid4().hex,
            "source": filename,
            "kind": "file",
            "text": chunk["text"],
            "chunk_index": chunk["chunk_index"],
            "content_type": chunk["content_type"],
        }
        for chunk in chunk_records
    ]
    if STORE:
        STORE.replace_source(notebook_id, filename, new_chunks)
        STORE.upsert_source_status(notebook_id, filename, "file", "indexed", None)
        STORE.update_counts(notebook_id, _now(), len(STORE.list_sources(notebook_id)), len(STORE.list_chunks(notebook_id)))
        return {"name": filename, "kind": "file", "chunks": len(new_chunks), "characters": len(text), "status": "indexed"}
    with _LOCK:
        existing = [c for c in _load_chunks(notebook_id) if c.get("source") != filename]
        all_chunks = existing + new_chunks
        _save_chunks(notebook_id, all_chunks)
        key = _user_key(user_id)
        manifest = _load_manifest()
        for notebook in manifest.get(key, []):
            if notebook["id"] == notebook_id:
                notebook["updated"] = _now()
                notebook["source_count"] = len(list_sources(user_id, notebook_id))
                notebook["node_count"] = len(all_chunks)
                break
        _save_manifest(manifest)
    return {"name": filename, "kind": "file", "chunks": len(new_chunks), "characters": len(text), "status": "indexed"}


def remove_source(user_id: str | None, notebook_id: str, filename: str) -> bool:
    if not get_notebook(user_id, notebook_id):
        return False
    if STORE:
        removed = STORE.delete_source(notebook_id, filename)
        if removed:
            STORE.update_counts(notebook_id, _now(), len(STORE.list_sources(notebook_id)), len(STORE.list_chunks(notebook_id)))
        return removed
    with _LOCK:
        existing = _load_chunks(notebook_id)
        chunks = [c for c in existing if c.get("source") != filename]
        if len(chunks) == len(existing):
            return False
        _save_chunks(notebook_id, chunks)
    return True


def _bm25_scores(query: str, chunks: list[dict[str, Any]]) -> list[tuple[float, int]]:
    if not chunks:
        return []
    query_terms = _tokens(query)
    if not query_terms:
        return []
    document_terms = [_tokens(chunk.get("text", "")) for chunk in chunks]
    doc_lengths = [len(tokens) for tokens in document_terms]
    avgdl = sum(doc_lengths) / max(1, len(doc_lengths))
    document_frequency: Counter[str] = Counter()
    for terms in document_terms:
        document_frequency.update(set(terms))
    scores: list[tuple[float, int]] = []
    k1 = 1.5
    b = 0.75
    n_docs = len(chunks)
    for index, terms in enumerate(document_terms):
        term_counts = Counter(terms)
        dl = doc_lengths[index]
        score = 0.0
        for term in query_terms:
            df = document_frequency.get(term, 0)
            if not df:
                continue
            tf = term_counts.get(term, 0)
            if not tf:
                continue
            idf = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
            denom = tf + k1 * (1 - b + b * dl / max(avgdl, 1.0))
            score += idf * ((tf * (k1 + 1)) / max(denom, 1e-9))
        scores.append((score, index))
    scores.sort(reverse=True)
    return scores


def retrieve_hybrid(
    user_id: str | None,
    notebook_id: str,
    query: str,
    top_k: int = 5,
    source_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    if not get_notebook(user_id, notebook_id):
        return []
    chunks = get_notebook_chunks(user_id, notebook_id, source_names)
    if not chunks:
        return []

    bm25 = _bm25_scores(query, chunks)
    bm25_ranks = {index: rank for rank, (_, index) in enumerate(bm25[: max(top_k * 4, 20)], 1)}
    vector_results: list[dict[str, Any]] = []
    if STORE and getattr(STORE, "vector_enabled", False):
        try:
            query_embedding = embed_text(query)
            vector_results = STORE.vector_search(notebook_id, query_embedding, top_k=max(top_k * 4, 20), source_names=source_names)
        except Exception as exc:
            print(f"[Apollo RAG] vector retrieval unavailable; using BM25 only: {exc}")

    id_to_index = {str(chunk.get("id")): index for index, chunk in enumerate(chunks)}
    vector_ranks: dict[int, int] = {}
    vector_scores: dict[int, float] = {}
    for rank, item in enumerate(vector_results, 1):
        index = id_to_index.get(str(item.get("id")))
        if index is not None:
            vector_ranks[index] = rank
            vector_scores[index] = float(item.get("similarity", 0.0))

    rrf_k = float(os.getenv("APOLLO_RRF_K", "60"))
    bm25_weight = float(os.getenv("APOLLO_RRF_BM25_WEIGHT", "1.0"))
    vector_weight = float(os.getenv("APOLLO_RRF_VECTOR_WEIGHT", "1.0"))
    candidate_indexes = set(bm25_ranks) | set(vector_ranks)
    if not candidate_indexes:
        candidate_indexes = {index for _, index in bm25[:top_k]}

    fused: list[tuple[float, int]] = []
    for index in candidate_indexes:
        score = 0.0
        if index in bm25_ranks:
            score += bm25_weight / (rrf_k + bm25_ranks[index])
        if index in vector_ranks:
            score += vector_weight / (rrf_k + vector_ranks[index])
        fused.append((score, index))
    fused.sort(reverse=True)

    bm25_score_map = {index: score for score, index in bm25}
    results: list[dict[str, Any]] = []
    for rrf_score, index in fused[:top_k]:
        method = "hybrid" if index in bm25_ranks and index in vector_ranks else ("vector" if index in vector_ranks else "bm25")
        results.append(
            {
                "source": chunks[index]["source"],
                "text": chunks[index]["text"],
                "score": float(rrf_score),
                "bm25_score": float(bm25_score_map.get(index, 0.0)),
                "vector_score": float(vector_scores.get(index, 0.0)),
                "rrf_score": float(rrf_score),
                "retrieval_method": method,
                "chunk_index": chunks[index].get("chunk_index", 0),
                "content_type": chunks[index].get("content_type", "plain"),
                "id": chunks[index].get("id"),
            }
        )
    return results


def retrieve(user_id: str | None, notebook_id: str, query: str, top_k: int = 5, source_names: list[str] | None = None) -> list[dict[str, Any]]:
    return retrieve_hybrid(user_id, notebook_id, query, top_k=top_k, source_names=source_names)


def format_context(results: list[dict[str, Any]], max_chars: int = 9000, max_tokens: int | None = None) -> str:
    if not results:
        return ""
    blocks = []
    used_chars = 0
    used_tokens = 0
    for idx, result in enumerate(results, 1):
        block = f"[Source {idx}: {result['source']}]\n{result['text']}"
        block_tokens = token_count(block)
        if blocks and max_tokens is not None and used_tokens + block_tokens > max_tokens:
            break
        if blocks and used_chars + len(block) > max_chars:
            break
        if not blocks and max_tokens is not None and block_tokens > max_tokens:
            words = block.split()
            block = " ".join(words[: max_tokens * 2])
        blocks.append(block)
        used_chars += len(block)
        used_tokens += token_count(block)
    return "\n\n".join(blocks)
