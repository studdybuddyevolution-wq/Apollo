from types import SimpleNamespace

import context_builder
import research_engine
import source_ingestion


def test_deep_research_honors_explicit_sections():
    question = """Explain Apollo.
1. Architecture
2. Retrieval pipeline
3. Deployment concerns
"""
    sections = research_engine.extract_requested_sections(question)
    assert sections == ["Architecture", "Retrieval pipeline", "Deployment concerns"]
    assert research_engine.build_outline("conceptual", question) == sections
    plan = research_engine.decompose_query(question, "conceptual")
    assert [item["aspect"] for item in plan] == sections


def test_summary_source_mode_reads_only_saved_summaries(monkeypatch):
    monkeypatch.setattr(context_builder, "retrieve_hybrid", lambda *args, **kwargs: [])
    monkeypatch.setattr(context_builder, "get_notebook_chunks", lambda *args, **kwargs: [])
    monkeypatch.setattr(context_builder, "format_context", lambda results, **kwargs: " | ".join(item["text"] for item in results))
    monkeypatch.setattr(context_builder, "token_count", lambda value: len(str(value).split()))
    monkeypatch.setattr(
        context_builder,
        "STORE",
        SimpleNamespace(
            list_insights=lambda notebook_id: [
                {"source_name": "chapter.pdf", "insight_type": "summary", "content": "Photosynthesis converts light energy."},
                {"source_name": "chapter.pdf", "insight_type": "quiz", "content": "What is photosynthesis?"},
                {"source_name": "other.pdf", "insight_type": "summary", "content": "Different source."},
            ]
        ),
    )

    built = context_builder.build_context(
        "u1",
        "nb1",
        ["chapter.pdf"],
        "photosynthesis",
        source_modes={"chapter.pdf": "summary"},
        include_insights=True,
    )

    assert "Photosynthesis converts light energy." in built["context"]
    assert "What is photosynthesis?" not in built["context"]
    assert built["summary_sources"] == ["chapter.pdf"]
    assert built["full_sources"] == []


def test_refresh_url_source_reuses_existing_source_name(monkeypatch):
    monkeypatch.setattr(
        source_ingestion,
        "get_source_metadata",
        lambda user_id, notebook_id, source_name: {"kind": "url", "source_url": "https://example.com/page"},
    )
    monkeypatch.setattr(source_ingestion, "_validate_public_url", lambda url: ("93.184.216.34", url))
    monkeypatch.setattr(source_ingestion, "_download", lambda ip, url: (b"<html><title>Example</title><p>Hello world</p></html>", "text/html"))
    monkeypatch.setattr(source_ingestion, "_html_to_text", lambda raw: ("Example", "Hello world"))
    monkeypatch.setattr(
        source_ingestion,
        "add_source",
        lambda user_id, notebook_id, filename, payload, **kwargs: {
            "name": filename,
            "kind": kwargs["kind"],
            "source_url": kwargs["source_url"],
            "payload": payload,
        },
    )

    result = source_ingestion.refresh_url_source("u1", "nb1", "Example [URL].txt")

    assert result["name"] == "Example [URL].txt"
    assert result["kind"] == "url"
    assert result["source_url"] == "https://example.com/page"
    assert b"Hello world" in result["payload"]


def test_outline_section_boundaries():
    fewer = "Explain Apollo with:\n1. Architecture\n2. Retrieval\n3. Deployment"
    exactly_five = "Research this:\n1. One\n2. Two\n3. Three\n4. Four\n5. Five"
    more_than_five = "Research this:\n1. One\n2. Two\n3. Three\n4. Four\n5. Five\n6. Six\n7. Seven\n8. Eight\n9. Nine"
    too_many = "Research this:\n" + "\n".join(f"{i}. Section {i}" for i in range(1, 15))
    malformed = "Research this:"

    assert len(research_engine.build_outline("conceptual", fewer)) == 3
    assert len(research_engine.build_outline("conceptual", exactly_five)) == 5
    assert len(research_engine.build_outline("conceptual", more_than_five)) == 9
    assert len(research_engine.build_outline("conceptual", too_many)) == research_engine.MAX_RESEARCH_SECTIONS
    assert research_engine.build_outline("conceptual", malformed) == research_engine.TOPIC_TEMPLATES["conceptual"]
    assert len(research_engine.decompose_query(more_than_five, "conceptual")) == 9


def test_filesystem_source_payload_and_delete_are_not_orphaned(monkeypatch, tmp_path):
    monkeypatch.setattr("rag_service.STORE", None)
    monkeypatch.setattr("rag_service.DATA_DIR", tmp_path)
    monkeypatch.setattr("rag_service.NOTEBOOKS_FILE", tmp_path / "notebooks.json")

    notebook = __import__("rag_service").create_notebook("u1", "Test")
    result = __import__("rag_service").add_source("u1", notebook["id"], "notes.txt", b"alpha beta gamma")
    payload_path = tmp_path / "notebooks" / notebook["id"] / "payloads"
    assert any(payload_path.iterdir())

    assert __import__("rag_service").remove_source("u1", notebook["id"], "notes.txt") is True
    assert not any(payload_path.iterdir())


def test_filesystem_notebook_delete_removes_source_data(monkeypatch, tmp_path):
    rag = __import__("rag_service")
    monkeypatch.setattr(rag, "STORE", None)
    monkeypatch.setattr(rag, "DATA_DIR", tmp_path)
    monkeypatch.setattr(rag, "NOTEBOOKS_FILE", tmp_path / "notebooks.json")

    notebook = rag.create_notebook("u1", "Test")
    rag.add_source("u1", notebook["id"], "notes.txt", b"alpha beta gamma")
    notebook_dir = tmp_path / "notebooks" / notebook["id"]
    assert notebook_dir.exists()
    assert rag.delete_notebook("u1", notebook["id"]) is True
    assert not notebook_dir.exists()
