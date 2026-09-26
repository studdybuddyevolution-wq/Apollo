import base64
import json

import workspace_service
import session_history
from session_history import list_messages_page, list_sessions_page


def test_session_cursor_pagination_covers_history_without_duplicates(monkeypatch, tmp_path):
    monkeypatch.setattr(workspace_service, "STORE", None)
    monkeypatch.setattr(session_history, "STORE", None)
    monkeypatch.setattr(workspace_service, "DATA_DIR", tmp_path)
    monkeypatch.setattr(workspace_service, "WORKSPACE_FILE", tmp_path / "workspace.json")

    ids = []
    for index in range(5):
        session = workspace_service.create_session("u1", "nb1", "Chat " + str(index))
        ids.append(session["id"])
        workspace_service.append_message("u1", "nb1", session["id"], "user", "Question " + str(index))

    first = list_sessions_page("u1", limit=2)
    second = list_sessions_page("u1", limit=2, cursor=first["next_cursor"])
    third = list_sessions_page("u1", limit=2, cursor=second["next_cursor"])

    combined = [item["id"] for item in first["sessions"] + second["sessions"] + third["sessions"]]
    assert len(combined) == 5
    assert len(set(combined)) == 5
    assert set(combined) == set(ids)
    assert first["has_more"] is True
    assert third["has_more"] is False


def test_message_cursor_pagination_returns_chronological_pages(monkeypatch, tmp_path):
    monkeypatch.setattr(workspace_service, "STORE", None)
    monkeypatch.setattr(workspace_service, "DATA_DIR", tmp_path)
    monkeypatch.setattr(workspace_service, "WORKSPACE_FILE", tmp_path / "workspace.json")

    session = workspace_service.create_session("u2", "nb1", "Paged chat")
    for index in range(6):
        workspace_service.append_message("u2", "nb1", session["id"], "user", "Message " + str(index))

    first = list_messages_page("u2", "nb1", session["id"], limit=2)
    second = list_messages_page("u2", "nb1", session["id"], limit=2, cursor=first["next_cursor"])
    third = list_messages_page("u2", "nb1", session["id"], limit=2, cursor=second["next_cursor"])

    combined = first["messages"] + second["messages"] + third["messages"]
    assert [item["content"] for item in combined]
    assert len(combined) == 6
    assert len({item["id"] for item in combined}) == 6
    assert third["has_more"] is False


def test_session_page_search_and_socratic_filter(monkeypatch, tmp_path):
    monkeypatch.setattr(workspace_service, "STORE", None)
    monkeypatch.setattr(workspace_service, "DATA_DIR", tmp_path)
    monkeypatch.setattr(workspace_service, "WORKSPACE_FILE", tmp_path / "workspace.json")

    chat = workspace_service.create_session("u3", "nb1", "Physics normal")
    workspace_service.append_message("u3", "nb1", chat["id"], "user", "Ohm law")

    socratic = workspace_service.create_session("u3", "nb1", "Physics Socratic")
    workspace_service.save_socratic_state("u3", "nb1", socratic["id"], {"topic": "Newton laws", "phase": "elenchus"})

    filtered = list_sessions_page("u3", kind="socratic")
    assert [item["id"] for item in filtered["sessions"]] == [socratic["id"]]

    searched = list_sessions_page("u3", search="Newton")
    assert [item["id"] for item in searched["sessions"]] == [socratic["id"]]


# ---------------------------------------------------------------------------
# Malformed cursor handling
# ---------------------------------------------------------------------------

def test_decode_cursor_returns_none_for_malformed_base64():
    assert session_history.decode_cursor("not-valid-base64!!!") is None


def test_decode_cursor_returns_none_for_malformed_json():
    garbage = base64.urlsafe_b64encode(b"not json at all").decode("ascii").rstrip("=")
    assert session_history.decode_cursor(garbage) is None


def test_decode_cursor_returns_none_for_missing_fields():
    payload = base64.urlsafe_b64encode(json.dumps({"foo": "bar"}).encode()).decode("ascii").rstrip("=")
    assert session_history.decode_cursor(payload) is None


def test_decode_cursor_still_works_for_a_valid_cursor():
    cursor = session_history.encode_cursor("2026-09-20T10:00:00", "chat_abc123")
    assert session_history.decode_cursor(cursor) == ("2026-09-20T10:00:00", "chat_abc123")


def test_sessions_route_rejects_malformed_cursor_with_400(monkeypatch, tmp_path):
    monkeypatch.setattr(workspace_service, "STORE", None)
    monkeypatch.setattr(session_history, "STORE", None)
    monkeypatch.setattr(workspace_service, "DATA_DIR", tmp_path)
    monkeypatch.setattr(workspace_service, "WORKSPACE_FILE", tmp_path / "workspace.json")

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import history_routes

    app = FastAPI()
    history_routes.register(app)
    client = TestClient(app)

    response = client.get("/api/sessions", params={"user_id": "u1", "cursor": "not-valid-base64!!!"})
    assert response.status_code == 400

    response = client.get("/api/sessions", params={"user_id": "u1"})
    assert response.status_code == 200


def test_session_pagination_with_identical_updated_timestamps(monkeypatch, tmp_path):
    monkeypatch.setattr(workspace_service, "STORE", None)
    monkeypatch.setattr(session_history, "STORE", None)
    monkeypatch.setattr(workspace_service, "DATA_DIR", tmp_path)
    monkeypatch.setattr(workspace_service, "WORKSPACE_FILE", tmp_path / "workspace.json")
    monkeypatch.setattr(workspace_service, "_now", lambda: "2026-09-20T10:00:00")

    ids = [workspace_service.create_session("u4", "nb1", f"Chat {i}")["id"] for i in range(5)]

    seen: list[str] = []
    cursor = None
    for _ in range(10):
        page = list_sessions_page("u4", limit=2, cursor=cursor)
        seen.extend(item["id"] for item in page["sessions"])
        if not page["has_more"]:
            break
        cursor = page["next_cursor"]

    assert len(seen) == len(ids)
    assert len(set(seen)) == len(ids)
    assert set(seen) == set(ids)


def test_message_pagination_with_identical_created_timestamps(monkeypatch, tmp_path):
    monkeypatch.setattr(workspace_service, "STORE", None)
    monkeypatch.setattr(workspace_service, "DATA_DIR", tmp_path)
    monkeypatch.setattr(workspace_service, "WORKSPACE_FILE", tmp_path / "workspace.json")

    session = workspace_service.create_session("u5", "nb1", "Same-second chat")
    monkeypatch.setattr(workspace_service, "_now", lambda: "2026-09-20T10:00:00")
    ids = []
    for i in range(6):
        msg = workspace_service.append_message("u5", "nb1", session["id"], "user", f"Message {i}")
        ids.append(msg["id"])

    seen: list[str] = []
    cursor = None
    for _ in range(10):
        page = list_messages_page("u5", "nb1", session["id"], limit=2, cursor=cursor)
        seen.extend(item["id"] for item in page["messages"])
        if not page["has_more"]:
            break
        cursor = page["next_cursor"]

    assert len(seen) == len(ids)
    assert len(set(seen)) == len(ids)
    assert set(seen) == set(ids)


def test_session_deletion_between_page_requests_does_not_crash_or_duplicate(monkeypatch, tmp_path):
    monkeypatch.setattr(workspace_service, "STORE", None)
    monkeypatch.setattr(session_history, "STORE", None)
    monkeypatch.setattr(workspace_service, "DATA_DIR", tmp_path)
    monkeypatch.setattr(workspace_service, "WORKSPACE_FILE", tmp_path / "workspace.json")

    ids = [workspace_service.create_session("u6", "nb1", f"Chat {i}")["id"] for i in range(5)]

    first = list_sessions_page("u6", limit=2)
    remaining_before_delete = set(ids) - {item["id"] for item in first["sessions"]}
    deleted_id = next(iter(remaining_before_delete))
    assert workspace_service.delete_session("u6", "nb1", deleted_id) is True

    combined = list(first["sessions"])
    cursor = first["next_cursor"]
    has_more = first["has_more"]
    while has_more:
        page = list_sessions_page("u6", limit=2, cursor=cursor)
        combined.extend(page["sessions"])
        has_more = page["has_more"]
        cursor = page["next_cursor"]

    combined_ids = [item["id"] for item in combined]
    assert deleted_id not in combined_ids
    assert len(combined_ids) == len(set(combined_ids))
    assert set(combined_ids) == set(ids) - {deleted_id}
