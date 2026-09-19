import asyncio

import pytest

import error_classifier
import jobs


@pytest.mark.parametrize(
    "exc",
    [
        ValueError("unsupported file format"),
        ValueError("No readable text found in source"),
        RuntimeError("Could not extract content from this source. The URL may be unreachable."),
    ],
)
def test_permanent_source_failures_do_not_retry(exc):
    retryable, status_code, _message = error_classifier.classify_source_error(exc)
    assert retryable is False
    assert status_code == 400


@pytest.mark.parametrize(
    "exc",
    [
        TimeoutError("provider timed out"),
        RuntimeError("HTTP 503 service unavailable"),
        RuntimeError("429 rate limit exceeded"),
    ],
)
def test_transient_source_failures_are_retryable(exc):
    assert error_classifier.is_retryable_source_error(exc) is True


class FakeStore:
    def vector_available(self):
        return True

    def list_unembedded_chunks(self, notebook_id, source_name):
        return [{"id": "chunk-1", "source": source_name or "source.txt", "text": "hello"}]

    def upsert_chunk_embedding(self, chunk_id, embedding):
        return True

    def get_job(self, job_id):
        return None

    def create_job(self, record):
        return record

    def update_job(self, job_id, **updates):
        return None

    def upsert_source_status(self, *args, **kwargs):
        return None


def test_embedding_job_retries_transient_failure(monkeypatch):
    fake_store = FakeStore()
    monkeypatch.setattr(jobs, "STORE", fake_store)
    calls = {"embed": 0}

    async def flaky_embed(texts):
        calls["embed"] += 1
        if calls["embed"] == 1:
            raise TimeoutError("provider timed out")
        return [[0.1, 0.2]]

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(jobs, "embed_texts", flaky_embed)
    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    job = jobs.Job(id="job_retry", type="embed_source", notebook_id="nb1", created_at=jobs._now())
    asyncio.run(jobs._embed_job(job, "source.txt"))

    assert calls["embed"] == 2
    assert job.status == "completed"
    assert job.progress == 100


def test_embedding_job_does_not_retry_permanent_failure(monkeypatch):
    fake_store = FakeStore()
    monkeypatch.setattr(jobs, "STORE", fake_store)
    calls = {"embed": 0}

    async def permanent_failure(_texts):
        calls["embed"] += 1
        raise ValueError("unsupported embedding input")

    monkeypatch.setattr(jobs, "embed_texts", permanent_failure)

    job = jobs.Job(id="job_no_retry", type="embed_source", notebook_id="nb1", created_at=jobs._now())
    with pytest.raises(ValueError):
        asyncio.run(jobs._embed_job(job, "source.txt"))

    assert calls["embed"] == 1
    assert job.status == "failed"
