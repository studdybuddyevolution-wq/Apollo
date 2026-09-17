from types import SimpleNamespace

import pytest

import main


class _Rendered:
    kind = "mermaid"
    source_code = "flowchart TD\nA[Cells] --> B[DNA]"
    svg_bytes = b"<svg xmlns=\"http://www.w3.org/2000/svg\"><text>Cells</text><text>DNA</text></svg>"
    error = None


def test_mindmap_rejects_missing_indexed_sources(monkeypatch):
    monkeypatch.setattr(main, "get_notebook", lambda user_id, notebook_id: {"id": notebook_id})
    monkeypatch.setattr(main, "get_notebook_chunks", lambda *args, **kwargs: [])
    request = main.MindMapRequest(active_sources=[], user_id="u1")
    with pytest.raises(Exception) as exc:
        import asyncio
        asyncio.run(main.notebook_mindmap("nb1", request, SimpleNamespace(client=SimpleNamespace(host="test"))))
    assert "No indexed source content" in str(exc.value)


def test_mindmap_uses_server_indexed_content(monkeypatch):
    observed = {}
    monkeypatch.setattr(main, "get_notebook", lambda user_id, notebook_id: {"id": notebook_id})
    monkeypatch.setattr(main, "get_notebook_chunks", lambda *args, **kwargs: [{"source": "biology.md", "text": "Cells contain DNA."}])
    monkeypatch.setattr(main, "build_context", lambda *args, **kwargs: {"context": "[Source 1: biology.md]\nCells contain DNA."})
    monkeypatch.setattr(main, "_generate_gemini_once", lambda prompt: observed.setdefault("prompt", prompt) or "```mermaid\nflowchart TD\nA[Cells] --> B[DNA]\n```")
    monkeypatch.setattr(main, "generate_and_render", lambda text: _Rendered())
    monkeypatch.setattr(main, "content_overlap_ratio", lambda *args: 1.0)
    monkeypatch.setattr(main, "_check_rate_limit", lambda key: (True, 0))

    import asyncio
    response = asyncio.run(main.notebook_mindmap("nb1", main.MindMapRequest(active_sources=["biology.md"], user_id="u1"), SimpleNamespace(client=SimpleNamespace(host="test"))))

    assert response["verified"] is True
    assert "Cells contain DNA" in observed["prompt"]
    assert response["sources"] == ["biology.md"]
