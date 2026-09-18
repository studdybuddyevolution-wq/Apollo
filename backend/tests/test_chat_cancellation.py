from types import SimpleNamespace

import main
import phase1_routes


def test_workspace_stream_persists_partial_response_on_client_cancel(monkeypatch):
    appended = []

    monkeypatch.setattr(phase1_routes, "_REGISTERED_APPS", phase1_routes._REGISTERED_APPS)
    monkeypatch.setattr(phase1_routes, "_check_notebook", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        phase1_routes,
        "get_session",
        lambda user_id, notebook_id, session_id: {"id": session_id} if session_id else None,
    )
    monkeypatch.setattr(
        phase1_routes,
        "create_session",
        lambda user_id, notebook_id: {"id": "sess_1", "title": "New chat"},
    )
    monkeypatch.setattr(
        phase1_routes,
        "append_message",
        lambda user_id, notebook_id, session_id, role, content, model=None, sources=None: appended.append(
            {"role": role, "content": content, "model": model, "sources": sources}
        ),
    )
    monkeypatch.setattr(
        phase1_routes,
        "build_context",
        lambda *args, **kwargs: {"context": "source context", "full_sources": ["notes.txt"]},
    )
    monkeypatch.setattr(main, "_check_rate_limit", lambda key: (True, 0))
    monkeypatch.setattr(
        main,
        "_stream_model",
        lambda *args, **kwargs: iter(
            [
                phase1_routes._event({"type": "start", "model": "test"}),
                phase1_routes._event({"type": "token", "text": "partial answer"}),
            ]
        ),
    )

    app = SimpleNamespace()

    # Registering adds the route to a real FastAPI app; use a minimal fake app
    # that captures the function so the test only exercises the generator path.
    captured = {}

    class FakeApp:
        def post(self, path):
            def decorator(fn):
                captured[path] = fn
                return fn
            return decorator

        def get(self, path):
            return lambda fn: fn

        def patch(self, path):
            return lambda fn: fn

        def delete(self, path):
            return lambda fn: fn

    phase1_routes.register(FakeApp())

    request = phase1_routes.Phase1ChatRequest(
        messages=[phase1_routes.Phase1ChatMessage(role="user", content="Explain")],
        notebook_id="nb1",
        user_id="u1",
    )
    response = captured["/api/chat/workspace"](request, SimpleNamespace(client=SimpleNamespace(host="127.0.0.1")))
    iterator = response.body_iterator

    next(iterator)  # session event
    next(iterator)  # start event
    iterator.close()

    assert [item["role"] for item in appended] == ["user", "assistant"]
    assert appended[-1]["content"] == "partial answer"
