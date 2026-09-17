import asyncio

import jobs


def test_embedding_job_completes_in_bm25_only_mode(monkeypatch):
    monkeypatch.setattr(jobs, "STORE", None)
    job = asyncio.run(_enqueue_and_wait())
    assert job["status"] == "completed"
    assert job["progress"] == 100


async def _enqueue_and_wait():
    result = await jobs.enqueue_embedding_job("nb1", "u1", "notes.txt")
    assert result["status"] == "queued"
    for _ in range(20):
        job = jobs.get_job(result["id"])
        if job and job["status"] == "completed":
            return job
        await asyncio.sleep(0)
    raise AssertionError("job did not complete")
