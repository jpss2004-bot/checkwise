from __future__ import annotations

import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1.router import api_router
from app.core.config import settings

log = logging.getLogger("checkwise.unhandled")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject baseline security headers on every response.

    FastAPI / Starlette do not emit HSTS, X-Frame-Options, etc. by
    default. External security scanners (Mozilla Observatory, Qualys
    SSL Labs, buyer-audit checklists) flag the omission even though
    every state-changing route is authenticated. HSTS is gated on
    non-local environments because plain ``http://localhost`` dev
    would otherwise pin the browser to HTTPS for a year and refuse
    to load the dev server.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Referrer-Policy", "strict-origin-when-cross-origin"
        )
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        # INFRA-1 — JSON API responses can carry the strictest possible
        # CSP (they execute nothing), which satisfies external scanners
        # and locks down the surface. Scoped to JSON only so it never
        # touches the Swagger ``/docs`` HTML (local-only) or inline file
        # responses. The user-facing HTML/JS CSP lives on the Vercel
        # frontend (next.config.ts), where the needed origins are known.
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("application/json"):
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
            )
        else:
            # INFRA-1 (extension) — non-JSON responses (inline PDFs, ZIP
            # streams, redirects, the default 422/500 bodies) still get the
            # non-render-blocking CSP subset, so clickjacking (frame-ancestors)
            # and <base> hijack (base-uri) are denied on every response, not
            # just JSON. ``default-src 'none'`` stays JSON-only so it never
            # blocks a legitimately served file.
            response.headers.setdefault(
                "Content-Security-Policy",
                "frame-ancestors 'none'; base-uri 'none'",
            )
        if not settings.is_local_env:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response


_HTTP_METHODS = {
    "get", "put", "post", "delete", "options", "head", "patch", "trace"
}


def _assert_critical_routes(app: FastAPI) -> None:
    """Fail boot if a deploy is missing routes the frontend depends on.

    Checks the generated OpenAPI schema rather than walking ``app.routes``
    directly. FastAPI 0.137+ / Starlette 1.3+ include sub-routers
    *lazily*: ``app.include_router(...)`` inserts a single opaque
    ``_IncludedRouter`` entry whose child routes are not flattened onto
    ``app.routes`` synchronously, so the previous flat scan reported a
    false negative for every included route (every ``/api/v1/*`` path)
    and crash-looped the deploy. ``app.openapi()`` forces full route
    resolution and reflects the real request-time routing table on every
    FastAPI version we've shipped, old and new.
    """
    critical = {
        ("get", f"{settings.API_V1_PREFIX}/portal/me"),
        ("post", f"{settings.API_V1_PREFIX}/portal/enter"),
    }
    paths = app.openapi().get("paths", {})
    registered = {
        (method.lower(), path)
        for path, operations in paths.items()
        for method in operations
        if method.lower() in _HTTP_METHODS
    }
    missing = sorted(critical - registered)
    if missing:
        rendered = ", ".join(
            f"{method.upper()} {path}" for method, path in missing
        )
        raise RuntimeError(f"Critical API route(s) not registered: {rendered}")


def create_app() -> FastAPI:
    # /docs, /redoc, /openapi.json leak the entire API surface to
    # anonymous callers. Off by default outside `CHECKWISE_ENV=local`;
    # ENABLE_API_DOCS=true is the explicit opt-in for any other tier.
    docs_on = settings.api_docs_enabled
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.API_VERSION,
        description="API base para cumplimiento documental REPSE de CheckWise.",
        openapi_url="/openapi.json" if docs_on else None,
        docs_url="/docs" if docs_on else None,
        redoc_url="/redoc" if docs_on else None,
    )

    allowed_origins = settings.cors_origins_list

    # Audit P3-03 (2026-05-25) — tightened from ``["*"]`` to explicit
    # allowlists. Permissive wildcards weren't exploitable (every
    # state-changing endpoint enforces auth) but a buyer-audit
    # rightly flags them. Headers list covers every header any
    # CheckWise frontend (admin / client / portal) actually sends —
    # ``Authorization`` for JWT, ``X-Workspace-Token`` for the legacy
    # portal token path, plus the standard fetch / form-data headers.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=[
            "Accept",
            "Accept-Language",
            "Authorization",
            "Content-Language",
            "Content-Type",
            "Origin",
            "X-Requested-With",
            "X-Workspace-Token",
        ],
        # Without this the browser hides ``Content-Disposition`` from
        # cross-origin fetch responses, so blob downloads (expediente /
        # auditoría ZIPs) silently lose the server-side filename and
        # fall back to a generic one (audit 2026-06-12).
        expose_headers=["Content-Disposition"],
    )
    app.add_middleware(SecurityHeadersMiddleware)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # CORSMiddleware does not attach Access-Control-* headers to a
        # response generated by Starlette's default 500 path, so a
        # crash in any handler shows up in the browser as
        # net::ERR_FAILED instead of "500 Internal Server Error".
        # We catch every uncaught exception, log the traceback, and
        # echo the request's Origin back if it is in the allowlist so
        # the frontend can read the JSON body and toast it.
        log.error(
            "Unhandled exception on %s %s: %s\n%s",
            request.method,
            request.url.path,
            exc,
            "".join(traceback.format_exception(exc)),
        )
        origin = request.headers.get("origin")
        headers: dict[str, str] = {}
        # Only reflect an exact-match allowlisted Origin. The CORSMiddleware
        # forbids ``*`` with credentials; this handler must not be more
        # permissive, so the ``"*" in allowed_origins`` shortcut is gone —
        # it would echo any origin with ``Allow-Credentials: true`` if
        # CORS_ORIGINS were ever misconfigured to a wildcard.
        if origin and origin in allowed_origins:
            headers["access-control-allow-origin"] = origin
            headers["access-control-allow-credentials"] = "true"
            headers["vary"] = "Origin"
        body = {"detail": "Internal server error."}
        if settings.CHECKWISE_ENV == "local":
            body["error"] = f"{type(exc).__name__}: {exc}"
        return JSONResponse(status_code=500, content=body, headers=headers)

    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    def root() -> RedirectResponse:
        # When docs are disabled (prod default) point the bare-host hit
        # at /health instead of a 404'd /docs.
        return RedirectResponse(url="/docs" if docs_on else "/health")

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "checkwise-api", "environment": settings.CHECKWISE_ENV}

    @app.on_event("startup")
    def _prewarm_pdf_renderer() -> None:
        """Pre-install Chromium in the background at boot if it's missing.

        The report PDF renderer needs Playwright's Chromium. When the build's
        ``playwright install`` doesn't end up where the runtime looks (a
        recurring Render build-cache / browser-path quirk), the renderer
        self-heals by installing on the FIRST PDF request — which makes that
        one request take ~30s. Warming here moves that cost to deploy time,
        in a background thread, so the server is live immediately and the
        first user-triggered render is fast. No-op when Chromium is already
        present (the normal case). Production only; local/CI rely on a
        one-time ``playwright install``.
        """
        if settings.CHECKWISE_ENV != "production":
            return

        import os
        import subprocess
        import sys
        import threading

        def _warm() -> None:
            try:
                from playwright.sync_api import sync_playwright

                with sync_playwright() as p:
                    exe = p.chromium.executable_path
                if exe and os.path.exists(exe):
                    log.info("[startup] Chromium present; PDF renderer warm.")
                    return
            except Exception as exc:  # noqa: BLE001 — fall through to install
                log.warning("[startup] Chromium probe failed (%s); installing.", exc)
            try:
                subprocess.run(
                    [sys.executable, "-m", "playwright", "install", "chromium"],
                    check=False,
                    capture_output=True,
                    timeout=300,
                )
                log.info("[startup] Chromium pre-warm install finished.")
            except Exception as exc:  # noqa: BLE001
                log.warning("[startup] Chromium pre-warm install failed: %s", exc)

        threading.Thread(
            target=_warm, name="chromium-prewarm", daemon=True
        ).start()

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    _assert_critical_routes(app)
    return app


app = create_app()
