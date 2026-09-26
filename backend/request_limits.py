"""Raw ASGI request-body limits for Apollo.

The endpoint-level upload limit remains the final defense for uploaded file
bytes. This middleware protects the application before FastAPI parses a large
multipart request, including requests that omit or falsify Content-Length.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

DEFAULT_MAX_UPLOAD_BYTES = 25 * 1024 * 1024
REQUEST_BODY_OVERHEAD_BYTES = 512 * 1024


class RequestBodyTooLarge(Exception):
    """Internal control-flow exception raised when streamed body bytes exceed the limit."""


def get_max_upload_bytes() -> int:
    """Read the configured upload limit, safely falling back on bad values."""
    raw = os.getenv("APOLLO_MAX_UPLOAD_BYTES", "").strip()
    try:
        value = int(raw) if raw else DEFAULT_MAX_UPLOAD_BYTES
    except (TypeError, ValueError):
        value = DEFAULT_MAX_UPLOAD_BYTES
    if value <= 0:
        value = DEFAULT_MAX_UPLOAD_BYTES
    return value


def get_max_request_body_bytes() -> int:
    """Allow the configured file limit plus a bounded multipart envelope."""
    return get_max_upload_bytes() + REQUEST_BODY_OVERHEAD_BYTES


class RequestBodyLimitMiddleware:
    """Reject oversized HTTP request bodies at the raw ASGI layer."""

    def __init__(self, app: ASGIApp, max_body_size: int) -> None:
        self.app = app
        self.max_body_size = max(1, int(max_body_size))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        content_length = headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.max_body_size:
                    await _send_413(send, self.max_body_size)
                    return
            except ValueError:
                # Malformed Content-Length is not trusted; enforce the
                # limit while the body streams in instead.
                pass

        total_size = 0
        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        async def receive_wrapper() -> Message:
            nonlocal total_size
            message = await receive()
            if message["type"] == "http.request":
                total_size += len(message.get("body") or b"")
                if total_size > self.max_body_size:
                    raise RequestBodyTooLarge()
            return message

        try:
            await self.app(scope, receive_wrapper, send_wrapper)
        except RequestBodyTooLarge:
            if not response_started:
                await _send_413(send, self.max_body_size)
            # If the application already started a response, ASGI does not
            # allow us to send a second response. Let the connection close.


async def _send_413(send: Send, max_body_size: int) -> None:
    detail = (
        '{"detail":"Request body exceeds Apollo\'s maximum upload size",'
        f'"max_body_bytes":{max_body_size}}}'
    )
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"cache-control", b"no-store"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": detail.encode("utf-8")})
