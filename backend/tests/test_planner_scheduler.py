from datetime import date

from fastapi.testclient import TestClient

import phase2_app
import planner_store


def _reset_store(tmp_path, monkeypatch):
    monkeypatch.setattr(planner_store.PLANNER_STORE, "_path", tmp_path / "study_planner.json")
    planner_store.PLANNER_STORE._tables = {name: {} for name in planner_store.ENTITY_FIELDS}


def _seed(client, user="alice", estimated=120, exam="2026-10-03"):
    goal = client.post("/api/planner/goals", json={
        "title": "Physics exam",
        "subject": "Physics",
        "exam_date": exam,
        "priority": 5,
        "user_id": user,
    }).json()
    topic = client.post("/api/planner/topics", json={
        "title": "Electricity",
        "goal_id": goal["id"],
        "estimated_minutes": estimated,
        "difficulty": 3,
        "user_id": user,
    }).json()
    for weekday in range(7):
        client.post("/api/planner/availability", json={
            "weekday": weekday,
            "start_time": "17:00",
            "end_time": "18:00",
            "user_id": user,
        })
    return goal, topic


def test_scheduler_is_deterministic_and_explainable(tmp_path, monkeypatch):
    _reset_store(tmp_path, monkeypatch)
    client = TestClient(phase2_app.app)
    goal, topic = _seed(client, estimated=90)

    first = client.post("/api/planner/proposals", json={
        "goal_ids": [goal["id"]],
        "start_date": "2026-10-01",
        "horizon_days": 3,
        "user_id": "alice",
    })
    second = client.post("/api/planner/proposals", json={
        "goal_ids": [goal["id"]],
        "start_date": "2026-10-01",
        "horizon_days": 3,
        "user_id": "alice",
    })
    assert first.status_code == 200
    assert second.status_code == 200

    fields = lambda payload: [
        {key: item[key] for key in ("title", "planned_date", "start_time", "duration_minutes", "topic_id", "goal_id")}
        for item in payload["blocks"]
    ]
    assert fields(first.json()) == fields(second.json())
    assert first.json()["deterministic"] is True
    assert first.json()["blocks"][0]["reason"]
    assert first.json()["available_capacity_minutes"] == 180


def test_capacity_limit_and_deadline_warning(tmp_path, monkeypatch):
    _reset_store(tmp_path, monkeypatch)
    client = TestClient(phase2_app.app)
    goal, topic = _seed(client, estimated=240, exam="2026-10-02")

    # Only two one-hour windows are available before the exam.
    for row in client.get("/api/planner/availability?user_id=alice").json()["availability"]:
        if row["weekday"] not in {3, 4}:
            client.delete(f"/api/planner/availability/{row['id']}?user_id=alice")

    response = client.post("/api/planner/proposals", json={
        "goal_ids": [goal["id"]],
        "start_date": "2026-10-01",
        "horizon_days": 7,
        "user_id": "alice",
    })
    assert response.status_code == 200
    body = response.json()
    assert sum(block["duration_minutes"] for block in body["blocks"]) == 120
    assert body["unscheduled_work"]
    assert any("unscheduled" in warning.lower() for warning in body["warnings"])


def test_apply_proposal_persists_only_after_acceptance(tmp_path, monkeypatch):
    _reset_store(tmp_path, monkeypatch)
    client = TestClient(phase2_app.app)
    goal, _ = _seed(client, estimated=45)

    proposal = client.post("/api/planner/proposals", json={
        "goal_ids": [goal["id"]],
        "start_date": "2026-10-01",
        "horizon_days": 1,
        "user_id": "alice",
    }).json()
    assert client.get("/api/planner/blocks?user_id=alice").json()["blocks"] == []

    applied = client.post("/api/planner/proposals/apply", json={
        "proposal": proposal,
        "user_id": "alice",
    })
    assert applied.status_code == 200
    blocks = client.get("/api/planner/blocks?user_id=alice").json()["blocks"]
    assert len(blocks) == 1
    assert blocks[0]["topic_id"] == proposal["blocks"][0]["topic_id"]


def test_replan_does_not_delete_manual_or_locked_blocks(tmp_path, monkeypatch):
    _reset_store(tmp_path, monkeypatch)
    client = TestClient(phase2_app.app)
    goal, topic = _seed(client, estimated=45)

    manual = client.post("/api/planner/blocks", json={
        "title": "Teacher-assigned review",
        "planned_date": "2026-10-01",
        "start_time": "17:00",
        "duration_minutes": 30,
        "goal_id": goal["id"],
        "topic_id": topic["id"],
        "generated_by": "manual",
        "user_id": "alice",
    }).json()

    generated = client.post("/api/planner/blocks", json={
        "title": "Generated review",
        "planned_date": "2026-10-01",
        "start_time": "17:30",
        "duration_minutes": 30,
        "goal_id": goal["id"],
        "topic_id": topic["id"],
        "generated_by": "generated",
        "locked": False,
        "user_id": "alice",
    }).json()

    response = client.post("/api/planner/replan", json={
        "goal_ids": [goal["id"]],
        "start_date": "2026-10-01",
        "horizon_days": 3,
        "user_id": "alice",
    })
    assert response.status_code == 200
    ids = response.json()["delete_block_ids"]
    assert generated["id"] in ids
    assert manual["id"] not in ids

    applied = client.post("/api/planner/proposals/apply", json={
        "proposal": response.json(),
        "user_id": "alice",
    })
    assert applied.status_code == 200
    remaining = {row["id"]: row for row in client.get("/api/planner/blocks?user_id=alice").json()["blocks"]}
    assert manual["id"] in remaining
    assert generated["id"] not in remaining


def test_cross_user_proposal_cannot_use_foreign_goal(tmp_path, monkeypatch):
    _reset_store(tmp_path, monkeypatch)
    client = TestClient(phase2_app.app)
    goal, _ = _seed(client, user="alice")
    response = client.post("/api/planner/proposals", json={
        "goal_ids": [goal["id"]],
        "start_date": "2026-10-01",
        "user_id": "bob",
    })
    assert response.status_code == 400
