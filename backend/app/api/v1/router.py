from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    admin,
    auth,
    client,
    compliance,
    endpoints,
    metadata_dry_run,
    portal,
    reviewer,
)

api_router = APIRouter()
api_router.include_router(endpoints.router)
api_router.include_router(compliance.router)
api_router.include_router(portal.router)
api_router.include_router(auth.router)
api_router.include_router(reviewer.router)
api_router.include_router(admin.router)
api_router.include_router(client.router)
api_router.include_router(metadata_dry_run.router)
