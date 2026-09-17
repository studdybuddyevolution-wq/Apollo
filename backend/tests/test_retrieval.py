import rag_service


def test_retrieve_hybrid_preserves_notebook_scope(monkeypatch):
    chunks = [
        {"id": "1", "source": "physics.pdf", "text": "Newton described force and acceleration."},
        {"id": "2", "source": "history.pdf", "text": "The French Revolution changed European politics."},
    ]
    monkeypatch.setattr(rag_service, "get_notebook", lambda user_id, notebook_id: {"id": notebook_id})
    monkeypatch.setattr(rag_service, "get_notebook_chunks", lambda user_id, notebook_id, source_names=None: [c for c in chunks if not source_names or c["source"] in source_names])
    monkeypatch.setattr(rag_service, "STORE", None)

    results = rag_service.retrieve_hybrid("u1", "nb1", "force acceleration", top_k=5, source_names=["physics.pdf"])

    assert results
    assert all(result["source"] == "physics.pdf" for result in results)
    assert all("rrf_score" in result for result in results)
    assert results[0]["bm25_score"] > 0


def test_hybrid_falls_back_to_bm25_without_vector_store(monkeypatch):
    chunks = [{"id": "1", "source": "notes.txt", "text": "Mitosis creates two daughter cells."}]
    monkeypatch.setattr(rag_service, "get_notebook", lambda user_id, notebook_id: {"id": notebook_id})
    monkeypatch.setattr(rag_service, "get_notebook_chunks", lambda *args, **kwargs: chunks)
    monkeypatch.setattr(rag_service, "STORE", None)
    results = rag_service.retrieve("u1", "nb1", "daughter cells", top_k=3)
    assert results[0]["retrieval_method"] == "bm25"
