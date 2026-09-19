"""Small in-process job runner for long notebook operations.

The job record is persisted to Postgres when available; execution remains
in-process for now, keeping Apollo simple while preventing long requests from
blocking FastAPI workers.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from embeddings import embed_texts
from error_classifier import is_retryable_source_error
from storage import STORE


@dataclass
class Job:
    id: str
    type: str
    status: str = "queued"
    progress: int = 0
    notebook_id: str | None = None
    user_id: str | None = None
    created_at: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    result_ref: str | None = None


_TASKS: dict[str, asyncio.Task] = {}
_MEMORY_JOBS: dict[str, dict[str, Any]] = {}


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _as_dict(job: Job) -> dict[str, Any]:
    return {
        "id": job.id,
        "type": job.type,
        "status": job.status,
        "progress": job.progress,
        "notebook_id": job.notebook_id,
        "user_id": job.user_id,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "error": job.error,
        "result_ref": job.result_ref,
    }


def get_job(job_id: str) -> dict[str, Any] | None:
    if STORE:
        return STORE.get_job(job_id)
    return _MEMORY_JOBS.get(job_id)


def _save(job: Job) -> None:
    record = _as_dict(job)
    _MEMORY_JOBS[job.id] = record
    if STORE:
        if STORE.get_job(job.id) is None:
            STORE.create_job(record)
        else:
            STORE.update_job(job.id, status=job.status, progress=job.progress, started_at=job.started_at, completed_at=job.completed_at, error=job.error, result_ref=job.result_ref)


async def _embed_job(job: Job, source_name: str | None) -> None:
    if not STORE or not STORE.vector_available():
        job.status = "completed"
        job.progress = 100
        job.completed_at = _now()
        job.result_ref = "bm25-only"
        _save(job)
        return

    chunks = STORE.list_unembedded_chunks(job.notebook_id, source_name)
    total = len(chunks)
    if not total:
        job.status = "completed"
        job.progress = 100
        job.completed_at = _now()
        _save(job)
        return

    job.status = "processing"
    job.started_at = _now()
    _save(job)
    try:
        batch_size = 50
        for start in range(0, total, batch_size):
            batch = chunks[start:start + batch_size]
            for attempt in range(3):
                try:
                    vectors = await embed_texts([item["text"] for item in batch])
                    for item, vector in zip(batch, vectors):
                        STORE.upsert_chunk_embedding(item["id"], vector)
                    break
                except Exception as exc:
                    if attempt >= 2 or not is_retryable_source_error(exc):
                        raise
                    await asyncio.sleep(0.5 * (2 ** attempt))
            job.progress = min(99, int(((start + len(batch)) / total) * 100))
            _save(job)
        job.status = "completed"
        job.progress = 100
        job.completed_at = _now()
        _save(job)
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)[:500]
        job.completed_at = _now()
        _save(job)
        if source_name:
            STORE.upsert_source_status(job.notebook_id or "", source_name, "file", "failed", job.error, now=job.completed_at)
        raise


async def _run(job: Job, runner: Callable[[], Awaitable[None]]) -> None:
    try:
        await runner()
    except Exception:
        # Runner is responsible for detailed state updates when appropriate.
        pass
    finally:
        _TASKS.pop(job.id, None)


async def enqueue_embedding_job(notebook_id: str, user_id: str | None = None, source_name: str | None = None) -> dict[str, Any]:
    job = Job(id="job_" + uuid.uuid4().hex[:12], type="embed_source" if source_name else "embed_notebook", notebook_id=notebook_id, user_id=user_id, created_at=_now())
    _save(job)
    task = asyncio.create_task(_run(job, lambda: _embed_job(job, source_name)))
    _TASKS[job.id] = task
    return _as_dict(job)


async def enqueue_job(job_type: str, notebook_id: str | None = None, user_id: str | None = None, source_name: str | None = None) -> dict[str, Any]:
    if job_type in {"embed_source", "embed_notebook"}:
        return await enqueue_embedding_job(notebook_id or "", user_id, source_name if job_type == "embed_source" else None)
    raise ValueError(f"Unsupported job type: {job_type}")
