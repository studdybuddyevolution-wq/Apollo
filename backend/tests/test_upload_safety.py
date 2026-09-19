from concurrent.futures import ThreadPoolExecutor

import rag_service


def _isolated_rag(monkeypatch, tmp_path):
    monkeypatch.setattr(rag_service, "STORE", None)
    monkeypatch.setattr(rag_service, "DATA_DIR", tmp_path)
    monkeypatch.setattr(rag_service, "NOTEBOOKS_FILE", tmp_path / "notebooks.json")


def test_source_filename_sanitizes_path_components(monkeypatch, tmp_path):
    _isolated_rag(monkeypatch, tmp_path)
    assert rag_service.sanitize_source_filename("../../notes.txt") == "notes.txt"
    assert rag_service.sanitize_source_filename(r"..\notes.txt") == "notes.txt"


def test_concurrent_same_name_uploads_get_distinct_source_names(monkeypatch, tmp_path):
    _isolated_rag(monkeypatch, tmp_path)
    notebook = rag_service.create_notebook("u1", "Test")

    def upload(index):
        return rag_service.add_source(
            "u1",
            notebook["id"],
            "../../report.txt",
            f"content-{index}".encode(),
            replace_existing=False,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(upload, range(8)))

    names = [result["name"] for result in results]
    assert len(set(names)) == 8
    assert "report.txt" in names
    assert "report (1).txt" in names

    chunks = rag_service.get_notebook_chunks("u1", notebook["id"])
    assert {item["source"] for item in chunks} == set(names)


def test_failed_parse_keeps_complete_payload_for_retry_and_cleans_claim(monkeypatch, tmp_path):
    _isolated_rag(monkeypatch, tmp_path)
    notebook = rag_service.create_notebook("u1", "Test")
    original = rag_service._extract_text

    def fail(*args, **kwargs):
        raise ValueError("unsupported source")

    monkeypatch.setattr(rag_service, "_extract_text", fail)

    try:
        rag_service.add_source(
            "u1",
            notebook["id"],
            "notes.txt",
            b"retry me",
            replace_existing=False,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("expected parse failure")
    finally:
        monkeypatch.setattr(rag_service, "_extract_text", original)

    metadata = rag_service.get_source_metadata("u1", notebook["id"], "notes.txt")
    assert metadata["status"] == "failed"
    assert rag_service.get_source_payload("u1", notebook["id"], "notes.txt") == b"retry me"
    claims = tmp_path / "notebooks" / notebook["id"] / ".claims"
    assert not list(claims.glob("*.claim"))
