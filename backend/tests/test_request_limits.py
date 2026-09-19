from types import SimpleNamespace

import pytest

import main
from request_limits import (
    DEFAULT_MAX_UPLOAD_BYTES,
    REQUEST_BODY_OVERHEAD_BYTES,
    RequestBodyLimitMiddleware,
    get_max_request_body_bytes,
    get_max_upload_bytes,
)


async def _echo(scope, receive, send):
    body = bytearray()
    more = True
    while more:
        message = await receive()
        body.extend(message.get("body") or b"")
        more = message.get("more_body", False)
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": str(len(body)).encode()})


class Receive:
    def __init__(self, chunks):
        self.chunks = list(chunks)

    async def __call__(self):
        if not self.chunks:
            return {"type": "http.request", "body": b"", "more_body": False}
        chunk = self.chunks.pop(0)
        return {"type": "http.request", "body": chunk, "more_body": bool(self.chunks)}


class Send:
    def __init__(self):
        self.messages = []

    async def __call__(self, message):
        self.messages.append(message)

    @property
    def status(self):
        return next((m["status"] for m in self.messages if m["type"] == "http.response.start"), None)


def scope(headers=None):
    return {
        "type": "http",
        "method": "POST",
        "path": "/upload",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
    }


def test_upload_limit_config_falls_back_safely(monkeypatch):
    monkeypatch.delenv("APOLLO_MAX_UPLOAD_BYTES", raising=False)
    assert get_max_upload_bytes() == DEFAULT_MAX_UPLOAD_BYTES
    assert get_max_request_body_bytes() == DEFAULT_MAX_UPLOAD_BYTES + REQUEST_BODY_OVERHEAD_BYTES

    monkeypatch.setenv("APOLLO_MAX_UPLOAD_BYTES", "bad")
    assert get_max_upload_bytes() == DEFAULT_MAX_UPLOAD_BYTES

    monkeypatch.setenv("APOLLO_MAX_UPLOAD_BYTES", "0")
    assert get_max_upload_bytes() == DEFAULT_MAX_UPLOAD_BYTES

    monkeypatch.setenv("APOLLO_MAX_UPLOAD_BYTES", "-1")
    assert get_max_upload_bytes() == DEFAULT_MAX_UPLOAD_BYTES


@pytest.mark.asyncio
async def test_content_length_rejects_before_app_runs():
    called = False

    async def inner(scope, receive, send):
        nonlocal called
        called = True
        await _echo(scope, receive, send)

    app = RequestBodyLimitMiddleware(inner, 10)
    sender = Send()
    await app(scope({"content-length": "11"}), Receive([b"x" * 11]), sender)

    assert sender.status == 413
    assert called is False


@pytest.mark.asyncio
async def test_exact_limit_passes():
    sender = Send()
    app = RequestBodyLimitMiddleware(_echo, 10)
    await app(scope({"content-length": "10"}), Receive([b"x" * 10]), sender)

    assert sender.status == 200


@pytest.mark.asyncio
async def test_one_byte_over_limit_fails():
    sender = Send()
    app = RequestBodyLimitMiddleware(_echo, 10)
    await app(scope({"content-length": "11"}), Receive([b"x" * 11]), sender)

    assert sender.status == 413


@pytest.mark.asyncio
async def test_chunked_body_is_still_limited():
    sender = Send()
    app = RequestBodyLimitMiddleware(_echo, 10)
    await app(scope(), Receive([b"a" * 5, b"b" * 5, b"c" * 1]), sender)

    assert sender.status == 413


@pytest.mark.asyncio
async def test_malformed_content_length_falls_back_to_streaming_check():
    sender = Send()
    app = RequestBodyLimitMiddleware(_echo, 10)
    await app(scope({"content-length": "not-a-number"}), Receive([b"x" * 11]), sender)

    assert sender.status == 413


@pytest.mark.asyncio
async def test_non_http_scope_passes_through():
    called = []

    async def inner(scope, receive, send):
        called.append(scope["type"])

    app = RequestBodyLimitMiddleware(inner, 10)
    await app({"type": "lifespan"}, Receive([]), Send())

    assert called == ["lifespan"]


def test_cors_wraps_request_limit_middleware():
    classes = [getattr(item.cls, "__name__", "") for item in main.app.user_middleware]
    assert classes.index("CORSMiddleware") < classes.index("RequestBodyLimitMiddleware")
