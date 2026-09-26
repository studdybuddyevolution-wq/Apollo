from types import SimpleNamespace

import asyncio
import os

import pytest

import phase3_common
import phase3_routes
import transformations


def test_gemini_retries_primary_then_falls_back(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    calls = []
    sleeps = []

    class FakeResponse:
        text = "fallback-success"

    class FakeModels:
        def generate_content(self, *, model, contents, config):
            calls.append(model)
            if len(calls) <= 2:
                raise RuntimeError("503 UNAVAILABLE high demand")
            return FakeResponse()

    class FakeClient:
        def __init__(self):
            self.models = FakeModels()

    def factory(api_key, timeout_ms):
        assert api_key == "test-key"
        assert timeout_ms == 9000
        return FakeClient()

    text, model, attempts = phase3_common.generate_gemini_text(
        "prompt",
        model_chain=["gemini-3.8-flash", "gemini-3.7-flash"],
        max_models=2,
        retry_primary_once=True,
        request_timeout_ms=9000,
        client_factory=factory,
        sleep_fn=sleeps.append,
    )

    assert text == "fallback-success"
    assert model == "gemini-3.7-flash"
    assert attempts == 3
    assert calls == ["gemini-3.8-flash", "gemini-3.8-flash", "gemini-3.7-flash"]
    assert sleeps == [0.8]


def test_gemini_does_not_retry_same_model_after_rate_limit():
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        calls = []

        class FakeResponse:
            text = "quota-fallback-success"

        class FakeModels:
            def generate_content(self, *, model, contents, config):
                calls.append(model)
                if model == "gemini-3.5-flash-lite":
                    raise RuntimeError("429 RESOURCE_EXHAUSTED rate limit exceeded")
                return FakeResponse()

        class FakeClient:
            def __init__(self):
                self.models = FakeModels()

        sleeps = []
        text, model, attempts = phase3_common.generate_gemini_text(
            "prompt",
            model_chain=["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"],
            max_models=2,
            retry_primary_once=True,
            client_factory=lambda *_: FakeClient(),
            sleep_fn=sleeps.append,
        )

        assert text == "quota-fallback-success"
        assert model == "gemini-3.1-flash-lite"
        assert attempts == 2
        assert calls == ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
        assert sleeps == []
    finally:
        monkeypatch.undo()


def test_default_gemini_chain_prefers_flash_lite_models(monkeypatch):
    monkeypatch.delenv("APOLLO_GEMINI_FALLBACK_MODELS", raising=False)
    monkeypatch.delenv("APOLLO_WEB_SYNTHESIS_MODEL", raising=False)

    chain = phase3_common.gemini_model_chain(max_models=3)

    assert chain == [
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3.6-flash",
    ]

def test_friendly_gemini_error_hides_provider_details():
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        class FakeModels:
            def generate_content(self, **kwargs):
                raise RuntimeError("503 UNAVAILABLE This model is currently experiencing high demand")
        class FakeClient:
            def __init__(self):
                self.models = FakeModels()
        with pytest.raises(phase3_common.FriendlyGeminiError) as exc:
            phase3_common.generate_gemini_text(
                "prompt",
                model_chain=["gemini-3.8-flash"],
                max_models=1,
                retry_primary_once=False,
                client_factory=lambda *_: FakeClient(),
            )
        assert "UNAVAILABLE" not in str(exc.value)
        assert "high demand" not in str(exc.value).lower()
        assert "fallback models" in str(exc.value)
    finally:
        monkeypatch.undo()


def test_transformations_include_expanded_types():
    expected = {
        "summary", "key_concepts", "faq", "outline", "glossary", "quiz",
        "study_guide", "timeline", "compare_contrast", "explain_simply", "misconceptions",
    }
    assert expected.issubset(transformations.TRANSFORMATION_PROMPTS)


def test_studio_slide_output_is_source_scoped(monkeypatch):
    monkeypatch.setattr(phase3_routes, "get_notebook", lambda user_id, notebook_id: {"id": notebook_id})
    monkeypatch.setattr(phase3_routes, "get_notebook_chunks", lambda *args, **kwargs: [{"source": "biology.md", "text": "Cells contain DNA."}])
    monkeypatch.setattr(phase3_routes, "build_context", lambda *args, **kwargs: {"context": "[Source 1: biology.md]\nCells contain DNA.", "sources": ["biology.md"]})
    monkeypatch.setattr(phase3_routes, "STORE", None)
    monkeypatch.setattr(
        phase3_routes,
        "generate_gemini_text",
        lambda *args, **kwargs: (
            '{"title":"Cell Biology","slides":[{"title":"DNA","bullets":["Cells contain DNA."],"speaker_notes":"Use the source wording.","source_refs":["biology.md"]}]}',
            "gemini-3.8-flash",
            1,
        ),
    )

    request = phase3_routes.StudioGenerateRequest(tool="slides", active_sources=["biology.md"], user_id="u1")
    result = phase3_routes._studio_generate(request, "nb1")

    assert result["tool"] == "slides"
    assert result["sources"] == ["biology.md"]
    assert result["data"]["slides"][0]["source_refs"] == ["biology.md"]
