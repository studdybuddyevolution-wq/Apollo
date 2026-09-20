from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Any

from planner_store import PLANNER_STORE, new_id


MAX_BLOCK_MINUTES = 60
DEFAULT_HORIZON_DAYS = 14


def _date(value: Any) -> dt.date:
    if isinstance(value, dt.date) and not isinstance(value, dt.datetime):
        return value
    return dt.date.fromisoformat(str(value)[:10])


def _time(value: Any) -> dt.time | None:
    if value is None or value == "":
        return None
    if isinstance(value, dt.time):
        return value
    return dt.time.fromisoformat(str(value)[:8])


def _iso_date(value: dt.date) -> str:
    return value.isoformat()


def _iso_time(value: dt.time | None) -> str | None:
    return value.isoformat(timespec="minutes") if value else None


def _weekday_windows(user_id: str) -> dict[int, list[tuple[dt.time, dt.time]]]:
    result: dict[int, list[tuple[dt.time, dt.time]]] = defaultdict(list)
    for row in PLANNER_STORE.list("availability", user_id):
        if not row.get("enabled", True):
            continue
        start, end = _time(row.get("start_time")), _time(row.get("end_time"))
        if start and end and end > start:
            result[int(row["weekday"])].append((start, end))
    for windows in result.values():
        windows.sort()
    return result


def _goal_map(user_id: str) -> dict[str, dict[str, Any]]:
    return {row["id"]: row for row in PLANNER_STORE.list("goals", user_id)}


def _topic_map(user_id: str) -> dict[str, dict[str, Any]]:
    return {row["id"]: row for row in PLANNER_STORE.list("topics", user_id)}


def _existing_blocks(user_id: str, exclude_ids: set[str] | None = None) -> list[dict[str, Any]]:
    excluded = exclude_ids or set()
    return [
        row for row in PLANNER_STORE.list("blocks", user_id)
        if row["id"] not in excluded and row.get("status") != "skipped"
    ]


def _minutes_for_blocks(blocks: list[dict[str, Any]], *, status: str | None = None) -> int:
    return sum(
        int(row.get("actual_minutes") or row.get("duration_minutes") or 0)
        for row in blocks
        if status is None or row.get("status") == status
    )


def _topic_remaining(
    user_id: str,
    topic: dict[str, Any],
    blocks: list[dict[str, Any]],
    today: dt.date,
) -> int:
    topic_id = topic["id"]
    completed = [
        row for row in blocks
        if row.get("topic_id") == topic_id and row.get("status") == "completed"
    ]
    future_planned = [
        row for row in blocks
        if row.get("topic_id") == topic_id
        and row.get("status") == "planned"
        and _date(row["planned_date"]) >= today
    ]
    overdue = [
        row for row in blocks
        if row.get("topic_id") == topic_id
        and row.get("status") == "planned"
        and _date(row["planned_date"]) < today
    ]
    baseline = max(0, int(topic.get("estimated_minutes", 0)))
    completed_minutes = _minutes_for_blocks(completed)
    future_minutes = _minutes_for_blocks(future_planned)
    overdue_minutes = _minutes_for_blocks(overdue)
    remaining = max(0, baseline - completed_minutes - future_minutes)
    return remaining + overdue_minutes


def _is_leaf(topic_id: str, topics: dict[str, dict[str, Any]]) -> bool:
    return not any(row.get("parent_id") == topic_id for row in topics.values())


def _last_completed_date(topic_id: str, blocks: list[dict[str, Any]], today: dt.date) -> dt.date | None:
    dates = [
        _date(row["planned_date"])
        for row in blocks
        if row.get("topic_id") == topic_id and row.get("status") == "completed" and _date(row["planned_date"]) <= today
    ]
    return max(dates) if dates else None


def _candidate_score(
    topic: dict[str, Any],
    goal: dict[str, Any] | None,
    remaining_minutes: int,
    last_completed: dt.date | None,
    today: dt.date,
    exam_date: dt.date | None,
) -> tuple[float, list[str]]:
    reasons: list[str] = []
    deadline_score = 0.5
    if exam_date:
        days = max(0, (exam_date - today).days)
        deadline_score = 5.0 if days <= 2 else 4.0 if days <= 7 else 3.0 if days <= 14 else 1.5
        reasons.append(f"exam/deadline in {days} day{'s' if days != 1 else ''}")
    elif goal:
        reasons.append("goal has no fixed deadline")

    priority = int((goal or {}).get("priority", 3))
    goal_score = float(priority)
    reasons.append(f"goal priority {priority}/5")

    if last_completed is None:
        neglect_score = 4.0
        reasons.append("not studied in the planner yet")
    else:
        days_since = max(0, (today - last_completed).days)
        neglect_score = min(4.0, 1.0 + days_since / 3.0)
        reasons.append(f"last planned completion {days_since} day{'s' if days_since != 1 else ''} ago")

    workload_score = min(3.0, remaining_minutes / 60.0)
    difficulty = int(topic.get("difficulty", 3))
    difficulty_score = difficulty / 2.0
    reasons.append(f"difficulty {difficulty}/5")

    score = (
        deadline_score * 3.0
        + goal_score * 1.8
        + neglect_score * 1.5
        + workload_score
        + difficulty_score
    )
    return score, reasons


def _daily_capacity(
    date: dt.date,
    windows: dict[int, list[tuple[dt.time, dt.time]]],
    blocks: list[dict[str, Any]],
) -> tuple[int, list[tuple[dt.time, dt.time]]]:
    day_windows = windows.get(date.weekday(), [])
    if not day_windows:
        return 0, []

    intervals: list[tuple[dt.time, dt.time]] = []
    floating_minutes = 0
    for block in blocks:
        if _date(block["planned_date"]) != date or block.get("status") not in {"planned", "completed"}:
            continue
        duration = max(0, int(block.get("duration_minutes", 0) or 0))
        start = _time(block.get("start_time"))
        if start:
            end_dt = dt.datetime.combine(date, start) + dt.timedelta(minutes=duration)
            intervals.append((start, end_dt.time()))
        else:
            floating_minutes += duration
    intervals.sort()

    free: list[tuple[dt.time, dt.time]] = []
    for win_start, win_end in day_windows:
        cursor = win_start
        for occ_start, occ_end in intervals:
            if occ_end <= cursor or occ_start >= win_end:
                continue
            if occ_start > cursor:
                free.append((cursor, min(occ_start, win_end)))
            if occ_end > cursor:
                cursor = max(cursor, occ_end)
            if cursor >= win_end:
                break
        if cursor < win_end:
            free.append((cursor, win_end))

    free_minutes = sum(
        max(0, int((dt.datetime.combine(date, end) - dt.datetime.combine(date, start)).total_seconds() // 60))
        for start, end in free
    )
    return max(0, free_minutes - floating_minutes), free


def _allocate_block(
    date: dt.date,
    duration: int,
    free_slots: list[tuple[dt.time, dt.time]],
) -> tuple[dt.time | None, list[tuple[dt.time, dt.time]]]:
    remaining = duration
    slots = list(free_slots)
    for index, (start, end) in enumerate(slots):
        available = int((dt.datetime.combine(date, end) - dt.datetime.combine(date, start)).total_seconds() // 60)
        if available >= remaining:
            start_dt = dt.datetime.combine(date, start)
            next_start = (start_dt + dt.timedelta(minutes=remaining)).time()
            updated = slots[:index] + ([(next_start, end)] if next_start < end else []) + slots[index + 1:]
            return start, updated
    return None, free_slots


def _build_candidates(
    user_id: str,
    goal_ids: list[str],
    today: dt.date,
    blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    goals = _goal_map(user_id)
    topics = _topic_map(user_id)
    selected = set(goal_ids)

    candidates: list[dict[str, Any]] = []
    for topic in topics.values():
        if topic.get("status") == "completed" or not _is_leaf(topic["id"], topics):
            continue
        if selected and topic.get("goal_id") not in selected:
            continue
        goal = goals.get(topic.get("goal_id")) if topic.get("goal_id") else None
        if goal and goal.get("status") != "active":
            continue
        remaining = _topic_remaining(user_id, topic, blocks, today)
        if remaining <= 0:
            continue
        exam_date = None
        if goal and goal.get("exam_date"):
            exam_date = _date(goal["exam_date"])
            if exam_date < today:
                exam_date = today
        last_completed = _last_completed_date(topic["id"], blocks, today)
        score, reasons = _candidate_score(topic, goal, remaining, last_completed, today, exam_date)
        candidates.append({
            "topic": topic,
            "goal": goal,
            "remaining_minutes": remaining,
            "score": score,
            "reasons": reasons,
            "subject": (topic.get("subject") or (goal or {}).get("subject") or "General").strip() or "General",
            "exam_date": exam_date,
        })
    return candidates


def generate_proposal(
    user_id: str,
    *,
    goal_ids: list[str] | None = None,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    start_date: dt.date | None = None,
    notebook_id: str | None = None,
    exclude_block_ids: set[str] | None = None,
    replan: bool = False,
) -> dict[str, Any]:
    today = start_date or dt.date.today()
    horizon_end = today + dt.timedelta(days=max(1, horizon_days) - 1)
    goals = _goal_map(user_id)
    selected_ids = list(goal_ids or [])
    if selected_ids:
        missing = [gid for gid in selected_ids if gid not in goals]
        if missing:
            raise ValueError("One or more study goals were not found")
    windows = _weekday_windows(user_id)
    excluded = exclude_block_ids or set()
    existing_blocks = _existing_blocks(user_id, excluded)

    candidates = _build_candidates(user_id, selected_ids, today, existing_blocks)
    daily_free: dict[dt.date, list[tuple[dt.time, dt.time]]] = {}
    daily_capacity: dict[dt.date, int] = {}
    for offset in range((horizon_end - today).days + 1):
        date = today + dt.timedelta(days=offset)
        capacity, free_slots = _daily_capacity(date, windows, existing_blocks)
        # Never schedule beyond a goal deadline.
        for gid in selected_ids or [c.get("goal", {}).get("id") for c in candidates if c.get("goal")]:
            goal = goals.get(gid) if gid else None
            if goal and goal.get("exam_date") and date > _date(goal["exam_date"]):
                continue
        daily_capacity[date] = capacity
        daily_free[date] = free_slots

    total_available = sum(daily_capacity.values())
    planned: list[dict[str, Any]] = []
    warnings: list[str] = []
    unscheduled: list[dict[str, Any]] = []
    remaining = {item["topic"]["id"]: int(item["remaining_minutes"]) for item in candidates}
    ordered_candidates = list(candidates)
    previous_subject = None

    while ordered_candidates and any(remaining.get(item["topic"]["id"], 0) > 0 for item in ordered_candidates):
        active = [item for item in ordered_candidates if remaining[item["topic"]["id"]] > 0]
        if not active:
            break
        active.sort(key=lambda item: (-item["score"], item["topic"].get("title", "").lower()))
        chosen = active[0]
        alternatives = [item for item in active if item["subject"] != previous_subject]
        if previous_subject and alternatives and chosen["subject"] == previous_subject:
            chosen = sorted(alternatives, key=lambda item: (-item["score"], item["topic"].get("title", "").lower()))[0]
        topic = chosen["topic"]
        goal = chosen["goal"]
        remaining_minutes = remaining[topic["id"]]
        chunk = min(MAX_BLOCK_MINUTES, remaining_minutes)

        placed = False
        for date in sorted(daily_free):
            if remaining[topic["id"]] <= 0:
                break
            if daily_capacity.get(date, 0) < chunk:
                continue
            if goal and goal.get("exam_date") and date > _date(goal["exam_date"]):
                continue
            start_time, updated_slots = _allocate_block(date, chunk, daily_free[date])
            if not start_time:
                continue
            daily_free[date] = updated_slots
            daily_capacity[date] -= chunk
            reason = "; ".join(chosen["reasons"])
            if replan:
                reason = "Replanned because remaining capacity/work has shifted; " + reason
            proposed = {
                "id": new_id("proposal"),
                "title": topic["title"],
                "planned_date": _iso_date(date),
                "start_time": _iso_time(start_time),
                "duration_minutes": chunk,
                "goal_id": topic.get("goal_id"),
                "topic_id": topic["id"],
                "priority": int((goal or {}).get("priority", 3)),
                "generated_by": "replanned" if replan else "generated",
                "locked": False,
                "notebook_id": notebook_id,
                "source_id": None,
                "session_id": None,
                "actual_minutes": None,
                "reason": reason,
                "score": round(chosen["score"], 2),
                "capacity_remaining_after": daily_capacity[date],
            }
            planned.append(proposed)
            remaining[topic["id"]] -= chunk
            previous_subject = chosen["subject"]
            placed = True
            break
        if not placed:
            # If no slot is available, mark the rest as unscheduled and drop this
            # candidate from the active loop so the scheduler can report all gaps.
            unscheduled.append({
                "topic_id": topic["id"],
                "title": topic["title"],
                "goal_id": topic.get("goal_id"),
                "remaining_minutes": remaining[topic["id"]],
                "reason": "No remaining study window fits this workload before its planning horizon/deadline.",
            })
            remaining[topic["id"]] = 0

    if not windows:
        warnings.append("No enabled weekly study windows are configured. Add availability before generating a plan.")
    if unscheduled:
        unscheduled_minutes = sum(int(row["remaining_minutes"]) for row in unscheduled)
        warnings.append(
            f"{unscheduled_minutes // 60}h {unscheduled_minutes % 60}m remains unscheduled because the available windows are full or a deadline is too close."
        )

    deadline_risks = []
    for candidate in candidates:
        rem = sum(int(row["duration_minutes"]) for row in planned if row["topic_id"] == candidate["topic"]["id"])
        if candidate["remaining_minutes"] > rem and candidate.get("exam_date"):
            gap = candidate["remaining_minutes"] - rem
            deadline_risks.append({
                "topic_id": candidate["topic"]["id"],
                "title": candidate["topic"]["title"],
                "exam_date": candidate["exam_date"].isoformat(),
                "unallocated_minutes": gap,
            })
    if deadline_risks:
        warnings.append("Some deadline-bound work remains unallocated; see deadline_risks for the affected topics.")

    total_planned = sum(int(item["duration_minutes"]) for item in planned)
    return {
        "proposal_id": new_id("plan"),
        "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "start_date": _iso_date(today),
        "end_date": _iso_date(horizon_end),
        "blocks": planned,
        "delete_block_ids": [],
        "unscheduled_work": unscheduled,
        "warnings": warnings,
        "deadline_risks": deadline_risks,
        "total_planned_minutes": total_planned,
        "available_capacity_minutes": total_available,
        "conflicts": [],
        "deterministic": True,
    }


def generate_replan_proposal(
    user_id: str,
    *,
    goal_ids: list[str] | None = None,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    start_date: dt.date | None = None,
    notebook_id: str | None = None,
) -> dict[str, Any]:
    today = start_date or dt.date.today()
    selected = set(goal_ids or [])
    removable = {
        row["id"]
        for row in PLANNER_STORE.list("blocks", user_id)
        if row.get("status") == "planned"
        and row.get("generated_by") in {"generated", "replanned"}
        and not row.get("locked")
        and _date(row["planned_date"]) >= today
        and (not selected or row.get("goal_id") in selected)
    }
    proposal = generate_proposal(
        user_id,
        goal_ids=list(selected),
        horizon_days=horizon_days,
        start_date=today,
        notebook_id=notebook_id,
        exclude_block_ids=removable,
        replan=True,
    )
    proposal["delete_block_ids"] = sorted(removable)
    proposal["warnings"].insert(0, f"{len(removable)} future generated block(s) are proposed for replacement; completed/manual/locked blocks are protected.")
    return proposal


def _validate_accepted_blocks(
    user_id: str,
    blocks: list[dict[str, Any]],
    delete_ids: set[str],
) -> None:
    """Validate user-edited proposal blocks before persistence."""
    today = dt.date.today()
    goals = _goal_map(user_id)
    availability = _weekday_windows(user_id)
    existing = [
        row for row in PLANNER_STORE.list("blocks", user_id)
        if row["id"] not in delete_ids and row.get("status") in {"planned", "completed"}
    ]

    occupied: dict[dt.date, list[tuple[dt.datetime, dt.datetime]]] = defaultdict(list)
    daily_minutes: dict[dt.date, int] = defaultdict(int)

    for row in existing:
        planned_date = _date(row["planned_date"])
        duration = max(0, int(row.get("duration_minutes", 0) or 0))
        daily_minutes[planned_date] += duration
        start = _time(row.get("start_time"))
        if start:
            begin = dt.datetime.combine(planned_date, start)
            occupied[planned_date].append((begin, begin + dt.timedelta(minutes=duration)))

    for item in blocks:
        planned_date = _date(item.get("planned_date"))
        if planned_date < today:
            raise ValueError("Accepted plan blocks must be scheduled today or later")
        duration = int(item.get("duration_minutes", 0))
        if duration <= 0:
            raise ValueError("Every proposed block must have a positive duration")

        goal_id = item.get("goal_id")
        goal = goals.get(goal_id) if goal_id else None
        if goal and goal.get("exam_date") and planned_date > _date(goal["exam_date"]):
            raise ValueError(f"Block '{item.get('title') or 'Study'}' is after its goal deadline")

        start = _time(item.get("start_time"))
        if start:
            window_ok = False
            end_dt = dt.datetime.combine(planned_date, start) + dt.timedelta(minutes=duration)
            for win_start, win_end in availability.get(planned_date.weekday(), []):
                if start >= win_start and end_dt.time() <= win_end:
                    window_ok = True
                    break
            if not window_ok:
                raise ValueError(f"Block '{item.get('title') or 'Study'}' is outside an enabled study window")

            for occupied_start, occupied_end in occupied.get(planned_date, []):
                if end_dt > occupied_start and dt.datetime.combine(planned_date, start) < occupied_end:
                    raise ValueError(f"Block '{item.get('title') or 'Study'}' overlaps another accepted block")

            interval = (dt.datetime.combine(planned_date, start), end_dt)
            for other_start, other_end in occupied.get(planned_date, []):
                if interval[1] > other_start and interval[0] < other_end:
                    raise ValueError(f"Block '{item.get('title') or 'Study'}' overlaps another accepted block")
            occupied.setdefault(planned_date, []).append(interval)

        daily_minutes[planned_date] += duration
        capacity = sum(
            int((dt.datetime.combine(planned_date, end) - dt.datetime.combine(planned_date, start)).total_seconds() // 60)
            for start, end in availability.get(planned_date.weekday(), [])
        )
        if daily_minutes[planned_date] > capacity:
            raise ValueError(
                f"Accepted work on {planned_date.isoformat()} exceeds available capacity "
                f"({daily_minutes[planned_date]}m planned vs {capacity}m available)"
            )

def apply_proposal(user_id: str, proposal: dict[str, Any]) -> dict[str, Any]:
    blocks = proposal.get("blocks")
    if not isinstance(blocks, list):
        raise ValueError("Proposal blocks must be a list")
    delete_ids = [str(value) for value in proposal.get("delete_block_ids", []) if value]
    existing = {row["id"]: row for row in PLANNER_STORE.list("blocks", user_id)}
    for block_id in delete_ids:
        row = existing.get(block_id)
        if row and (row.get("status") != "planned" or row.get("generated_by") not in {"generated", "replanned"} or row.get("locked")):
            raise ValueError("Proposal cannot delete completed, manual, skipped, or locked blocks")

    goals = _goal_map(user_id)
    topics = _topic_map(user_id)
    _validate_accepted_blocks(user_id, blocks, set(delete_ids))
    normalized: list[dict[str, Any]] = []
    now = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    for item in blocks:
        topic_id = item.get("topic_id")
        goal_id = item.get("goal_id")
        if topic_id and topic_id not in topics:
            raise ValueError(f"Study topic not found: {topic_id}")
        if goal_id and goal_id not in goals:
            raise ValueError(f"Study goal not found: {goal_id}")
        planned_date = _date(item.get("planned_date"))
        start_time = _time(item.get("start_time"))
        duration = int(item.get("duration_minutes", 0))
        if duration <= 0:
            raise ValueError("Every proposed block must have a positive duration")
        normalized.append({
            "id": new_id("block"),
            "user_id": user_id,
            "goal_id": goal_id,
            "topic_id": topic_id,
            "title": str(item.get("title") or (topics.get(topic_id) or {}).get("title") or "Study"),
            "planned_date": planned_date.isoformat(),
            "start_time": start_time.isoformat() if start_time else None,
            "duration_minutes": duration,
            "status": "planned",
            "priority": max(1, min(5, int(item.get("priority", 3)))),
            "generated_by": str(item.get("generated_by") or "generated"),
            "locked": bool(item.get("locked", False)),
            "notebook_id": item.get("notebook_id"),
            "source_id": item.get("source_id"),
            "session_id": item.get("session_id"),
            "actual_minutes": None,
            "completed_at": None,
            "created_at": now,
            "updated_at": now,
        })
    created = PLANNER_STORE.apply_plan(user_id, delete_ids, normalized)
    return {
        "applied": True,
        "deleted_block_ids": delete_ids,
        "blocks": created,
        "total_planned_minutes": sum(int(item["duration_minutes"]) for item in created),
    }


def build_planner_overview(user_id: str, days: int = 7) -> dict[str, Any]:
    today = dt.date.today()
    end = today + dt.timedelta(days=max(1, days) - 1)
    goals = [row for row in PLANNER_STORE.list("goals", user_id) if row.get("status") == "active"]
    blocks = PLANNER_STORE.list("blocks", user_id)
    window = [row for row in blocks if today <= _date(row["planned_date"]) <= end]
    planned = sum(int(row.get("duration_minutes", 0)) for row in window if row.get("status") != "skipped")
    completed = sum(int(row.get("actual_minutes") or row.get("duration_minutes") or 0) for row in window if row.get("status") == "completed")
    upcoming = [
        goal for goal in goals
        if goal.get("exam_date") and _date(goal["exam_date"]) >= today
    ]
    upcoming.sort(key=lambda row: _date(row["exam_date"]))
    upcoming_goal = upcoming[0] if upcoming else None
    completion = round((completed / planned) * 100, 1) if planned else 0.0
    warnings: list[str] = []
    if upcoming_goal:
        exam = _date(upcoming_goal["exam_date"])
        days_left = max(0, (exam - today).days)
        if days_left <= 7:
            warnings.append(f"{upcoming_goal['title']} is due in {days_left} day{'s' if days_left != 1 else ''}.")
    overdue = [
        row for row in blocks
        if row.get("status") == "planned" and _date(row["planned_date"]) < today
    ]
    if overdue:
        warnings.append(f"{len(overdue)} planned block(s) are overdue and should be replanned or completed.")
    return {
        "today": today.isoformat(),
        "window_end": end.isoformat(),
        "current_goal": upcoming_goal,
        "upcoming_blocks": sorted(window, key=lambda row: (row["planned_date"], row.get("start_time") or "99:99"))[:20],
        "weekly_workload_minutes": planned,
        "weekly_completed_minutes": completed,
        "completion_percentage": completion,
        "deadline_warnings": warnings,
    }
