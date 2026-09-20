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