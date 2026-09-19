"""Abuse-resistant sliding-window rate limiting for Apollo.

Inspired by OpenStudy's proxy-aware client IP handling, but keyed by
authenticated user + verified edge IP for expensive operations. Postgres is
used when available so limits survive multiple Render instances; an in-memory
fallback keeps local development usable.
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, Request

from storage import STORE

_LOCK = threading.Lock()
_MEMORY: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def client_ip(request: Request) -> str:
    cf = (request.headers.get("cf-connecting-ip") or "").strip()
    if cf:
        return cf
    xff = (request.headers.get("x-forwarded-for") or "").strip()
    if xff and "," not in xff:
        return xff
    return (request.client.host if request.client else "unknown") or "unknown"


def rate_key(request: Request, user_id: str | None) -> str:
    identity = (user_id or "anonymous").strip() or "anonymous"
    return f"{identity}:{client_ip(request)}"


def _hash_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def check_and_consume(
    request: Request,
    *,
    user_id: str | None,
    bucket: str,
    limit: int,
    window_seconds: int,
) -> tuple[bool, int]:
    key = rate_key(request, user_id)
    now = datetime.now(UTC)
    cutoff = now - timedelta(seconds=window_seconds)

    if STORE:
        hashed = _hash_key(key)
        with STORE._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*), MIN(at) FROM apollo_rate_limit_events WHERE rate_key=%s AND bucket=%s AND at >= %s",
                    (hashed, bucket, cutoff),
                )
                count, oldest = cur.fetchone()
                if int(count or 0) >= limit:
                    retry = max(1, int((oldest + timedelta(seconds=window_seconds) - now).total_seconds()) + 1)
                    return False, retry
                cur.execute(
                    "INSERT INTO apollo_rate_limit_events(rate_key,bucket,at) VALUES(%s,%s,%s)",
                    (hashed, bucket, now),
                )
                return True, 0

    memory_key = (key, bucket)
    now_ts = time.time()
    with _LOCK:
        hits = _MEMORY[memory_key]
        cutoff_ts = now_ts - window_seconds
        while hits and hits[0] < cutoff_ts:
            hits.popleft()
        if len(hits) >= limit:
            retry = max(1, int(hits[0] + window_seconds - now_ts) + 1)
            return False, retry
        hits.append(now_ts)
        return True, 0


def enforce(
    request: Request,
    *,
    user_id: str | None,
    bucket: str,
    limit: int,
    window_seconds: int,
) -> None:
    allowed, retry_after = check_and_consume(
        request,
        user_id=user_id,
        bucket=bucket,
        limit=limit,
        window_seconds=window_seconds,
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded for {bucket}. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )
