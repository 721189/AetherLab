from fastapi import APIRouter

from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.projects import router as projects_router
from app.api.v1.endpoints.agents import router as agents_router
from app.api.v1.endpoints.conversations import router as conversations_router
from app.api.v1.endpoints.environmental import router as environmental_router

v1_router = APIRouter(prefix="/api/v1")

v1_router.include_router(auth_router)
v1_router.include_router(projects_router)
v1_router.include_router(agents_router)
v1_router.include_router(conversations_router)
v1_router.include_router(environmental_router)