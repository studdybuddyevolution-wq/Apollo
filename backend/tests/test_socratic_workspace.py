import json

from fastapi.testclient import TestClient

import context_builder
import main
import phase1_routes
import workspace_service


def test_socratic_workspace_stream_emits_state_and_persists(monkeypatch, tmp_path):
    monkeypatch.setattr(workspace_service, "STORE", None)
    monkeypatch.setattr(workspace_service, "DATA_DIR", tmp_path)
    monkeypatch.setattr(workspace_service, "WORKSPACE_FILE", tmp_path / "workspace.json")
    monkeypatch.setattr(phase1_routes, "get_notebook", lambda _user_id, notebook_id: {"id": notebook_id, "title": "Physics"})
    monkeypatch.setattr(main, "_check_rate_limit", lambda _key: (True, 0))
    monkeypatch.setattr(
        context_builder,
        "build_context",
        lambda *args, **kwargs: {"context": "V = IR is Ohm's law.", "full_sources": ["physics.txt"]},
    )

    def fake_stream(request, _context, _sources):
        yield 'data: {"type":"start","model":"openai/gpt-oss-120b","research":"socratic"}\n\n'
        yield 'data: {"type":"token","text":"What are you assuming about memorization?"}\n\n'
        yield 'data: {"type":"done"}\n\n'

    monkeypatch.setattr(main, "_stream_model", fake_stream)

    client = TestClient(main.app)
    response = client.post(
        "/api/chat/workspace",
        json={
            "messages": [{"role": "user", "content": "I think memorizing formulas is the best way to learn physics."}],
            "notebook_id": "nb1",
            "notebook_title": "Physics",
            "active_sources": ["physics.txt"],
            "source_modes": {"physics.txt": "full"},
            "user_id": "u1",
            "research_mode": "socratic",
            "socratic_topic": "How should I learn physics?",
        },
    )

    assert response.status_code == 200
    assert '"type": "socratic_state"' in response.text
    assert '"phase": "elenchus"' in response.text
    assert "What are you assuming about memorization?" in response.text

    sessions = workspace_service.list_sessions("u1", "nb1")
    assert len(sessions) == 1
    session_id = sessions[0]["id"]
    state = workspace_service.get_socratic_state("u1", "nb1", session_id)
    assert state["phase"] == "elenchus"
    assert state["topic"] == "How should I learn physics?"

    messages = workspace_service.list_messages("u1", "nb1", session_id)
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[-1]["content"] == "What are you assuming about memorization?"


def test_socratic_route_is_registered():
    routes = {route.path for route in main.app.routes}
    assert "/api/socratic/quick-check" in routes
    assert "/api/socratic/quick-check/grade" in routes
    assert "/api/socratic/mastery" in routes
    assert "/api/notebooks/{notebook_id}/sessions/{session_id}/socratic-state" in routes



def test_socratic_workspace_persists_partial_response_on_cancel(monkeypatch, tmp_path):
    monkeypatch.setattr(workspace_service, "STORE", None)
    monkeypatch.setattr(workspace_service, "DATA_DIR", tmp_path)
    monkeypatch.setattr(workspace_service, "WORKSPACE_FILE", tmp_path / "workspace.json")
    monkeypatch.setattr(phase1_routes, "get_notebook", lambda _user_id, notebook_id: {"id": notebook_id, "title": "Physics"})
    monkeypatch.setattr(main, "_check_rate_limit", lambda _key: (True, 0))
    monkeypatch.setattr(
        context_builder,
        "build_context",
        lambda *args, **kwargs: {"context": "", "full_sources": []},
    )

    def cancelled_stream(request, _context, _sources):
        yield 'data: {"type":"start","model":"openai/gpt-oss-120b","research":"socratic"}\n\n'
        yield 'data: {"type":"token","text":"Partial Socratic response"}\n\n'
        raise GeneratorExit

    monkeypatch.setattr(main, "_stream_model", cancelled_stream)

    client = TestClient(main.app)
    response = client.post(
        "/api/chat/workspace",
        json={
            "messages": [{"role": "user", "content": "I think practice is enough to master physics."}],
            "notebook_id": "nb_cancel",
            "notebook_title": "Physics",
            "user_id": "u_cancel",
            "research_mode": "socratic",
            "socratic_topic": "How should I learn physics?",
        },
    )

    assert response.status_code == 200
    sessions = workspace_service.list_sessions("u_cancel", "nb_cancel")
    assert len(sessions) == 1
    session_id = sessions[0]["id"]
    messages = workspace_service.list_messages("u_cancel", "nb_cancel", session_id)
    assert messages[-1]["content"] == "Partial Socratic response"
    state = workspace_service.get_socratic_state("u_cancel", "nb_cancel", session_id)
    assert state["phase"] == "elenchus"


def test_global_session_history_includes_message_counts_and_socratic_state(monkeypatch, tmp_path):
    monkeypatch.setattr(workspace_service, "STORE", None)
    monkeypatch.setattr(workspace_service, "DATA_DIR", tmp_path)
    monkeypatch.setattr(workspace_service, "WORKSPACE_FILE", tmp_path / "workspace.json")

    first = workspace_service.create_session("u_history", "nb1", "Physics chat")
    workspace_service.append_message("u_history", "nb1", first["id"], "user", "What is Ohm's law?")
    workspace_service.append_message("u_history", "nb1", first["id"], "assistant", "V = IR.")
    workspace_service.save_socratic_state(
        "u_history",
        "nb1",
        first["id"],
        {
            "phase": "elenchus",
            "topic": "Ohm's law",
            "mastery_score": 62.0,
            "mastery_tier": "Proficient",
        },
    )

    second = workspace_service.create_session("u_history", "nb2", "Chemistry chat")
    workspace_service.append_message("u_history", "nb2", second["id"], "user", "Explain valency.")

    history = workspace_service.list_all_sessions("u_history")
    assert [row["id"] for row in history] == [second["id"], first["id"]]
    assert history[0]["message_count"] == 1
    assert history[1]["message_count"] == 2
    assert history[1]["socratic_state"]["topic"] == "Ohm's law"


def test_global_session_history_route_is_registered():
    routes = {route.path for route in main.app.routes}
    assert "/api/sessions" in routes

    client = TestClient(main.app)
    response = client.get("/api/sessions?user_id=history_test")
    assert response.status_code == 200
    assert response.json() == {"sessions": []}
