import pytest
from fastapi.testclient import TestClient

import planner_store
import phase2_app


@pytest.fixture(autouse=True)
def isolated_planner_store(tmp_path, monkeypatch):
    monkeypatch.setattr(planner_store.PLANNER_STORE, "_path", tmp_path / "study_planner.json")
    planner_store.PLANNER_STORE._tables = {name: {} for name in planner_store.ENTITY_FIELDS}
    yield
    planner_store.PLANNER_STORE._tables = {name: {} for name in planner_store.ENTITY_FIELDS}


def test_planner_crud_and_ownership():
    client = TestClient(phase2_app.app)

    goal = client.post("/api/planner/goals", json={
        "title": "Physics exam",
        "subject": "Physics",
        "exam_date": "2026-10-10",
        "priority": 5,
        "user_id": "alice",
    })
    assert goal.status_code == 200
    goal_id = goal.json()["id"]

    topic = client.post("/api/planner/topics", json={
        "title": "Ohm's Law",
        "goal_id": goal_id,
        "estimated_minutes": 45,
        "difficulty": 3,
        "user_id": "alice",
    })
    assert topic.status_code == 200
    topic_id = topic.json()["id"]

    child = client.post("/api/planner/topics", json={
        "title": "Resistance",
        "goal_id": goal_id,
        "parent_id": topic_id,
        "estimated_minutes": 30,
        "difficulty": 2,
        "user_id": "alice",
    })
    assert child.status_code == 200

    availability = client.post("/api/planner/availability", json={
        "weekday": 1,
        "start_time": "17:00:00",
        "end_time": "19:00:00",
        "user_id": "alice",
    })
    assert availability.status_code == 200

    block = client.post("/api/planner/blocks", json={
        "title": "Manual review",
        "planned_date": "2026-10-05",
        "start_time": "17:00:00",
        "duration_minutes": 30,
        "goal_id": goal_id,
        "topic_id": topic_id,
        "generated_by": "manual",
        "user_id": "alice",
    })
    assert block.status_code == 200
    assert block.json()["locked"] is True

    assert client.get("/api/planner/goals?user_id=alice").json()["goals"][0]["id"] == goal_id
    assert client.get(f"/api/planner/goals?user_id=bob").json()["goals"] == []
    assert client.patch(f"/api/planner/goals/{goal_id}", json={"title": "Nope", "user_id": "bob"}).status_code == 404


def test_invalid_availability_is_rejected():
    client = TestClient(phase2_app.app)
    response = client.post("/api/planner/availability", json={
        "weekday": 2,
        "start_time": "18:00",
        "end_time": "18:00",
        "user_id": "alice",
    })
    assert response.status_code == 400


def test_completed_block_is_immutable():
    client = TestClient(phase2_app.app)
    created = client.post("/api/planner/blocks", json={
        "title": "Review",
        "planned_date": "2026-10-02",
        "duration_minutes": 25,
        "user_id": "alice",
    }).json()
    block_id = created["id"]
    completed = client.post(f"/api/planner/blocks/{block_id}/complete", json={"actual_minutes": 20, "user_id": "alice"})
    assert completed.status_code == 200
    moved = client.post(f"/api/planner/blocks/{block_id}/move", json={"planned_date": "2026-10-03", "user_id": "alice"})
    assert moved.status_code == 400
