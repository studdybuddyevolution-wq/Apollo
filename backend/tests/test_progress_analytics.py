import datetime as dt
import json

import analytics_service
import workspace_service


def test_filesystem_progress_dashboard_calculates_gapless_streak(monkeypatch, tmp_path):
    workspace_service.DATA_DIR = tmp_path
    workspace_service.WORKSPACE_FILE = tmp_path / "workspace.json"
    workspace_service.STORE = None
    analytics_service.STORE = None

    session = {
        "id": "chat_1",
        "notebook_id": "nb1",
        "user_id": "u1",
        "title": "Study",
        "created": "2026-09-17T10:00:00",
        "updated": "2026-09-20T10:00:00",
        "socratic_state": {"phase": "elenchus"},
    }
    messages = {
        "chat_1": [
            {"id": "m1", "session_id": "chat_1", "role": "user", "content": "a", "created": "2026-09-18T10:00:00"},
            {"id": "m2", "session_id": "chat_1", "role": "assistant", "content": "b", "created": "2026-09-19T10:00:00"},
            {"id": "m3", "session_id": "chat_1", "role": "user", "content": "c", "created": "2026-09-20T10:00:00"},
        ],
    }
    payload = {"sessions": {"chat_1": session}, "messages": messages, "notes": {}}
    (tmp_path / "workspace.json").write_text(json.dumps(payload), encoding="utf-8")

    result = analytics_service.get_progress_dashboard("u1", days=30)
    assert result["streak"]["current"] == 3
    assert result["streak"]["longest"] == 3
    assert result["streak"]["active_days"] == 3
    assert result["activity"]["sessions"] == 1
    assert result["activity"]["messages"] == 3


def test_progress_dashboard_window_has_daily_rows(monkeypatch, tmp_path):
    workspace_service.DATA_DIR = tmp_path
    workspace_service.WORKSPACE_FILE = tmp_path / "workspace.json"
    workspace_service.STORE = None
    analytics_service.STORE = None
    payload = {"sessions": {}, "messages": {}, "notes": {}}
    (tmp_path / "workspace.json").write_text(json.dumps(payload), encoding="utf-8")

    result = analytics_service.get_progress_dashboard("u2", days=7)
    assert result["window_days"] == 7
    assert len(result["activity"]["calendar"]) == 7
    assert sum(item["messages"] for item in result["activity"]["calendar"]) == 0
