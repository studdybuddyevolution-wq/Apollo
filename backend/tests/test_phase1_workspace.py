from types import SimpleNamespace

import pytest

import context_builder
import main
import workspace_service


def test_source_modes_only_retrieve_full_sources(monkeypatch):
    calls = []

    monkeypatch.setattr(context_builder, "retrieve_hybrid", lambda *args, **kwargs: calls.append(kwargs["source_names"]) or [{"source": "full.md", "text": "full context"}])
    monkeypatch.setattr(context_builder, "format_context", lambda results, **kwargs: "full context")
    monkeypatch.setattr(context_builder, "token_count", lambda value: 2)
    monkeypatch.setattr(context_builder, "STORE", None)

    built = context_builder.build_context(
        "u1",
        "nb1",
        ["full.md", "insights.md", "off.md"],
        "question",
        source_modes={"full.md": "full", "insights.md": "insights", "off.md": "off"},
    )

    assert calls == [["full.md"]]
    assert built["full_sources"] == ["full.md"]
    assert built["insight_sources"] == ["full.md", "insights.md"]
    assert built["enabled_sources"] == ["full.md", "insights.md"]


def test_workspace_filesystem_sessions_and_messages(monkeypatch, tmp_path):
    monkeypatch.setattr(workspace_service, "STORE", None)
    monkeypatch.setattr(workspace_service, "DATA_DIR", tmp_path)
    monkeypatch.setattr(workspace_service, "WORKSPACE_FILE", tmp_path / "workspace.json")

    session = workspace_service.create_session("u1", "nb1", "New chat")
    message = workspace_service.append_message("u1", "nb1", session["id"], "user", "Explain Ohm's law")

    assert message["role"] == "user"
    assert workspace_service.get_session("u1", "nb1", session["id"])["title"] == "Explain Ohm's law"
    assert workspace_service.list_messages("u1", "nb1", session["id"])[0]["content"] == "Explain Ohm's law"


def test_workspace_filesystem_notes(monkeypatch, tmp_path):
    monkeypatch.setattr(workspace_service, "STORE", None)
    monkeypatch.setattr(workspace_service, "DATA_DIR", tmp_path)
    monkeypatch.setattr(workspace_service, "WORKSPACE_FILE", tmp_path / "workspace.json")

    note = workspace_service.create_note("u1", "nb1", "Ohm's Law", "V = IR", "chat", "chat_1")
    updated = workspace_service.update_note("u1", "nb1", note["id"], "Ohm's Law", "V = IR and R = V/I")

    assert updated["content"].endswith("R = V/I")
    assert workspace_service.list_notes("u1", "nb1")[0]["title"] == "Ohm's Law"
    assert workspace_service.delete_note("u1", "nb1", note["id"]) is True
    assert workspace_service.list_notes("u1", "nb1") == []


def test_workspace_routes_are_registered():
    routes = {route.path for route in main.app.routes}
    assert "/api/chat/workspace" in routes
    assert "/api/notebooks/{notebook_id}/sessions" in routes
    assert "/api/notebooks/{notebook_id}/notes" in routes
