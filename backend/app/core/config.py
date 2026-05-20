from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "CheckWise API"
    API_VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"
    CHECKWISE_ENV: str = "local"

    DATABASE_URL: str = "postgresql+psycopg://checkwise:checkwise@localhost:5432/checkwise"
    # Optional second URL used only by Alembic. Pooled connection providers
    # (Neon's pgbouncer endpoint, RDS Proxy, etc.) don't support the advisory
    # locks Alembic uses, so production deploys point DATABASE_URL at the
    # pooled endpoint and DIRECT_DATABASE_URL at the direct endpoint.
    DIRECT_DATABASE_URL: str = ""
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    STORAGE_BACKEND: str = "local"
    STORAGE_BUCKET: str = "checkwise-local"
    STORAGE_PUBLIC_BASE_URL: str = ""
    LOCAL_STORAGE_PATH: str = "./storage"

    # S3-compatible object storage (used when STORAGE_BACKEND == "s3").
    # AWS_S3_ENDPOINT is the bucket endpoint URL — set it for Cloudflare R2,
    # MinIO, or any non-AWS provider; leave blank for AWS S3 itself.
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_S3_ENDPOINT: str = ""
    AWS_REGION: str = "auto"
    S3_PRESIGNED_URL_TTL_SECONDS: int = 60 * 15

    MAX_UPLOAD_SIZE_BYTES: int = 15 * 1024 * 1024
    ALLOWED_FILE_EXTENSIONS: str = ".pdf"
    SUPPORT_WHATSAPP_URL: str = ""
    SUPPORT_QR_PLACEHOLDER_URL: str = ""

    # Auth + RBAC (Patch 6). The default secret is for local dev only;
    # any non-local environment must override AUTH_JWT_SECRET via env.
    AUTH_JWT_SECRET: str = "checkwise-local-dev-secret-change-me-please-min-32-chars"
    AUTH_JWT_ALGORITHM: str = "HS256"
    AUTH_JWT_EXPIRES_MINUTES: int = 60 * 24
    AUTH_BCRYPT_ROUNDS: int = 12

    # Portal session cookie (CheckWise 1.7). Provider portal moves off
    # localStorage and onto an httpOnly signed cookie. Cookie is
    # `Secure` automatically when CHECKWISE_ENV != "local" so dev still
    # works over plain HTTP localhost.
    PORTAL_SESSION_COOKIE_NAME: str = "checkwise_portal_session"
    PORTAL_SESSION_EXPIRES_MINUTES: int = 60 * 24  # 24h, matches AUTH_JWT default

    # Reports AI (Phase 3.3+). Anthropic Claude powers the report
    # planner + per-block content generator. Empty string means "no
    # API key configured" — the LLM client factory will fall back to
    # DeterministicMockLLMClient. Setting CHECKWISE_LLM_BACKEND=mock
    # forces the mock even when a key is present (useful for CI).
    ANTHROPIC_API_KEY: str = ""
    CHECKWISE_LLM_BACKEND: str = ""  # '' | 'anthropic' | 'mock'

    # Contact-form delivery (P0-3). Optional Slack incoming-webhook
    # URL that receives a formatted message for each new public
    # contact request. Empty (default) → persistence only; the
    # endpoint never fails because of a missing/broken webhook.
    SLACK_CONTACT_WEBHOOK_URL: str = ""

    # Internal feedback delivery (tester bug/improvement reports).
    # Requires a Slack *bot* token (xoxb-…) because attaching a PNG
    # uses files.upload_v2, which incoming webhooks do not support.
    # Both empty (default) → endpoint validates the request and
    # responds 202 with delivered=false, so the frontend can be
    # exercised before the Slack app is provisioned.
    SLACK_BOT_TOKEN: str = ""
    SLACK_FEEDBACK_CHANNEL_ID: str = ""

    # Stage 2.7 — Provider correction-request delivery.
    # Optional Slack incoming-webhook URL that receives a Block Kit
    # message each time a provider submits a Tier B correction request
    # (contact_email / contact_phone / contact_name) via the workspace
    # context bar. Empty (default) → persistence to audit_log only; the
    # endpoint never fails because of a missing or broken webhook. Ops
    # may point this at the same #checkwise-feedback channel that the
    # feedback router uses, or at a dedicated channel for triage.
    SLACK_CORRECTION_WEBHOOK_URL: str = ""

    # Stage 2.7 — Multi-file upload feature flag.
    # When True, the provider /submissions endpoint accepts up to 5
    # files per submission (≤ 30 MB total) and the intake wizard shows
    # the multi-file dropzone. When False (default), the legacy
    # single-file path is the only one available. Flag-gated so the new
    # path can be rolled back without redeploying.
    MULTI_FILE_UPLOAD_ENABLED: bool = False

    # Catalog v2 (2026-05-20) — collapsed recurring catalog feature flag.
    # When True, ``recurring_for_year_v2`` is the authoritative
    # generator: each (institution, period) pair becomes ONE
    # ``RecurringRequirement`` row carrying an ``accepts_documents``
    # list naming the alternative doc types the provider may submit
    # (Comprobante de pago bancario / CFDI / Cédula / Resumen for IMSS
    # monthly, etc.). When False (default), the legacy v1 catalog
    # remains authoritative — one row per (institution, period, doc
    # name). The flag lets v2 cohabit with v1 in production while the
    # slot resolver + endpoints + frontend land in follow-up sessions;
    # rollback is a flag flip rather than a code revert.
    RECURRING_CATALOG_V2: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def allowed_extensions_set(self) -> set[str]:
        return {
            ext.strip().lower() for ext in self.ALLOWED_FILE_EXTENSIONS.split(",") if ext.strip()
        }

    @property
    def cookie_secure(self) -> bool:
        """Set `Secure` on cookies in any non-local environment."""
        return self.CHECKWISE_ENV != "local"

    @property
    def cookie_samesite(self) -> str:
        """``SameSite`` value for the portal session cookie.

        In production the frontend (Vercel) and the API (Render) live on
        different eTLD+1 origins, so the browser will only send the
        portal cookie cross-site when ``SameSite=None`` AND ``Secure``
        are both set. In local dev everything is on ``localhost``, so
        ``Lax`` is the safer default.
        """
        return "none" if self.cookie_secure else "lax"

    @property
    def sqlalchemy_url(self) -> str:
        """``DATABASE_URL`` normalized for SQLAlchemy + psycopg 3.

        Managed providers (Neon, Supabase, Render) hand out plain
        ``postgresql://`` URLs. SQLAlchemy with psycopg 3 needs the
        explicit ``postgresql+psycopg://`` driver token, so paste-as-is
        Just Works without you remembering to rewrite the URL.
        """
        return _normalize_pg_url(self.DATABASE_URL)

    @property
    def alembic_url(self) -> str:
        """URL Alembic should use.

        Prefers ``DIRECT_DATABASE_URL`` (pooled endpoints lack advisory
        locks). Falls back to ``DATABASE_URL`` when no direct URL is set,
        which matches single-endpoint dev setups.
        """
        return _normalize_pg_url(self.DIRECT_DATABASE_URL or self.DATABASE_URL)


def _normalize_pg_url(url: str) -> str:
    if not url:
        return url
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
