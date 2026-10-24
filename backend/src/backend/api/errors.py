"""Translate domain exceptions into HTTP responses in one place."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from backend.domain.exceptions import (
    SessionNotFoundError,
    UploadTooLargeError,
    UploadValidationError,
)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(SessionNotFoundError)
    async def _session_not_found(_request: Request, exc: SessionNotFoundError) -> JSONResponse:
        # SessionNotFoundError subclasses KeyError, whose str() adds quotes.
        detail = str(exc.args[0]) if exc.args else ""
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": detail or "Session not found"},
        )

    @app.exception_handler(UploadTooLargeError)
    async def _upload_too_large(_request: Request, exc: UploadTooLargeError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            content={"detail": str(exc)},
        )

    @app.exception_handler(UploadValidationError)
    async def _invalid_upload(_request: Request, exc: UploadValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": str(exc)},
        )
