import json

import rag_service


def test_add_source_persists_chunk_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(rag_service, "DATA_DIR", tmp_path)
    monkeypatch.setattr(rag_service, "NOTEBOOKS_FILE", tmp_path / "notebooks.json")
    monkeypatch.setattr(rag_service, "STORE", None)

    notebook = rag_service.create_notebook("u1", "Biology")
    result = rag_service.add_source("u1", notebook["id"], "notes.md", b"# Cells\nCells are the basic unit of life.\n\n# DNA\nDNA stores genetic information.")

    assert result["status"] == "indexed"
    chunks_path = tmp_path / "notebooks" / notebook["id"] / "chunks.json"
    chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    assert chunks
    assert chunks[0]["chunk_index"] == 0
    assert chunks[0]["content_type"] == "markdown"
