from __future__ import annotations

import datetime as dt
import json
from typing import Any

from storage import STORE
from workspace_service import _LOCK, _load, _user_key
from socratic_engine import list_mastery


def _date_range(days: int) -> tuple[dt.date, dt.date]:
    safe_days = max(7, min(int(days), 365))
    end = dt.datetime.now(dt.UTC).date()
    return end - dt.timedelta(days=safe_days - 1), end


def _streaks_from_days(days: list[dt.date], today: dt.date) -> tuple[int, int]:
    if not days:
        return 0, 0
    unique = sorted(set(days))
    longest = 1
    run = 1
    for index in range(1, len(unique)):
        if unique[index] == unique[index - 1] + dt.timedelta(days=1):
            run += 1
            longest = max(longest, run)
        else:
            run = 1

    day_set = set(unique)
    anchor = today if today in day_set else today - dt.timedelta(days=1)
    current = 0
    cursor = anchor
    while cursor in day_set:
        current += 1
        cursor -= dt.timedelta(days=1)
    return current, longest


def _pg_dashboard(user_id: str, days: int) -> dict[str, Any]:
    start, end = _date_range(days)
    with STORE._connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH active_days AS (
                    SELECT DISTINCT (m.created::timestamp)::date AS study_day
                    FROM apollo_chat_messages m
                    JOIN apollo_chat_sessions s ON s.id=m.session_id
                    WHERE s.user_id=%s
                      AND (m.created::timestamp)::date BETWEEN %s AND %s
                ),
                ranked_days AS (
                    SELECT study_day,
                           ROW_NUMBER() OVER (ORDER BY study_day) AS row_num
                    FROM active_days
                ),
                streak_groups AS (
                    SELECT study_day,
                           study_day - (row_num::int * INTERVAL '1 day') AS group_key
                    FROM ranked_days
                )
                SELECT study_day FROM active_days ORDER BY study_day
                """,
                (user_id, start, end),
            )
            active_day_rows = cur.fetchall()

            cur.execute(
                """
                WITH active_days AS (
                    SELECT DISTINCT (m.created::timestamp)::date AS study_day
                    FROM apollo_chat_messages m
                    JOIN apollo_chat_sessions s ON s.id=m.session_id
                    WHERE s.user_id=%s
                      AND (m.created::timestamp)::date BETWEEN %s AND %s
                ),
                ranked_days AS (
                    SELECT study_day,
                           ROW_NUMBER() OVER (ORDER BY study_day) AS row_num
                    FROM active_days
                ),
                streak_groups AS (
                    SELECT study_day,
                           study_day - (row_num::int * INTERVAL '1 day') AS group_key
                    FROM ranked_days
                ),
                streak_lengths AS (
                    SELECT group_key, COUNT(*) AS length
                    FROM streak_groups
                    GROUP BY group_key
                )
                SELECT COALESCE(MAX(length),0) FROM streak_lengths
                """,
                (user_id, start, end),
            )
            longest_from_sql = int(cur.fetchone()[0] or 0)

            cur.execute(
                """
                SELECT (m.created::timestamp)::date AS study_day,
                       COUNT(*) AS messages,
                       COUNT(DISTINCT m.session_id) AS sessions
                FROM apollo_chat_messages m
                JOIN apollo_chat_sessions s ON s.id=m.session_id
                WHERE s.user_id=%s
                  AND (m.created::timestamp)::date BETWEEN %s AND %s
                GROUP BY study_day
                ORDER BY study_day
                """,
                (user_id, start, end),
            )
            activity_rows = cur.fetchall()

            cur.execute(
                """
                SELECT COUNT(*),
                       COUNT(*) FILTER (WHERE s.socratic_state_json IS NOT NULL)
                FROM apollo_chat_sessions s
                WHERE s.user_id=%s
                  AND (s.updated::timestamp)::date BETWEEN %s AND %s
                """,
                (user_id, start, end),
            )
            session_total, socratic_sessions = cur.fetchone()

            cur.execute(
                """
                SELECT COUNT(*) AS attempts,
                       COALESCE(SUM(correct),0) AS correct,
                       COALESCE(AVG(score),0) AS avg_score,
                       COUNT(*) FILTER (WHERE score >= 75) AS proficient_topics,
                       COUNT(*) FILTER (WHERE score >= 90) AS mastered_topics
                FROM apollo_socratic_mastery
                WHERE user_id=%s
                """,
                (user_id,),
            )
            attempts, correct, avg_score, proficient_topics, mastered_topics = cur.fetchone()

            cur.execute(
                """
                SELECT COUNT(*)
                FROM apollo_chat_messages m
                JOIN apollo_chat_sessions s ON s.id=m.session_id
                WHERE s.user_id=%s
                  AND m.role='assistant'
                  AND (m.created::timestamp)::date BETWEEN %s AND %s
                """,
                (user_id, start, end),
            )
            assistant_messages = int(cur.fetchone()[0] or 0)

    active_dates = [row[0] for row in active_day_rows]
    current_streak, longest_python = _streaks_from_days(active_dates, end)
    longest = max(longest_from_sql, longest_python)
    daily_map = {
        str(day): {"messages": int(messages), "sessions": int(sessions)}
        for day, messages, sessions in activity_rows
    }
    calendar = []
    cursor = start
    while cursor <= end:
        item = daily_map.get(str(cursor), {"messages": 0, "sessions": 0})
        calendar.append({"date": str(cursor), **item})
        cursor += dt.timedelta(days=1)

    attempts = int(attempts or 0)
    correct = int(correct or 0)
    return {
        "window_days": (end - start).days + 1,
        "window_start": str(start),
        "window_end": str(end),
        "streak": {
            "current": current_streak,
            "longest": longest,
            "active_days": len(active_dates),
        },
        "activity": {
            "sessions": int(session_total or 0),
            "socratic_sessions": int(socratic_sessions or 0),
            "messages": sum(item["messages"] for item in calendar),
            "assistant_messages": assistant_messages,
            "calendar": calendar,
        },
        "mastery": {
            "attempts": attempts,
            "correct": correct,
            "accuracy": round(correct / attempts, 3) if attempts else 0.0,
            "average_score": round(float(avg_score or 0), 1),
            "proficient_topics": int(proficient_topics or 0),
            "mastered_topics": int(mastered_topics or 0),
        },
    }


def _filesystem_dashboard(user_id: str, days: int) -> dict[str, Any]:
    start, end = _date_range(days)
    with _LOCK:
        data = _load()
    sessions = [row for row in data["sessions"].values() if row.get("user_id") == user_id]
    messages_by_session = data["messages"]
    daily: dict[dt.date, dict[str, Any]] = {}
    daily_session_ids: dict[dt.date, set[str]] = {}
    total_sessions = 0
    socratic_sessions = 0
    assistant_messages = 0
    for session in sessions:
        updated = str(session.get("updated") or "")[:10]
        try:
            day = dt.date.fromisoformat(updated)
        except ValueError:
            continue
        in_window = start <= day <= end
        if in_window:
            total_sessions += 1
            if session.get("socratic_state"):
                socratic_sessions += 1
        for message in messages_by_session.get(session["id"], []):
            raw_day = str(message.get("created") or "")[:10]
            try:
                msg_day = dt.date.fromisoformat(raw_day)
            except ValueError:
                continue
            if not (start <= msg_day <= end):
                continue
            bucket = daily.setdefault(msg_day, {"messages": 0})
            bucket["messages"] += 1
            daily_session_ids.setdefault(msg_day, set()).add(str(session["id"]))
            if message.get("role") == "assistant":
                assistant_messages += 1

    active_dates = sorted(daily)
    current_streak, longest = _streaks_from_days(active_dates, end)
    mastery_rows = list_mastery(user_id)
    attempts = sum(int(row.get("attempts", 0) or 0) for row in mastery_rows)
    correct = sum(int(row.get("correct", 0) or 0) for row in mastery_rows)
    average_score = (
        sum(float(row.get("score", 0) or 0) for row in mastery_rows) / len(mastery_rows)
        if mastery_rows else 0.0
    )
    proficient_topics = sum(1 for row in mastery_rows if float(row.get("score", 0) or 0) >= 75)
    mastered_topics = sum(1 for row in mastery_rows if float(row.get("score", 0) or 0) >= 90)

    calendar = []
    cursor = start
    while cursor <= end:
        calendar.append({
            "date": str(cursor),
            "messages": daily.get(cursor, {}).get("messages", 0),
            "sessions": len(daily_session_ids.get(cursor, set())),
        })
        cursor += dt.timedelta(days=1)

    return {
        "window_days": (end - start).days + 1,
        "window_start": str(start),
        "window_end": str(end),
        "streak": {"current": current_streak, "longest": longest, "active_days": len(active_dates)},
        "activity": {
            "sessions": total_sessions,
            "socratic_sessions": socratic_sessions,
            "messages": sum(item["messages"] for item in calendar),
            "assistant_messages": assistant_messages,
            "calendar": calendar,
        },
        "mastery": {
            "attempts": attempts,
            "correct": correct,
            "accuracy": round(correct / attempts, 3) if attempts else 0.0,
            "average_score": round(average_score, 1),
            "proficient_topics": proficient_topics,
            "mastered_topics": mastered_topics,
        },
    }


def get_progress_dashboard(user_id: str | None, days: int = 30) -> dict[str, Any]:
    key = _user_key(user_id)
    if STORE:
        return _pg_dashboard(key, days)
    return _filesystem_dashboard(key, days)
