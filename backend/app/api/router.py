from fastapi import APIRouter

from app.api.v1.router import v1_router

router = APIRouter()

router.include_router(v1_router)