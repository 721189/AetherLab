from fastapi import FastAPI
from backend.app.core.config import settings

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
)


@app.get("/")
def root():
    return {
        "app": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "debug": settings.DEBUG,
    }