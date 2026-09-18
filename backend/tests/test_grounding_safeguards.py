import json

import pytest

import main
import phase3_routes
from diagrams import content_overlap_ratio


def test_text_overlap_uses_plain_prose_words():
    source = "Cells contain DNA and DNA stores genetic information."
    assert content_overlap_ratio("text", "Cells contain DNA.", source) > 0.5
    assert content_overlap_ratio("text", "Quantum mechanics describes a wavefunction.", source) < 0.5


def _events_to_payloads(events):
    payloads = []
    for event in events:
        if not event.startswith("data: "):
            continue
        payloads.append(json.loads(event.split("data: ", 1)[1]))
    return payloads


def test_study_report_retries_when_overlap_is_weak(monkeypatch):
    context = "[Source: biology.md]\nCells contain DNA. DNA is genetic material in cells."
    calls = []

    responses = [
        (
            '{"title":"Study Report","summary":"Mars has two moons.","sections":[{"heading":"Mars","points":["Phobos and Deimos orbit Mars."]}],"exam_questions":[]}',
            "model-1",
        ),
        (
            '{"title":"Study Report","summary":"Cells contain DNA.","sections":[{"heading":"DNA","points":["DNA is genetic material in cells."]}],"exam_questions":[]}',
            "model-2",
        ),
    ]

    monkeypatch.setattr(
        phase3_routes,
        "_context_or_400",
        lambda *args, **kwargs: (context, ["biology.md"]),
    )
    monkeypatch.setattr(
        phase3_routes,
        "_safe_generation",
        lambda prompt, **kwargs: (calls.append(prompt) or responses.pop(0)),
    )
    monkeypatch.setattr(phase3_routes, "_persist_output", lambda *args, **kwargs: {})

    request = phase3_routes.StudioGenerateRequest(
        tool="report",
        active_sources=["biology.md"],
        user_id="u1",
    )
    result = phase3_routes._studio_generate(request, "nb1")

    assert len(calls) == 2
    assert "Your previous report included claims not supported" in calls[1]
    assert result["verified"] is True
    assert result["overlap_ratio"] >= 0.5
    assert result["warning"] is None
    assert "Cells contain DNA." in result["markdown"]


@pytest.mark.parametrize(
    ("answer", "expected_verified"),
    [
        ("DNA is the genetic material in cells. It stores genetic information in cells, which is the main point in the retrieved evidence.", True),
        ("Quantum mechanics describes a wavefunction for physical systems.", False),
    ],
)
def test_deep_search_emits_grounding_check(monkeypatch, answer, expected_verified):
    monkeypatch.setenv("APOLLO_GROUNDING_MIN_OVERLAP", "0.4")
    plan = {
        "topic": "DNA",
        "outline": ["DNA"],
        "verification": {
            "web_sources": 1,
            "notebook_chunks": 1,
            "high_authority_sources": 1,
        },
        "evidence": [{"source": "biology.md", "text": "DNA is genetic material in cells."}],
        "web_sources": [{"title": "Biology source", "url": "https://example.test", "index": 1}],
        "plan": {},
    }

    monkeypatch.setattr(main, "run_hybrid_research", lambda **kwargs: plan)
    monkeypatch.setattr(main, "format_evidence", lambda evidence: "DNA is genetic material in cells.")
    monkeypatch.setattr(main, "build_synthesis_instruction", lambda **kwargs: "Stay grounded.")
    monkeypatch.setattr(main, "is_detailed_request", lambda question: False)
    monkeypatch.setattr(
        main,
        "_stream_gemini_resilient",
        lambda **kwargs: iter(
            [
                main._event({"type": "start", "model": "test"}),
                main._event({"type": "token", "text": answer}),
                main._event({"type": "done"}),
            ]
        ),
    )

    request = main.ChatRequest(
        messages=[main.ChatMessage(role="user", content="What is DNA?")],
        notebook_id="nb1",
        user_id="u1",
        web_enabled=True,
        research_mode="deep",
    )

    events = _events_to_payloads(main._stream_deep_research(request, "SYSTEM", ""))
    check = [event for event in events if event.get("type") == "grounding_check"]

    assert len(check) == 1
    assert check[0]["verified"] is expected_verified
    if expected_verified:
        assert check[0]["warning"] is None
    else:
        assert check[0]["warning"]
