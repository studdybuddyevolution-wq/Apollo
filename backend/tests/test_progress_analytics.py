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



def test_filesystem_socratic_sessions_respect_window(monkeypatch, tmp_path):
    workspace_service.DATA_DIR = tmp_path
    workspace_service.WORKSPACE_FILE = tmp_path / "workspace.json"
    workspace_service.STORE = None
    analytics_service.STORE = None
    today = dt.datetime.now(dt.UTC).date()
    inside = today - dt.timedelta(days=1)
    outside = today - dt.timedelta(days=10)

    sessions = {
        "inside": {
            "id": "inside", "notebook_id": "nb1", "user_id": "u1",
            "title": "Inside", "created": f"{inside}T09:00:00",
            "updated": f"{inside}T09:00:00",
            "socratic_state": {"topic": "Physics"},
        },
        "outside": {
            "id": "outside", "notebook_id": "nb1", "user_id": "u1",
            "title": "Outside", "created": f"{outside}T09:00:00",
            "updated": f"{outside}T09:00:00",
            "socratic_state": {"topic": "History"},
        },
    }
    messages = {
        "inside": [_msg("m1", str(inside))],
        "outside": [_msg("m2", str(outside))],
    }
    _write_workspace(tmp_path, sessions, messages)

    result = analytics_service.get_progress_dashboard("u1", days=7)

    assert result["activity"]["socratic_sessions"] == 1
    assert result["activity"]["sessions"] == 1


def test_filesystem_daily_sessions_count_distinct_sessions(monkeypatch, tmp_path):
    workspace_service.DATA_DIR = tmp_path
    workspace_service.WORKSPACE_FILE = tmp_path / "workspace.json"
    workspace_service.STORE = None
    analytics_service.STORE = None
    today = dt.datetime.now(dt.UTC).date()

    sessions = {}
    messages = {}
    for index in range(2):
        session_id = f"s{index}"
        sessions[session_id] = {
            "id": session_id, "notebook_id": "nb1", "user_id": "u1",
            "title": f"Chat {index}", "created": f"{today}T09:00:00",
            "updated": f"{today}T09:00:00", "socratic_state": None,
        }
        messages[session_id] = [_msg(f"m{index}-1", str(today)), _msg(f"m{index}-2", str(today))]

    _write_workspace(tmp_path, sessions, messages)

    result = analytics_service.get_progress_dashboard("u1", days=7)
    calendar_item = next(item for item in result["activity"]["calendar"] if item["date"] == str(today))

    assert calendar_item["sessions"] == 2
    assert calendar_item["messages"] == 4


def test_filesystem_mastery_matches_mastery_store_semantics(monkeypatch, tmp_path):
    workspace_service.DATA_DIR = tmp_path
    workspace_service.WORKSPACE_FILE = tmp_path / "workspace.json"
    workspace_service.STORE = None
    analytics_service.STORE = None

    mastery_file = tmp_path / "socratic_mastery.json"
    mastery_file.write_text(
        json.dumps({
            "u1:physics": {
                "user_id": "u1", "topic_key": "physics", "display_name": "Physics",
                "score": 80, "attempts": 3, "correct": 2, "updated": "2026-09-20T10:00:00",
            },
            "u1:biology": {
                "user_id": "u1", "topic_key": "biology", "display_name": "Biology",
                "score": 95, "attempts": 2, "correct": 2, "updated": "2026-09-20T10:00:00",
            },
        }),
        encoding="utf-8",
    )

    import socratic_engine
    monkeypatch.setattr(socratic_engine, "MASTERY_FILE", mastery_file)
    _write_workspace(tmp_path, {}, {})

    result = analytics_service.get_progress_dashboard("u1", days=7)

    assert result["mastery"]["attempts"] == 5
    assert result["mastery"]["correct"] == 4
    assert result["mastery"]["accuracy"] == 0.8
    assert result["mastery"]["average_score"] == 87.5
    assert result["mastery"]["proficient_topics"] == 2
    assert result["mastery"]["mastered_topics"] == 1
