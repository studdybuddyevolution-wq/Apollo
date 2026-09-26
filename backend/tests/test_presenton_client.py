from __future__ import annotations

from unittest.mock import Mock

import presenton_client


def test_presenton_slide_markdown_is_bounded():
    markdown = presenton_client._slide_markdown(
        {
            "title": "Cell structure",
            "bullets": [f"point-{index}" for index in range(10)],
        }
    )
    assert markdown.startswith("# Cell structure")
    assert markdown.count("\n- ") == 6


def test_generate_deck_maps_presenton_paths(monkeypatch):
    monkeypatch.setenv("MARKLYF_PRESENTON_URL", "http://presenton.test")
    monkeypatch.setenv("MARKLYF_PRESENTON_API_KEY", "sk-test")

    response = Mock()
    response.ok = True
    response.json.return_value = {
        "presentation_id": "deck-123",
        "path": "/app_data/deck-123/Test_Deck.pptx",
        "edit_path": "/presentation?id=deck-123",
    }

    post = Mock(return_value=response)
    monkeypatch.setattr(presenton_client.requests, "post", post)

    result = presenton_client.generate_deck(
        title="Test Deck",
        slides=[
            {"title": "Intro", "bullets": ["One", "Two"]},
            {"title": "Summary", "bullets": ["Three"]},
        ],
    )

    assert result["presentation_id"] == "deck-123"
    assert result["pptx_url"] == "http://presenton.test/app_data/deck-123/Test_Deck.pptx"
    assert result["edit_url"] == "http://presenton.test/presentation?id=deck-123"
    assert result["filename"] == "Test_Deck.pptx"

    payload = post.call_args.kwargs["json"]
    assert payload["content"] == ""
    assert len(payload["slides_markdown"]) == 2
    assert payload["web_search"] is False
    assert payload["include_title_slide"] is False
    assert payload["export_as"] == "pptx"


def test_presenton_errors_are_normalized(monkeypatch):
    monkeypatch.setenv("MARKLYF_PRESENTON_URL", "http://presenton.test")
    monkeypatch.setenv("MARKLYF_PRESENTON_API_KEY", "sk-test")

    response = Mock()
    response.ok = False
    response.status_code = 503
    response.text = "service unavailable"

    monkeypatch.setattr(presenton_client.requests, "post", Mock(return_value=response))

    try:
        presenton_client.generate_deck(
            title="Test",
            slides=[{"title": "Intro", "bullets": ["One"]}],
        )
    except presenton_client.PresentonError as exc:
        assert "HTTP 503" in str(exc)
        assert "service unavailable" in str(exc)
    else:
        raise AssertionError("PresentonError was not raised")


def test_presenton_cloud_is_not_allowed(monkeypatch):
    monkeypatch.setenv("MARKLYF_PRESENTON_URL", "https://presenton.ai")
    monkeypatch.setenv("MARKLYF_PRESENTON_API_KEY", "sk-test")
    assert presenton_client.is_configured() is False
