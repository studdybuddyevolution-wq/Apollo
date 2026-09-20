from fastapi.testclient import TestClient

import main


def test_history_and_progress_routes_are_registered():
    paths = {route.path for route in main.app.routes}
    assert "/api/sessions" in paths
    assert "/api/progress/dashboard" in paths
    assert "/api/notebooks/{notebook_id}/sessions/{session_id}/messages/page" in paths


def test_history_empty_page_is_backward_safe():
    client = TestClient(main.app)
    response = client.get("/api/sessions?user_id=history_empty")
    assert response.status_code == 200
    payload = response.json()
    assert payload["sessions"] == []
    assert payload["has_more"] is False
