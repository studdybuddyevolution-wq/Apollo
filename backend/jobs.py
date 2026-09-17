"""Lightweight in-process job runtime with Postgres persistence."""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from storage import STORE

_TASKS: dict[str, asyncio.Task[Any]] = {}
_MEMORY_JOBS: dict[str, dict[str, Any]] = {}


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def create_job(job_type: str, notebook_id: str | None = None, user_id: str | None = None) -> dict[str, Any]:
    job = {
        "id": "job_" + uuid.uuid4().hex[:12],
        "type": job_type,
        "status": "queued",
        "progress": 0,
        "notebook_id": notebook_id,
        "user_id": user_id,
        "created_at": _now(),
        "started_at": None,
        "completed_at": None,
        "error": None,
        "result_ref": None,
    }
    if STORE:
        STORE.create_job(job)
    else:
        _MEMORY_JOBS[job["id"]] = dict(job)
    return job


def get_job(job_id: str) -> dict[str, Any] | None:
    if STORE:
        return STORE.get_job(job_id)
    return _MEMORY_JOBS.get(job_id)


def update_job(job_id: str, **fields: Any) -> dict[str, Any] | None:
    if STORE:
        return STORE.update_job(job_id, fields)
    job = _MEMORY_JOBS.get(job_id)
    if job is None:
        return None
    job.update(fields)
    return job


async def run_job(job_id: str, worker: Callable[[Callable[[int], None]], Awaitable[Any]]) -> None:
    update_job(job_id, status="processing", progress=1, started_at=_now(), error=None)

    def progress(value: int) -> None:
        update_job(job_id, progress=max(0, min(100, int(value))))

    try:
        result = await worker(progress)
        update_job(
            job_id,
            status="completed",
            progress=100,
            completed_at=_now(),
            result_ref=json.dumps(result, ensure_ascii=False) if result is not None else None,
        )
    except Exception as exc:  # pragma: no cover - background failures are runtime dependent
        update_job(job_id, status="failed", completed_at=_now(), error=str(exc))
    finally:
        _TASKS.pop(job_id, None)


def schedule_job(job_id: str, worker: Callable[[Callable[[int], None]], Awaitable[Any]]) -> str:
    task = asyncio.create_task(run_job(job_id, worker))
    _TASKS[job_id] = task
    return job_id
