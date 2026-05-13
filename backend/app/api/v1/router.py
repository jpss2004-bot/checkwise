from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import compliance, endpoints, portal

api_router = APIRouter()
api_router.include_router(endpoints.router)
api_router.include_router(compliance.router)
api_router.include_router(portal.router)
