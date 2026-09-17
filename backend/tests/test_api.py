from fastapi.testclient import TestClient

import main


client = TestClient(main.app)


def test_health_exposes_retrieval_capabilities(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "apollo-api"
    assert "embedding_model" in body
    assert "pgvector" in body


def test_mindmap_requires_existing_notebook(monkeypatch):
    monkeypatch.setattr(main, "get_notebook", lambda user_id, notebook_id: None)
    response = client.post("/api/notebooks/nb-missing/mindmap", json={"user_id": "u1"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Notebook not found"
