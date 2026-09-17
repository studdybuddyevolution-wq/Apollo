import pytest
from fastapi.testclient import TestClient

import phase2_routes
from source_ingestion import _html_to_text, extract_youtube_video_id


def test_extract_youtube_video_id_variants():
    assert extract_youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    with pytest.raises(ValueError):
        extract_youtube_video_id("https://youtube.com/watch?v=bad")


def test_html_extraction_removes_script_and_keeps_title():
    title, text = _html_to_text(
        b"<html><head><title>Physics Notes</title><script>ignore()</script></head><body><h1>Current Electricity</h1><p>Resistance is opposition to current.</p></body></html>"
    )
    assert title == "Physics Notes"
    assert "Current Electricity" in text
    assert "Resistance is opposition to current." in text
    assert "ignore" not in text


def test_capabilities_route_reports_phase2_support(monkeypatch):
    monkeypatch.setattr(phase2_routes.importlib.util, "find_spec", lambda name: object() if name == "youtube_transcript_api" else None)
    phase2_routes._REGISTERED_APPS.clear()
    from fastapi import FastAPI
    app = FastAPI()
    phase2_routes.register(app)
    response = TestClient(app).get("/api/capabilities")
    assert response.status_code == 200
    body = response.json()
    assert body["source_ingestion"] == {"file": True, "url": True, "youtube": True}
    assert body["research"]["deep"] is True
