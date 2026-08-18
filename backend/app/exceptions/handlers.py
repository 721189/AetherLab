import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.exceptions.base import (
    AppError,
    DatabaseError,
)

logger = logging.getLogger("app.exceptions")


def register_exception_handlers(app: FastAPI) -> None:
    """Register all global exception handlers on the FastAPI app."""

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail,
                "error": exc.code,
            },
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(
        request: Request, exc: IntegrityError
    ) -> JSONResponse:
        logger.warning("IntegrityError: %s", exc.orig)
        return JSONResponse(
            status_code=409,
            content={
                "detail": "Resource conflict",
                "error": "conflict_error",
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_error_handler(
        request: Request, exc: SQLAlchemyError
    ) -> JSONResponse:
        logger.exception("Unhandled database error", exc_info=exc)
        db_error = DatabaseError()
        return JSONResponse(
            status_code=db_error.status_code,
            content={
                "detail": db_error.detail,
                "error": db_error.code,
            },
        )
