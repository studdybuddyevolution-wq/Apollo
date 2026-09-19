"""OpenStudy-inspired academic planning and fall-behind detection for Apollo.

FSRS remains responsible for memory-review intervals. This service handles the
separate question: can the learner cover the unfinished academic backlog before
the next meaningful lecture/exam deadline?
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from storage import STORE

STATUS_NOT_STARTED = "not_started"
STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def _parse(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.UTC)
    except ValueError:
        return None


def _store_required():
    if not STORE:
        raise RuntimeError("Planner persistence requires DATABASE_URL.")
    return STORE


def get_daily_hours(user_id: str, *, default: float = 2.0) -> float:
    store = _store_required()
    with store._connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT daily_hours FROM apollo_study_preferences WHERE user_id=%s", (user_id,))
            row = cur.fetchone()
    return float(row[0]) if row else default


def set_daily_hours(user_id: str, daily_hours: float) -> dict[str, Any]:
    hours = max(0.25, min(float(daily_hours), 16.0))
    now = _now()
    store = _store_required()
    with store._connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO apollo_study_preferences(user_id,daily_hours,updated)
                   VALUES(%s,%s,%s)
                   ON CONFLICT(user_id) DO UPDATE SET daily_hours=EXCLUDED.daily_hours,updated=EXCLUDED.updated""",
                (user_id, hours, now),
            )
    return {"user_id": user_id, "daily_hours": hours, "updated": now}


def create_course(user_id: str, *, code: str, title: str, deadline_at: str | None, priority: int = 3) -> dict[str, Any]:
    clean_code = code.strip().upper()
    clean_title = title.strip()
    if not clean_code or not clean_title:
        raise ValueError("Course code and title are required.")
    if deadline_at and _parse(deadline_at) is None:
        raise ValueError("deadline_at must be an ISO timestamp.")
    now = _now()
    record = {
        "id": "course_" + uuid.uuid4().hex[:12],
        "user_id": user_id,
        "code": clean_code[:16],
        "title": clean_title[:160],
        "deadline_at": deadline_at,
        "priority": max(1, min(int(priority), 5)),
        "created": now,
        "updated": now,
    }
    store = _store_required()
    with store._connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO apollo_courses(id,user_id,code,title,deadline_at,priority,created,updated)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
                tuple(record.values()),
            )
    return record


def list_courses(user_id: str) -> list[dict[str, Any]]:
    store = _store_required()
    with store._connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id,user_id,code,title,deadline_at,priority,created,updated
                   FROM apollo_courses WHERE user_id=%s ORDER BY priority DESC, deadline_at NULLS LAST, code""",
                (user_id,),
            )
            rows = cur.fetchall()
    keys = ("id", "user_id", "code", "title", "deadline_at", "priority", "created", "updated")
    return [dict(zip(keys, row)) for row in rows]


def create_topic(
    user_id: str,
    *,
    course_id: str,
    title: str,
    estimated_hours: float = 1.0,
    lecture_at: str | None = None,
) -> dict[str, Any]:
    if lecture_at and _parse(lecture_at) is None:
        raise ValueError("lecture_at must be an ISO timestamp.")
    hours = max(0.1, min(float(estimated_hours), 40.0))
    now = _now()
    clean_title = title.strip()
    if not clean_title:
        raise ValueError("Topic title is required.")
    store = _store_required()
    with store._connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM apollo_courses WHERE id=%s AND user_id=%s", (course_id, user_id))
            if not cur.fetchone():
                raise ValueError("Course not found.")
            record = {
                "id": "topic_" + uuid.uuid4().hex[:12],
                "user_id": user_id,
                "course_id": course_id,
                "title": clean_title[:240],
                "status": STATUS_NOT_STARTED,
                "estimated_hours": hours,
                "lecture_at": lecture_at,
                "completed_at": None,
                "created": now,
                "updated": now,
            }
            cur.execute(
                """INSERT INTO apollo_study_topics
                   (id,user_id,course_id,title,status,estimated_hours,lecture_at,completed_at,created,updated)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                tuple(record.values()),
            )
    return record


def list_topics(user_id: str, course_id: str | None = None) -> list[dict[str, Any]]:
    store = _store_required()
    query = """SELECT t.id,t.user_id,t.course_id,t.title,t.status,t.estimated_hours,
                      t.lecture_at,t.completed_at,t.created,t.updated
               FROM apollo_study_topics t
               JOIN apollo_courses c ON c.id=t.course_id
               WHERE t.user_id=%s"""
    params: list[Any] = [user_id]
    if course_id:
        query += " AND t.course_id=%s"
        params.append(course_id)
    query += " ORDER BY COALESCE(t.lecture_at,'9999-12-31T23:59:59+00:00'), t.title"
    with store._connect() as conn:
        with conn.cursor() as cur:
            cur.execute(query, tuple(params))
            rows = cur.fetchall()
    keys = ("id", "user_id", "course_id", "title", "status", "estimated_hours", "lecture_at", "completed_at", "created", "updated")
    return [dict(zip(keys, row)) for row in rows]


def set_topic_status(user_id: str, topic_id: str, status: str) -> dict[str, Any]:
    if status not in {STATUS_NOT_STARTED, STATUS_IN_PROGRESS, STATUS_COMPLETED}:
        raise ValueError("Unsupported study topic status.")
    now = _now()
    completed = now if status == STATUS_COMPLETED else None
    store = _store_required()
    with store._connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE apollo_study_topics
                   SET status=%s,completed_at=%s,updated=%s
                   WHERE id=%s AND user_id=%s
                   RETURNING id,user_id,course_id,title,status,estimated_hours,lecture_at,completed_at,created,updated""",
                (status, completed, now, topic_id, user_id),
            )
            row = cur.fetchone()
    if not row:
        raise ValueError("Study topic not found.")
    keys = ("id", "user_id", "course_id", "title", "status", "estimated_hours", "lecture_at", "completed_at", "created", "updated")
    return dict(zip(keys, row))


def compute_course_risk(
    *,
    course: dict[str, Any],
    topics: list[dict[str, Any]],
    daily_hours: float,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    clock = now or dt.datetime.now(dt.UTC)
    open_topics = [t for t in topics if t.get("status") != STATUS_COMPLETED]
    required_hours = sum(float(t.get("estimated_hours") or 0.0) for t in open_topics)
    targets = [
        value
        for value in [_parse(course.get("deadline_at")), *[_parse(t.get("lecture_at")) for t in open_topics]]
        if value and value >= clock
    ]
    deadline = min(targets) if targets else None
    days = max((deadline - clock).total_seconds() / 86400.0, 0.0) if deadline else None
    available_hours = (days * max(daily_hours, 0.0)) if days is not None else float("inf")
    utilization = required_hours / max(available_hours, 0.25) if deadline else 0.0

    if deadline and required_hours > available_hours * 1.25:
        severity = "critical"
    elif deadline and (required_hours > available_hours or (days is not None and days <= 2 and required_hours > daily_hours)):
        severity = "warn"
    else:
        severity = "ok"

    topic_priority = sorted(
        open_topics,
        key=lambda t: (
            _parse(t.get("lecture_at")) or dt.datetime.max.replace(tzinfo=dt.UTC),
            -float(t.get("estimated_hours") or 0.0),
        ),
    )
    return {
        "course_id": course["id"],
        "course_code": course["code"],
        "title": course["title"],
        "severity": severity,
        "required_hours": round(required_hours, 2),
        "available_hours": None if deadline is None else round(available_hours, 2),
        "days_until_target": None if days is None else round(days, 2),
        "target_at": deadline.isoformat() if deadline else None,
        "backlog_topics": [
            {
                "id": t["id"],
                "title": t["title"],
                "estimated_hours": float(t["estimated_hours"]),
                "lecture_at": t.get("lecture_at"),
            }
            for t in topic_priority
        ],
        "utilization": round(utilization, 2),
        "priority": int(course.get("priority") or 3),
    }


def get_fall_behind(user_id: str) -> list[dict[str, Any]]:
    courses = list_courses(user_id)
    topics = list_topics(user_id)
    daily_hours = get_daily_hours(user_id)
    by_course: dict[str, list[dict[str, Any]]] = {}
    for topic in topics:
        by_course.setdefault(topic["course_id"], []).append(topic)
    rows = [
        compute_course_risk(
            course=course,
            topics=by_course.get(course["id"], []),
            daily_hours=daily_hours,
        )
        for course in courses
    ]
    severity_rank = {"critical": 3, "warn": 2, "ok": 1}
    rows.sort(key=lambda row: (-severity_rank[row["severity"]], -float(row["utilization"]), -row["priority"], row["course_code"]))
    return rows


def dashboard(user_id: str) -> dict[str, Any]:
    courses = list_courses(user_id)
    topics = list_topics(user_id)
    risk = get_fall_behind(user_id)
    completed = sum(1 for topic in topics if topic["status"] == STATUS_COMPLETED)
    total_hours = sum(float(topic["estimated_hours"] or 0) for topic in topics)
    remaining_hours = sum(float(topic["estimated_hours"] or 0) for topic in topics if topic["status"] != STATUS_COMPLETED)
    return {
        "daily_hours": get_daily_hours(user_id),
        "courses": courses,
        "topics": topics,
        "fall_behind": risk,
        "progress": {
            "topics_total": len(topics),
            "topics_completed": completed,
            "completion_ratio": round(completed / len(topics), 3) if topics else 0.0,
            "hours_total": round(total_hours, 2),
            "hours_remaining": round(remaining_hours, 2),
        },
    }
