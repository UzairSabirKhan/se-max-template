"""Request body size limit as raw ASGI middleware.

Checking the Content-Length header alone is not enough: a chunked upload has no such header.
This counts the bytes actually received and answers 413 as soon as the limit is passed.
"""

from __future__ import annotations

import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class BodySizeLimit:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        for name, value in scope.get("headers", []):
            if name == b"content-length" and value.isdigit() and int(value) > self.max_bytes:
                await _send_413(send)
                return

        received = 0
        started = False   # the app has begun its own response
        refused = False   # we answered 413 ourselves

        async def counting_receive() -> Message:
            nonlocal received, refused
            if refused:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes and not started:
                    # Answer now, then tell the app the client is gone. (Raising here would be
                    # swallowed by FastAPI's body parser and turned into a generic 400.)
                    refused = True
                    await _send_413(send)
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal started
            if refused:
                return  # we already answered; drop whatever the app tries to send
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, guarded_send)
        except Exception:
            if not refused:
                raise  # a real error: let the normal error handling answer it


async def _send_413(send: Send) -> None:
    body = json.dumps({"error": "too_large", "message": "Request body is too large"}).encode()
    await send({"type": "http.response.start", "status": 413,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})
