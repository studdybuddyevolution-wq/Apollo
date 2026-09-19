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
