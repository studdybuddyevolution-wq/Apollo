from fastapi.testclient import TestClient

import phase2_app
import planner_store


def _reset(tmp_path):
    planner_store.PLANNER_STORE._path = tmp_path / "study_planner.json"
    planner_store.PLANNER_STORE._tables = {name: {} for name in planner_store.ENTITY_FIELDS}


def test_start_study_reuses_existing_workspace_session(tmp_path):
    _reset(tmp_path)
    client = TestClient(phase2_app.app)
    notebook = client.post("/api/notebooks", json={"title": "Physics", "user_id": "alice"}).json()
    block = client.post("/api/planner/blocks", json={
        "title": "Current Electricity",
        "planned_date": "2026-10-01",
        "duration_minutes": 45,
        "notebook_id": notebook["id"],
        "user_id": "alice",
    }).json()

    started = client.post(f"/api/planner/blocks/{block['id']}/start?user_id=alice")
    assert started.status_code == 200
    body = started.json()
    assert body["session"]["notebook_id"] == notebook["id"]
    assert body["block"]["session_id"] == body["session"]["id"]


def test_completed_block_cannot_be_deleted(tmp_path):
    _reset(tmp_path)
    client = TestClient(phase2_app.app)
    block = client.post("/api/planner/blocks", json={
        "title": "Review",
        "planned_date": "2026-10-01",
        "duration_minutes": 30,
        "user_id": "alice",
    }).json()
    client.post(
        f"/api/planner/blocks/{block['id']}/complete",
        json={"actual_minutes": 30, "user_id": "alice"},
    )
    response = client.delete(f"/api/planner/blocks/{block['id']}?user_id=alice")
    assert response.status_code == 400
