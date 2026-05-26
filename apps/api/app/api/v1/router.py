from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    admin,
    admin_notification_templates,
    auth,
    client,
    compliance,
    contact,
    endpoints,
    feedback,
    me,
    metadata_dry_run,
    portal,
    reports,
    reviewer,
    shares,
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
api_router.include_router(reports.router)
# Phase 10D — public share-consume endpoints under /api/v1/r/<token>.
api_router.include_router(shares.router)
api_router.include_router(contact.router)
api_router.include_router(feedback.router)
# Phase 7 / Slice N2 — per-user notification preferences.
api_router.include_router(me.router)
# Phase 7 / Slice N3 — admin CRUD for versioned templates.
api_router.include_router(admin_notification_templates.router)
