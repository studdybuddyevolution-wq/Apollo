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
