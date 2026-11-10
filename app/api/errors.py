"""One error shape for the whole API: {"error": code, "message": text[, "issues": [...]]}.

Never a 500 with a stack trace (NFR-04): unexpected errors are logged and answered with a
generic message.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("scrapeonce")


class ApiError(Exception):
    def __init__(self, status: int, error: str, message: str, issues: list[dict] | None = None,
                 extra: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.body: dict[str, Any] = {"error": error, "message": message}
        if issues is not None:
            self.body["issues"] = issues
        if extra:
            self.body.update(extra)


def invalid_flow(issues: list[dict]) -> ApiError:
    first = issues[0]["message"] if issues else "The flow is not valid"
    return ApiError(422, "invalid_flow", first, issues=issues)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(exc.body, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _bad_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        issues = [
            {"node_id": None, "path": ".".join(str(p) for p in e["loc"] if p != "body"),
             "message": e["msg"].removeprefix("Value error, ")}
            for e in exc.errors()
        ]
        message = issues[0]["message"] if issues else "Invalid request"
        return JSONResponse({"error": "invalid_request", "message": message, "issues": issues},
                            status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed", 413: "too_large"}.get(exc.status_code, "http_error")
        return JSONResponse({"error": code, "message": str(exc.detail)}, status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        log.exception("Unhandled error", exc_info=exc)
        return JSONResponse({"error": "internal_error", "message": "Something went wrong. Please try again."},
                            status_code=500)
