import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import router
from app.core.config import settings
from app.core.logging import setup_logging, request_id_context
from app.exceptions.handlers import register_exception_handlers

logger = logging.getLogger("app.main")

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
)

setup_logging()
register_exception_handlers(app)

# CORS — allow the Next.js frontend to call this API from a different origin.
if settings.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(router)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id

    with request_id_context(request_id):
        response = await call_next(request)

    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/")
def root():
    logger.info("Root endpoint hit")
    return {
        "message": "AetherLab Backend Running",
    }
