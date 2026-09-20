from __future__ import annotations

import datetime as dt
import weakref
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from planner_store import PLANNER_STORE, new_id
from workspace_service import create_session, get_session, list_sessions
from rag_service import get_notebook
from storage import STORE


_REGISTERED: weakref.WeakSet[FastAPI] = weakref.WeakSet()


def _user_id(value: str | None) -> str:
    return (value or "default").strip() or "default"


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


class GoalCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4000)
    goal_type: str = Field(default="exam", min_length=1, max_length=40)
    subject: str = Field(default="", max_length=120)
    exam_date: dt.date | None = None
    desired_outcome: str | None = Field(default=None, max_length=1000)
    priority: int = Field(default=3, ge=1, le=5)
    status: str = Field(default="active", pattern="^(active|completed|archived)$")
    user_id: str | None = None


class GoalUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    goal_type: str | None = Field(default=None, min_length=1, max_length=40)
    subject: str | None = Field(default=None, max_length=120)
    exam_date: dt.date | None = None
    desired_outcome: str | None = Field(default=None, max_length=1000)
    priority: int | None = Field(default=None, ge=1, le=5)
    status: str | None = Field(default=None, pattern="^(active|completed|archived)$")
    user_id: str | None = None


class TopicCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    subject: str = Field(default="", max_length=120)
    goal_id: str | None = None
    parent_id: str | None = None
    estimated_minutes: int = Field(default=45, ge=5, le=720)
    difficulty: int = Field(default=3, ge=1, le=5)
    status: str = Field(default="pending", pattern="^(pending|in_progress|completed)$")
    sort_order: int = Field(default=0, ge=0, le=100000)
    user_id: str | None = None


class TopicUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    subject: str | None = Field(default=None, max_length=120)
    goal_id: str | None = None
    parent_id: str | None = None
    estimated_minutes: int | None = Field(default=None, ge=5, le=720)
    difficulty: int | None = Field(default=None, ge=1, le=5)
    status: str | None = Field(default=None, pattern="^(pending|in_progress|completed)$")
    sort_order: int | None = Field(default=None, ge=0, le=100000)
    user_id: str | None = None


class AvailabilityCreate(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start_time: dt.time
    end_time: dt.time
    enabled: bool = True
    user_id: str | None = None


class AvailabilityUpdate(BaseModel):
    weekday: int | None = Field(default=None, ge=0, le=6)
    start_time: dt.time | None = None
    end_time: dt.time | None = None
    enabled: bool | None = None
    user_id: str | None = None


class BlockCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    planned_date: dt.date
    start_time: dt.time | None = None
    duration_minutes: int = Field(ge=5, le=720)
    goal_id: str | None = None
    topic_id: str | None = None
    status: str = Field(default="planned", pattern="^(planned|completed|skipped)$")
    priority: int = Field(default=3, ge=1, le=5)
    generated_by: str = Field(default="manual", pattern="^(manual|generated|replanned)$")
    locked: bool | None = None
    notebook_id: str | None = None
    source_id: str | None = None
    session_id: str | None = None
    actual_minutes: int | None = Field(default=None, ge=0, le=720)
    user_id: str | None = None


class BlockUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    planned_date: dt.date | None = None
    start_time: dt.time | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=720)
    goal_id: str | None = None
    topic_id: str | None = None
    status: str | None = Field(default=None, pattern="^(planned|completed|skipped)$")
    priority: int | None = Field(default=None, ge=1, le=5)
    generated_by: str | None = Field(default=None, pattern="^(manual|generated|replanned)$")
    locked: bool | None = None
    notebook_id: str | None = None
    source_id: str | None = None
    session_id: str | None = None
    actual_minutes: int | None = Field(default=None, ge=0, le=720)
    user_id: str | None = None


class CompleteBlockRequest(BaseModel):
    actual_minutes: int | None = Field(default=None, ge=0, le=720)
    user_id: str | None = None


class MoveBlockRequest(BaseModel):
    planned_date: dt.date
    start_time: dt.time | None = None
    user_id: str | None = None


class ProposalRequest(BaseModel):
    goal_ids: list[str] = Field(default_factory=list)
    horizon_days: int = Field(default=14, ge=1, le=60)
    start_date: dt.date | None = None
    notebook_id: str | None = None
    user_id: str | None = None


class ApplyProposalRequest(BaseModel):
    proposal: dict[str, Any]
    user_id: str | None = None


class ReplanRequest(BaseModel):
    goal_ids: list[str] = Field(default_factory=list)
    horizon_days: int = Field(default=14, ge=1, le=60)
    start_date: dt.date | None = None
    notebook_id: str | None = None
    user_id: str | None = None


def _ensure_goal(user_id: str, goal_id: str | None) -> None:
    if goal_id and not PLANNER_STORE.get("goals", user_id, goal_id):
        raise HTTPException(status_code=404, detail="Study goal not found")


def _ensure_topic(user_id: str, topic_id: str | None) -> dict[str, Any] | None:
    if not topic_id:
        return None
    topic = PLANNER_STORE.get("topics", user_id, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Study topic not found")
    return topic


def _ensure_relations(user_id: str, *, goal_id: str | None, topic_id: str | None, parent_id: str | None = None) -> None:
    _ensure_goal(user_id, goal_id)
    topic = _ensure_topic(user_id, topic_id)
    if parent_id:
        parent = PLANNER_STORE.get("topics", user_id, parent_id)
        if not parent:
            raise HTTPException(status_code=404, detail="Parent study topic not found")
        if topic and parent["id"] == topic["id"]:
            raise HTTPException(status_code=400, detail="A topic cannot be its own parent")
        if goal_id and parent.get("goal_id") and parent["goal_id"] != goal_id:
            raise HTTPException(status_code=400, detail="Parent topic belongs to a different goal")


def _ensure_notebook(user_id: str, notebook_id: str | None) -> None:
    if notebook_id and not get_notebook(user_id, notebook_id):
        raise HTTPException(status_code=404, detail="Notebook not found")


def _ensure_session(user_id: str, notebook_id: str | None, session_id: str | None) -> None:
    if not session_id:
        return
    if not notebook_id:
        raise HTTPException(status_code=400, detail="session_id requires notebook_id")
    if not get_session(user_id, notebook_id, session_id):
        raise HTTPException(status_code=404, detail="Chat session not found")


def _ensure_source(user_id: str, notebook_id: str | None, source_id: str | None) -> None:
    if not source_id:
        return
    if not notebook_id or not STORE:
        return
    with STORE._connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM apollo_sources s
                JOIN apollo_notebooks n ON n.id=s.notebook_id
                WHERE s.id=%s AND n.id=%s AND n.user_id=%s
                """,
                (source_id, notebook_id, user_id),
            )
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Source not found")


def _base_record(user_id: str) -> dict[str, str]:
    now = _now()
    return {"user_id": user_id, "created_at": now, "updated_at": now}


def _create_goal(user_id: str, data: GoalCreate) -> dict[str, Any]:
    record = {
        "id": new_id("goal"),
        **_base_record(user_id),
        "title": data.title.strip(),
        "description": data.description.strip(),
        "goal_type": data.goal_type.strip(),
        "subject": data.subject.strip(),
        "exam_date": data.exam_date.isoformat() if data.exam_date else None,
        "desired_outcome": data.desired_outcome.strip() if data.desired_outcome else None,
        "priority": data.priority,
        "status": data.status,
    }
    return PLANNER_STORE.create("goals", record)


def register(app: FastAPI) -> None:
    if app in _REGISTERED:
        return

    @app.get("/api/planner/goals")
    def list_goals(user_id: str = "default"):
        return {"goals": PLANNER_STORE.list("goals", _user_id(user_id))}

    @app.post("/api/planner/goals")
    def create_goal(payload: GoalCreate):
        user_id = _user_id(payload.user_id)
        return _create_goal(user_id, payload)

    @app.patch("/api/planner/goals/{goal_id}")
    def update_goal(goal_id: str, payload: GoalUpdate):
        user_id = _user_id(payload.user_id)
        if not PLANNER_STORE.get("goals", user_id, goal_id):
            raise HTTPException(status_code=404, detail="Study goal not found")
        changes = payload.model_dump(exclude_unset=True, exclude={"user_id"}, mode="json")
        if "title" in changes:
            changes["title"] = changes["title"].strip()
        if "description" in changes and changes["description"] is not None:
            changes["description"] = changes["description"].strip()
        if "subject" in changes and changes["subject"] is not None:
            changes["subject"] = changes["subject"].strip()
        return PLANNER_STORE.update("goals", user_id, goal_id, changes)

    @app.delete("/api/planner/goals/{goal_id}")
    def delete_goal(goal_id: str, user_id: str = "default"):
        deleted = PLANNER_STORE.delete("goals", _user_id(user_id), goal_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Study goal not found")
        return {"deleted": True, "id": goal_id}

    @app.get("/api/planner/topics")
    def list_topics(user_id: str = "default", goal_id: str | None = None):
        rows = PLANNER_STORE.list("topics", _user_id(user_id))
        if goal_id:
            rows = [row for row in rows if row.get("goal_id") == goal_id]
        return {"topics": rows}

    @app.get("/api/planner/topics/hierarchy")
    def topic_hierarchy(user_id: str = "default", goal_id: str | None = None):
        key = _user_id(user_id)
        rows = PLANNER_STORE.list("topics", key)
        if goal_id:
            rows = [row for row in rows if row.get("goal_id") == goal_id]
        by_parent: dict[str | None, list[dict[str, Any]]] = {}
        for row in rows:
            by_parent.setdefault(row.get("parent_id"), []).append({**row, "children": []})
        for bucket in by_parent.values():
            bucket.sort(key=lambda item: (int(item.get("sort_order", 0)), item.get("title", "").lower()))
        roots = by_parent.get(None, [])
        def attach(items):
            for item in items:
                children = by_parent.get(item["id"], [])
                item["children"] = children
                attach(children)
        attach(roots)
        return {"topics": roots}

    @app.post("/api/planner/topics")
    def create_topic(payload: TopicCreate):
        user_id = _user_id(payload.user_id)
        _ensure_relations(user_id, goal_id=payload.goal_id, topic_id=None, parent_id=payload.parent_id)
        record = {
            "id": new_id("topic"),
            **_base_record(user_id),
            "goal_id": payload.goal_id,
            "parent_id": payload.parent_id,
            "subject": payload.subject.strip(),
            "title": payload.title.strip(),
            "description": payload.description.strip() if payload.description else None,
            "estimated_minutes": payload.estimated_minutes,
            "difficulty": payload.difficulty,
            "status": payload.status,
            "sort_order": payload.sort_order,
        }
        return PLANNER_STORE.create("topics", record)

    @app.patch("/api/planner/topics/{topic_id}")
    def update_topic(topic_id: str, payload: TopicUpdate):
        user_id = _user_id(payload.user_id)
        existing = _ensure_topic(user_id, topic_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Study topic not found")
        changes = payload.model_dump(exclude_unset=True, exclude={"user_id"}, mode="json")
        next_goal = changes.get("goal_id", existing.get("goal_id"))
        next_parent = changes.get("parent_id", existing.get("parent_id"))
        _ensure_relations(user_id, goal_id=next_goal, topic_id=topic_id, parent_id=next_parent)
        if next_parent:
            parent = PLANNER_STORE.get("topics", user_id, next_parent)
            if parent and parent.get("goal_id") and next_goal and parent["goal_id"] != next_goal:
                raise HTTPException(status_code=400, detail="Parent topic must belong to the same goal")
        if "title" in changes:
            changes["title"] = changes["title"].strip()
        if "description" in changes and changes["description"] is not None:
            changes["description"] = changes["description"].strip()
        if "subject" in changes and changes["subject"] is not None:
            changes["subject"] = changes["subject"].strip()
        return PLANNER_STORE.update("topics", user_id, topic_id, changes)

    @app.delete("/api/planner/topics/{topic_id}")
    def delete_topic(topic_id: str, user_id: str = "default"):
        deleted = PLANNER_STORE.delete("topics", _user_id(user_id), topic_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Study topic not found")
        return {"deleted": True, "id": topic_id}

    @app.get("/api/planner/availability")
    def list_availability(user_id: str = "default"):
        return {"availability": PLANNER_STORE.list("availability", _user_id(user_id))}

    @app.post("/api/planner/availability")
    def create_availability(payload: AvailabilityCreate):
        user_id = _user_id(payload.user_id)
        if payload.end_time <= payload.start_time:
            raise HTTPException(status_code=400, detail="Availability end_time must be after start_time")
        record = {
            "id": new_id("avail"),
            "user_id": user_id,
            "weekday": payload.weekday,
            "start_time": payload.start_time.isoformat(),
            "end_time": payload.end_time.isoformat(),
            "enabled": payload.enabled,
        }
        return PLANNER_STORE.create("availability", record)

    @app.patch("/api/planner/availability/{availability_id}")
    def update_availability(availability_id: str, payload: AvailabilityUpdate):
        user_id = _user_id(payload.user_id)
        existing = PLANNER_STORE.get("availability", user_id, availability_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Availability window not found")
        changes = payload.model_dump(exclude_unset=True, exclude={"user_id"}, mode="json")
        start = changes.get("start_time", existing.get("start_time"))
        end = changes.get("end_time", existing.get("end_time"))
        if isinstance(start, str):
            start = dt.time.fromisoformat(start)
        if isinstance(end, str):
            end = dt.time.fromisoformat(end)
        if end <= start:
            raise HTTPException(status_code=400, detail="Availability end_time must be after start_time")
        return PLANNER_STORE.update("availability", user_id, availability_id, changes)

    @app.delete("/api/planner/availability/{availability_id}")
    def delete_availability(availability_id: str, user_id: str = "default"):
        deleted = PLANNER_STORE.delete("availability", _user_id(user_id), availability_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Availability window not found")
        return {"deleted": True, "id": availability_id}

    @app.get("/api/planner/blocks")
    def list_blocks(
        user_id: str = "default",
        start_date: dt.date | None = None,
        end_date: dt.date | None = None,
    ):
        rows = PLANNER_STORE.list("blocks", _user_id(user_id))
        if start_date:
            rows = [row for row in rows if row.get("planned_date", "") >= start_date.isoformat()]
        if end_date:
            rows = [row for row in rows if row.get("planned_date", "") <= end_date.isoformat()]
        return {"blocks": rows}

    @app.post("/api/planner/blocks")
    def create_block(payload: BlockCreate):
        user_id = _user_id(payload.user_id)
        _ensure_relations(user_id, goal_id=payload.goal_id, topic_id=payload.topic_id)
        _ensure_notebook(user_id, payload.notebook_id)
        _ensure_source(user_id, payload.notebook_id, payload.source_id)
        _ensure_session(user_id, payload.notebook_id, payload.session_id)
        if payload.session_id and payload.notebook_id is None:
            raise HTTPException(status_code=400, detail="session_id requires notebook_id")
        locked = payload.locked if payload.locked is not None else payload.generated_by == "manual"
        record = {
            "id": new_id("block"),
            **_base_record(user_id),
            "goal_id": payload.goal_id,
            "topic_id": payload.topic_id,
            "title": payload.title.strip(),
            "planned_date": payload.planned_date.isoformat(),
            "start_time": payload.start_time.isoformat() if payload.start_time else None,
            "duration_minutes": payload.duration_minutes,
            "status": payload.status,
            "priority": payload.priority,
            "generated_by": payload.generated_by,
            "locked": locked,
            "notebook_id": payload.notebook_id,
            "source_id": payload.source_id,
            "session_id": payload.session_id,
            "actual_minutes": payload.actual_minutes,
            "completed_at": _now() if payload.status == "completed" else None,
        }
        return PLANNER_STORE.create("blocks", record)

    @app.patch("/api/planner/blocks/{block_id}")
    def update_block(block_id: str, payload: BlockUpdate):
        user_id = _user_id(payload.user_id)
        existing = PLANNER_STORE.get("blocks", user_id, block_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Plan block not found")
        changes = payload.model_dump(exclude_unset=True, exclude={"user_id"}, mode="json")
        next_goal = changes.get("goal_id", existing.get("goal_id"))
        next_topic = changes.get("topic_id", existing.get("topic_id"))
        _ensure_relations(user_id, goal_id=next_goal, topic_id=next_topic)
        next_notebook = changes.get("notebook_id", existing.get("notebook_id"))
        next_session = changes.get("session_id", existing.get("session_id"))
        _ensure_notebook(user_id, next_notebook)
        _ensure_source(user_id, next_notebook, changes.get("source_id", existing.get("source_id")))
        _ensure_session(user_id, next_notebook, next_session)
        if "title" in changes and changes["title"] is not None:
            changes["title"] = changes["title"].strip()
        if changes.get("generated_by") == "manual":
            changes.setdefault("locked", True)
        if changes.get("status") == "completed":
            changes.setdefault("completed_at", _now())
            changes.setdefault("actual_minutes", existing.get("duration_minutes", 0))
        return PLANNER_STORE.update("blocks", user_id, block_id, changes)

    @app.delete("/api/planner/blocks/{block_id}")
    def delete_block(block_id: str, user_id: str = "default"):
        key = _user_id(user_id)
        existing = PLANNER_STORE.get("blocks", key, block_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Plan block not found")
        if existing.get("status") == "completed":
            raise HTTPException(status_code=400, detail="Completed blocks are immutable")
        deleted = PLANNER_STORE.delete("blocks", key, block_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Plan block not found")
        return {"deleted": True, "id": block_id}

    @app.post("/api/planner/blocks/{block_id}/start")
    def start_block(block_id: str, user_id: str = "default"):
        key = _user_id(user_id)
        block = PLANNER_STORE.get("blocks", key, block_id)
        if not block:
            raise HTTPException(status_code=404, detail="Plan block not found")
        if block.get("status") == "completed":
            raise HTTPException(status_code=400, detail="Completed blocks cannot be started")
        notebook_id = block.get("notebook_id")
        if not notebook_id:
            raise HTTPException(status_code=400, detail="This plan block has no notebook. Open a notebook and attach it before starting study.")
        _ensure_notebook(key, notebook_id)

        session = get_session(key, notebook_id, block.get("session_id")) if block.get("session_id") else None
        if not session:
            sessions = list_sessions(key, notebook_id)
            session = sessions[0] if sessions else create_session(key, notebook_id, "Study: " + str(block.get("title") or "Planned study"))
            block = PLANNER_STORE.update("blocks", key, block_id, {
                "notebook_id": notebook_id,
                "session_id": session["id"],
            }) or block
        return {"block": block, "session": session}

    @app.post("/api/planner/blocks/{block_id}/complete")
    def complete_block(block_id: str, payload: CompleteBlockRequest):
        user_id = _user_id(payload.user_id)
        existing = PLANNER_STORE.get("blocks", user_id, block_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Plan block not found")
        if existing.get("status") == "completed":
            return existing
        duration = int(existing.get("duration_minutes", 0))
        actual = duration if payload.actual_minutes is None else payload.actual_minutes
        return PLANNER_STORE.update(
            "blocks",
            user_id,
            block_id,
            {"status": "completed", "actual_minutes": actual, "completed_at": _now()},
        )

    @app.post("/api/planner/blocks/{block_id}/skip")
    def skip_block(block_id: str, user_id: str = "default"):
        existing = PLANNER_STORE.get("blocks", _user_id(user_id), block_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Plan block not found")
        if existing.get("status") == "completed":
            raise HTTPException(status_code=400, detail="Completed blocks are immutable")
        return PLANNER_STORE.update("blocks", _user_id(user_id), block_id, {"status": "skipped"})

    @app.post("/api/planner/blocks/{block_id}/move")
    def move_block(block_id: str, payload: MoveBlockRequest):
        user_id = _user_id(payload.user_id)
        existing = PLANNER_STORE.get("blocks", user_id, block_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Plan block not found")
        if existing.get("status") == "completed":
            raise HTTPException(status_code=400, detail="Completed blocks cannot be moved")
        return PLANNER_STORE.update(
            "blocks",
            user_id,
            block_id,
            {
                "planned_date": payload.planned_date.isoformat(),
                "start_time": payload.start_time.isoformat() if payload.start_time else None,
            },
        )

    @app.post("/api/planner/proposals")
    def generate_proposal(payload: ProposalRequest):
        from planner_service import generate_proposal
        user_id = _user_id(payload.user_id)
        _ensure_notebook(user_id, payload.notebook_id)
        try:
            return generate_proposal(
                user_id,
                goal_ids=payload.goal_ids,
                horizon_days=payload.horizon_days,
                start_date=payload.start_date,
                notebook_id=payload.notebook_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/planner/proposals/apply")
    def apply_proposal(payload: ApplyProposalRequest):
        from planner_service import apply_proposal
        user_id = _user_id(payload.user_id)
        try:
            return apply_proposal(user_id, payload.proposal)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/planner/replan")
    def replan(payload: ReplanRequest):
        from planner_service import generate_replan_proposal
        user_id = _user_id(payload.user_id)
        _ensure_notebook(user_id, payload.notebook_id)
        try:
            return generate_replan_proposal(
                user_id,
                goal_ids=payload.goal_ids,
                horizon_days=payload.horizon_days,
                start_date=payload.start_date,
                notebook_id=payload.notebook_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/planner/overview")
    def planner_overview(user_id: str = "default", days: int = Query(default=7, ge=1, le=31)):
        from planner_service import build_planner_overview
        return build_planner_overview(_user_id(user_id), days=days)

    _REGISTERED.add(app)
