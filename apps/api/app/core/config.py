from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/api service root (this file lives at app/core/config.py).
# Relative filesystem settings anchor here instead of the process CWD —
# "./storage" used to resolve against wherever uvicorn / a seed script /
# a cron happened to be launched from, scattering files across three
# different storage directories (audit 2026-06-12).
_API_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    PROJECT_NAME: str = "CheckWise API"
    API_VERSION: str = "2.5.1"
    API_V1_PREFIX: str = "/api/v1"
    CHECKWISE_ENV: str = "local"
    # IANA tz used to interpret date-only filters (e.g. the audit-log
    # explorer's Desde/Hasta) as full LOCAL calendar days. Stored timestamps
    # are UTC; this anchors a bare "2026-06-17" to the local day boundary.
    AUDIT_LOG_TIMEZONE: str = "America/Mexico_City"

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
    AUTO_METADATA_EXPORT_ENABLED: bool = True
    METADATA_EXPORT_PATH: str = "./metadata_exports"

    @field_validator("LOCAL_STORAGE_PATH", "METADATA_EXPORT_PATH")
    @classmethod
    def _anchor_relative_paths(cls, value: str) -> str:
        """Resolve relative paths against the apps/api service root.

        Absolute values (operator overrides, tests using tmp_path) pass
        through untouched; relative ones — including the defaults — land
        at a deterministic location regardless of the launch CWD.
        """
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = _API_ROOT / path
        return str(path.resolve())

    # S3-compatible object storage (used when STORAGE_BACKEND == "s3").
    # AWS_S3_ENDPOINT is the bucket endpoint URL — set it for Cloudflare R2,
    # MinIO, or any non-AWS provider; leave blank for AWS S3 itself.
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_S3_ENDPOINT: str = ""
    AWS_REGION: str = "auto"
    S3_PRESIGNED_URL_TTL_SECONDS: int = 60 * 15
    # ENC-2 — server-side-encryption algorithm sent on every object write
    # (S3 ``ServerSideEncryption``). "AES256" = SSE-S3 on AWS; Cloudflare R2
    # accepts it and also encrypts at rest unconditionally. Set to "" to
    # disable the header if a backend ever rejects it. Use "aws:kms" only
    # with a configured KMS key on AWS.
    STORAGE_SSE_ALGORITHM: str = "AES256"

    MAX_UPLOAD_SIZE_BYTES: int = 15 * 1024 * 1024
    ALLOWED_FILE_EXTENSIONS: str = ".pdf"

    # CW-DOS-001 — write-time bounds on report version content so an
    # authenticated editor can't store an oversized ``content_json`` that
    # later drives a heavy HTML/PDF (Chromium) export. Defaults are
    # generous — current real reports are a handful of blocks — so they
    # never reject legitimate content while killing the abuse vector.
    REPORT_CONTENT_MAX_BYTES: int = 2 * 1024 * 1024  # serialized content_json
    REPORT_CONTENT_MAX_BLOCKS: int = 200
    REPORT_CONTENT_MAX_TEXT_PER_BLOCK: int = 50_000  # chars across one block's strings
    REPORT_CONTENT_MAX_DEPTH: int = 32
    REPORT_PLAN_MAX_BYTES: int = 512 * 1024  # plan_json / llm_metadata, each
    SUPPORT_WHATSAPP_URL: str = ""
    SUPPORT_QR_PLACEHOLDER_URL: str = ""

    # Auth + RBAC (Patch 6). The default secret is for local dev only;
    # any non-local environment must override AUTH_JWT_SECRET via env.
    # ``_AUTH_JWT_PLACEHOLDER`` below holds the same string so the
    # boot-time validator can refuse to start when this default leaks
    # into a non-local deploy (audit P4-01 — 2026-05-25).
    AUTH_JWT_SECRET: str = "checkwise-local-dev-secret-change-me-please-min-32-chars"
    AUTH_JWT_ALGORITHM: str = "HS256"
    AUTH_JWT_EXPIRES_MINUTES: int = 60 * 24
    AUTH_BCRYPT_ROUNDS: int = 12
    FRONTEND_BASE_URL: str = "http://localhost:3000"
    PASSWORD_RESET_EXPIRES_MINUTES: int = 60

    # Password-reset email delivery. Configure these with the SMTP
    # credentials for the mailbox that should send reset messages.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_FROM_NAME: str = "CheckWise"
    SMTP_USE_TLS: bool = True
    SMTP_USE_SSL: bool = False
    # Backward-compatible names from the earlier email env template.
    EMAIL_SMTP_HOST: str = ""
    EMAIL_SMTP_PORT: int = 587
    EMAIL_SMTP_USER: str = ""
    EMAIL_SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = ""

    # WhatsApp outbound (Meta Cloud API direct). Off by default so a
    # missing template approval can't cause the renewal cron to fire
    # blank messages.
    #
    # Setup (operator):
    #   1. Create a Meta WhatsApp Business Account, verify a sender
    #      phone number, and submit the templates in
    #      docs/runbooks/whatsapp_templates.json. Wait for Meta to
    #      approve (24-48 hr typically).
    #   2. Mint a long-lived System User access token with the
    #      ``whatsapp_business_messaging`` permission.
    #   3. Set the env vars below + flip WHATSAPP_ENABLED=true.
    #
    # WHATSAPP_DRY_RUN=true logs what would be sent without calling
    # Meta — useful during template review and CI tests.
    WHATSAPP_ENABLED: bool = False
    WHATSAPP_DRY_RUN: bool = False
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_API_VERSION: str = "v21.0"
    WHATSAPP_DEFAULT_LANGUAGE_CODE: str = "es_MX"
    WHATSAPP_DEFAULT_COUNTRY_CODE: str = "52"  # MX

    # Reverse-cutover gate. When True, the notification fanout builds
    # the per-event Meta template ``components`` payload and sends via
    # WhatsApp Cloud API instead of falling through to Twilio SMS.
    # Flip ON only after every required template
    # (cw_renewal_threshold, cw_reviewer_decision) is APPROVED in Meta
    # WhatsApp Manager AND WHATSAPP_ENABLED/credentials are set. While
    # False, fanout preserves the SMS-first behavior shipped in Phase 7.
    WHATSAPP_NATIVE_TEMPLATES_ENABLED: bool = False

    # Notification cutover gate for reviewer-DECISION events
    # (submission.approved / rejected / clarification_requested). The
    # legacy workflow (``submission_workflow.apply_reviewer_decision``)
    # still writes the in-app ClientNotification + ProviderNotification
    # AND sends the decision email for these events. The active-mode
    # fabric (dispatcher → fanout) ALSO runs for them so it can own the
    # WhatsApp leg + the dispatch/idempotency audit trail. While this
    # flag is True (default), the fabric SKIPS the in-app row and the
    # email for decision events so the legacy path stays the sole writer
    # — preventing the duplicate bell rows / duplicate emails that would
    # otherwise appear once the emit is committed. Flip to False only
    # after the legacy ``notify_*`` / ``email_provider_of_reviewer_decision``
    # calls are removed and the fabric owns the full decision surface.
    LEGACY_OWNS_DECISION_NOTIFICATIONS: bool = True

    # SMS via Twilio (Phase 7 cutover). Used as the messaging
    # transport until Meta approves CheckWise's WhatsApp templates;
    # see :mod:`app.services.messaging_delivery` for the selection
    # logic. ``MESSAGING_ENABLED`` is the master gate covering both
    # WhatsApp + Twilio paths.
    MESSAGING_ENABLED: bool = False
    TWILIO_ENABLED: bool = False
    TWILIO_DRY_RUN: bool = False
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""

    # Portal session cookie (CheckWise 1.7). Provider portal moves off
    # localStorage and onto an httpOnly signed cookie. Cookie is
    # `Secure` automatically when CHECKWISE_ENV != "local" so dev still
    # works over plain HTTP localhost.
    PORTAL_SESSION_COOKIE_NAME: str = "checkwise_portal_session"
    PORTAL_SESSION_EXPIRES_MINUTES: int = 60 * 24  # 24h, matches AUTH_JWT default

    # Staff/client session cookie (FE-SEC-1, audit 2026-06-15). The
    # admin/client/reviewer JWT is moving off ``localStorage`` (XSS-
    # exfiltratable) onto this httpOnly cookie, mirroring the provider
    # portal. ``login`` issues it and ``get_current_user`` accepts it as a
    # fallback to the ``Authorization`` header, so the header flow keeps
    # working during the staged frontend cutover. ``Secure``/``SameSite``
    # follow ``cookie_secure``/``cookie_samesite`` (None+Secure in prod
    # for the Vercel↔Render cross-site setup).
    AUTH_SESSION_COOKIE_NAME: str = "checkwise_session"

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
    # the multi-file dropzone for contract + annex uploads. Default
    # changed to True on 2026-05-25 ahead of the first paying pilot
    # because contract + anexo uploads are material for REPSE
    # evidence. The legacy single-file path still works when a
    # provider uploads only one file. Override to False via env to
    # roll back without redeploying.
    MULTI_FILE_UPLOAD_ENABLED: bool = True

    # Async intake (§1.5, 2026-06-17) — when True (default), the provider
    # upload endpoint persists a lightweight ``recibido`` receipt and runs
    # the heavy validation pipeline (OCR, forensics, status derivation,
    # metadata export) in a background task; the provider's request
    # returns immediately. When False, the endpoint runs the pipeline
    # synchronously in-request (the legacy behavior) — a kill-switch if
    # the async path ever misbehaves, and the mode the test suite uses so
    # finalize writes land in the per-test session rather than a detached
    # ``SessionLocal``.
    INTAKE_ASYNC_FINALIZE: bool = True

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

    # Security hardening (2026-05-21).
    # ENABLE_API_DOCS: opt-in switch for /docs, /redoc, /openapi.json.
    #   * unset (None) → enabled in local, disabled everywhere else.
    #   * "true"  → forced ON (any environment).
    #   * "false" → forced OFF (any environment).
    # EXPOSE_LEGACY_SUBMISSIONS / EXPOSE_METADATA_DRY_RUN: route-registration
    # switches for deprecated/prototyping upload surfaces. Unset means local
    # only; set true to deliberately expose them in another tier, still behind
    # require_local_or_internal_admin. Set false to remove them everywhere.
    ENABLE_API_DOCS: str = ""
    EXPOSE_LEGACY_SUBMISSIONS: bool | None = None
    EXPOSE_METADATA_DRY_RUN: bool | None = None

    # Auth rate-limit. Conservative defaults — protect against
    # credential-stuffing and reset-link abuse without locking out
    # legitimate users. The backend implementation is selected by
    # ``REDIS_URL`` (see below): unset → in-memory sliding window
    # (single-worker only); set → shared Redis sliding window
    # (correct across any number of workers).
    AUTH_LOGIN_RATE_LIMIT_PER_MINUTE: int = 10
    AUTH_FORGOT_PASSWORD_RATE_LIMIT_PER_HOUR: int = 5
    # Account lockout (platform rework follow-up). Distinct from the
    # per-IP/email *rate* limiter above: this counts CONSECUTIVE failed
    # logins per account and locks it for a cooldown once the threshold
    # is hit — stopping a slow password-guess against one account even
    # from rotating IPs. The counter resets on any successful login or
    # password change, and an admin password-reset / reactivate clears
    # an active lock. THRESHOLD=0 disables the feature.
    AUTH_LOCKOUT_THRESHOLD: int = 5
    AUTH_LOCKOUT_MINUTES: int = 15
    # M3 (2026-05-25) — brute-force protection on the public share-
    # link password unlock + consume endpoints. 5 attempts per minute
    # per (ip, token) lets a legitimate user retype a typo; 30 per
    # hour per IP catches a slow grind across many tokens. Setting
    # either to 0 disables that bucket.
    SHARE_UNLOCK_RATE_LIMIT_PER_MINUTE: int = 5
    SHARE_UNLOCK_RATE_LIMIT_PER_HOUR: int = 30
    # M3 (2026-05-25) — per-user cap on LLM-backed reports endpoints
    # and the provider copilot. 15/minute matches interactive use
    # (one block regenerate every ~4s); 120/hour bounds the cost of
    # a runaway script or accidental loop. Set 0 to disable.
    AI_HEAVY_RATE_LIMIT_PER_MINUTE: int = 15
    AI_HEAVY_RATE_LIMIT_PER_HOUR: int = 120

    # Heavy file-export endpoints (audit-package + expediente ZIPs). These
    # stream up to hundreds of files / MB and render a Chromium manifest PDF, so
    # the cap is tighter than the AI one: 10/minute covers legitimate "download
    # a few packages" bursts; 60/hour bounds a scripted scrape. Set 0 to
    # disable. (perf audit P2-8)
    EXPORT_RATE_LIMIT_PER_MINUTE: int = 10
    EXPORT_RATE_LIMIT_PER_HOUR: int = 60

    # Rate-limit shared backing store (M4 — 2026-06-02). Empty string
    # selects the in-memory sliding window: correct on a single
    # uvicorn worker, silently double-counts on every additional
    # worker because each process keeps its own counters. Any value
    # parseable by ``redis.Redis.from_url`` (``redis://...``,
    # ``rediss://...`` for TLS, ``redis+sentinel://...``) selects the
    # shared backend so the configured limits hold across the entire
    # API cluster. Operator should provision Redis before bumping
    # Render's worker count above 1 — otherwise the documented
    # protections are off by a factor of N silently.
    REDIS_URL: str = ""
    # Per-call timeout for the rate-limit Redis ops in milliseconds.
    # Kept tight because the limiter runs on the hot path of login /
    # share-unlock — a hung Redis must not stall every request.
    # Failures raise (fail-closed → 500) rather than fall through so
    # an outage surfaces immediately instead of silently disabling
    # the limiter. See ``RedisRateLimiter`` for the fail-mode
    # contract.
    REDIS_RATE_LIMIT_TIMEOUT_MS: int = 250
    # CW-RATE-002 — number of trusted reverse proxies that append the real
    # peer to ``X-Forwarded-For``. Render fronts the API with exactly ONE
    # proxy, so the rightmost XFF entry is the real client → default 1
    # (preserves today's behavior byte-for-byte). ``client_ip_from_request``
    # picks the Nth-from-right entry; ``0`` distrusts XFF entirely and uses
    # the socket peer (correct when no trusted proxy is in front). A chain
    # shorter than this many hops is treated as forged and falls through to
    # X-Real-IP / socket peer rather than trusting an attacker-positioned IP.
    # Configurable so a topology change is an env edit, not a code change.
    RATE_LIMIT_TRUSTED_PROXY_HOPS: int = 1

    # Phase 3 — Google Document AI OCR fallback for scanned uploads.
    # OCR runs synchronously during intake when ``inspect_pdf`` reports
    # ``is_probably_scanned=True``. Default OFF so the backend boots
    # cleanly in CI / dev environments that have no GCP credentials —
    # scans fall through to ``pendiente_revision`` exactly as today.
    # See ``apps/api/docs/PHASE3_DOCUMENTAI_SETUP.md`` for provisioning.
    OCR_ENABLED: bool = False
    GOOGLE_DOC_AI_PROJECT_ID: str = ""
    GOOGLE_DOC_AI_LOCATION: str = "us"  # 'us' or 'eu'
    GOOGLE_DOC_AI_PROCESSOR_ID: str = ""
    # Render-friendly: paste the full JSON content here. Locally the
    # standard ``GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json`` path
    # also works (the SDK picks it up automatically). The service prefers
    # the inline JSON if both are set.
    GOOGLE_APPLICATION_CREDENTIALS_JSON: str = ""
    # Hard cap on the synchronous OCR call. Document AI usually returns
    # in 2-6s; 30s is the upload-timeout ceiling so we never block a
    # provider indefinitely on a slow processor.
    OCR_TIMEOUT_SECONDS: float = 30.0

    # ─────────────────────────────────────────────────────────────────
    # Phase 2 — Anthropic Claude document-analysis provider (shadow).
    #
    # Selects which backend the background shadow runner uses. The
    # inline heuristic classifier in ``submission_service`` runs
    # unconditionally; these settings only control the optional
    # secondary AI analysis that persists to the ``shadow_*`` columns
    # on ``DocumentInspection`` for offline comparison.
    #
    # Valid provider values:
    #   ``disabled`` (default) — no shadow runs.
    #   ``heuristic``         — shadow runs the regex baseline (test only).
    #   ``anthropic``         — Claude reads the PDF and extracts.
    #   ``shadow``            — alias for ``anthropic``.
    #
    # ``DOCUMENT_ANALYSIS_DAILY_CAP_PER_ORG`` is the safety circuit
    # breaker against runaway spend during the pilot. 0 disables.
    #
    # Limits mirror Anthropic's PDF support documented caps:
    # ``MAX_FILE_MB`` ≤ 32 (API hard cap), ``MAX_PAGES`` ≤ 100 for
    # the 200k-context models we use. Files exceeding either limit
    # skip the provider and record ``shadow_error=unsupported_size_or_type``.
    # ─────────────────────────────────────────────────────────────────
    DOCUMENT_ANALYSIS_PROVIDER: str = "disabled"
    # Phase C — tiered analysis. Every shadow-analyzed upload runs the
    # cheap TRIAGE model first; suspicious results (or high-stakes
    # requirements) re-run on the stronger escalation model below.
    # ``DOCUMENT_ANALYSIS_MODEL`` keeps its name for Render env compat
    # but is now the **escalation** model, not the per-upload default.
    DOCUMENT_ANALYSIS_MODEL: str = "claude-sonnet-4-6"
    DOCUMENT_ANALYSIS_TRIAGE_MODEL: str = "claude-haiku-4-5"
    DOCUMENT_ANALYSIS_TIMEOUT_SECONDS: float = 30.0
    DOCUMENT_ANALYSIS_MAX_FILE_MB: int = 30
    DOCUMENT_ANALYSIS_MAX_PAGES: int = 100
    DOCUMENT_ANALYSIS_DAILY_CAP_PER_ORG: int = 200
    # Phase C — separate daily cap for escalation-tier (expensive model)
    # re-runs. Counted independently of the triage cap; 0 disables.
    # Exhaustion skips the escalation gracefully (triage result stands).
    DOCUMENT_ANALYSIS_ESCALATION_DAILY_CAP_PER_ORG: int = 50

    # Phase 0 (comprehension) — the escalation/deep tier reasons about the
    # document instead of single-pass extracting it: adaptive thinking +
    # ``effort=high`` + structured outputs need more room and time than the
    # cheap triage pass. These knobs apply ONLY to the deep tier; the Haiku
    # triage tier keeps its tight 1024-token / 30 s budget. Raise the model
    # to ``claude-opus-4-8`` via ``DOCUMENT_ANALYSIS_MODEL`` when the cost
    # tradeoff is approved.
    DOCUMENT_ANALYSIS_DEEP_MAX_TOKENS: int = 8192
    DOCUMENT_ANALYSIS_DEEP_TIMEOUT_SECONDS: float = 90.0

    # Wise copilot (Haiku, max_tokens=500). The dock answer is returned
    # synchronously inside the request, so the Anthropic call is bounded
    # server-side. Without this the only guard was the frontend's 30 s abort
    # while the worker thread kept running the call (SDK default 600 s) after
    # the user already gave up. Wise prompts are small and fast — keep it tight.
    WISE_REQUEST_TIMEOUT_SECONDS: float = 20.0

    # Phase 2 (expediente) — the situational pass reasons across a whole
    # provider+period document set. Opt-in (off by default) and counted
    # against the per-org escalation cap, since each run is a deep call on
    # the stronger model. Uses ``DOCUMENT_ANALYSIS_MODEL`` (the deep tier
    # model) + the deep max-tokens/timeout knobs above.
    DOCUMENT_ANALYSIS_EXPEDIENTE_ENABLED: bool = False
    # Debounce for the after-deep-run trigger: skip the expediente pass if
    # a non-errored assessment for the same (client, vendor, period) ran
    # within this many hours. 0 disables the debounce (every deep run
    # triggers one). Keeps active expedientes from re-assessing on every
    # uploaded document.
    DOCUMENT_ANALYSIS_EXPEDIENTE_DEBOUNCE_HOURS: int = 6

    # Phase 3 — pilot-cohort allowlist. CSV of ``client.id`` values
    # that are allowed to receive shadow analysis. Empty string (the
    # default) disables the gate, so every org is in scope. When set,
    # the shadow runner short-circuits with
    # ``shadow_error="not_in_pilot_cohort"`` for any org_id not in
    # the list — the heuristic still drives the user-visible status
    # exactly as today. Whitespace + blank entries are tolerated.
    DOCUMENT_ANALYSIS_PILOT_ORG_IDS: str = ""

    # ─────────────────────────────────────────────────────────────────
    # Phase 3/4 — comprehension → metadata field suggestions.
    #
    # When the deep tier runs, it can also propose values for the
    # ``ai_assisted`` metadata fields the rulebook otherwise leaves blank
    # (main_date, participants, start_date, …) and those proposals fill the
    # metadata XLSX as ``prefilled_needs_review`` — never auto-approved
    # (the rulebook keeps ``legal_approval_allowed=False``). Zero extra
    # model calls: it rides the comprehension pass that already runs.
    #
    # Off by default — when disabled, the deep tier behaves exactly as
    # before (no field schema sent, no suggestions parsed) and the metadata
    # export keeps its deterministic skeleton. Safe to ship dark.
    COMPREHENSION_FIELD_SUGGESTIONS_ENABLED: bool = False
    # CSV allowlist of requirement codes whose uploads get field
    # suggestions. Empty (default) = none, even when the flag above is on —
    # graduate codes one at a time as calibration confirms precision
    # (mirrors the auto-approve unlock ladder). ``*`` unlocks all codes.
    COMPREHENSION_UNLOCKED_REQUIREMENT_CODES: str = ""
    # Drop any individual field suggestion below this confidence before it
    # reaches the workbook. The reviewer still confirms every prefilled
    # value; this just suppresses low-signal noise.
    COMPREHENSION_FIELD_SUGGESTION_MIN_CONFIDENCE: float = 0.55

    # ─────────────────────────────────────────────────────────────────
    # Phase E — document-revalidation approval suggestion + auto-approve.
    #
    # ``AUTO_APPROVE_SUGGEST_CONFIDENCE`` gates the reviewer-facing
    # "sugerimos aprobar" hint on the detail endpoint (live, advisory
    # only — never changes a status by itself).
    #
    # The auto-approve engine ships DARK:
    #   * ``AUTO_APPROVE_ENABLED`` is the master kill switch (default
    #     OFF — nothing is ever auto-approved until an operator flips
    #     it deliberately).
    #   * ``AUTO_APPROVE_UNLOCKED_REQUIREMENT_CODES`` is a CSV
    #     allowlist of requirement codes unlocked for auto-approval.
    #     Codes are added MANUALLY, one at a time, from calibration-
    #     harness reports proving ≥99% precision for that document
    #     type. Empty (the default) means no type is unlocked even
    #     with the master flag on.
    #   * ``AUTO_APPROVE_MIN_CONFIDENCE`` is the per-document floor on
    #     the best available match confidence (shadow preferred,
    #     heuristic fallback). Deliberately stricter than the
    #     suggestion threshold.
    # ─────────────────────────────────────────────────────────────────
    AUTO_APPROVE_SUGGEST_CONFIDENCE: float = 0.9
    AUTO_APPROVE_ENABLED: bool = False
    AUTO_APPROVE_UNLOCKED_REQUIREMENT_CODES: str = ""
    AUTO_APPROVE_MIN_CONFIDENCE: float = 0.97

    # env_file anchors to the apps/api root for the same reason the
    # storage paths do (audit 2026-06-12): a CWD-relative ".env" meant a
    # server launched from the repo root silently ran with default
    # settings — different auth secret, no R2 creds — while one launched
    # from apps/api picked up the real config.
    model_config = SettingsConfigDict(
        env_file=str(_API_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # Render (and many hosts) accept env vars set to an empty string as
    # "the var exists with an empty value". pydantic-settings 2.13 stopped
    # silently coercing those to None / default, so any int/bool/float
    # field that ends up empty in the dashboard now hard-fails the boot
    # with a ValidationError. This validator runs before type coercion
    # and substitutes the field's declared default when the raw value is
    # an empty string AND the field's annotation is a non-str scalar
    # type. We intentionally do NOT do this for `str` fields, because
    # empty-string-as-deliberate-value is meaningful there (e.g. setting
    # `CORS_ORIGINS=""` to mean "no allowed origins" is a legitimate
    # — albeit harsh — production choice).
    @field_validator("*", mode="before")
    @classmethod
    def _blank_non_str_to_default(cls, value: Any, info: Any) -> Any:
        if not (isinstance(value, str) and value == ""):
            return value
        field = cls.model_fields.get(info.field_name)
        if field is None:
            return value
        annotation = field.annotation
        if annotation is str:
            return value
        return field.default

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def allowed_extensions_set(self) -> set[str]:
        return {
            ext.strip().lower() for ext in self.ALLOWED_FILE_EXTENSIONS.split(",") if ext.strip()
        }

    @property
    def is_local_env(self) -> bool:
        """True iff the deploy is the local-dev environment.

        The single source of truth for "is this production-grade?".
        Used by the security middleware, the API-doc gate, and the
        upload-endpoint gates.
        """
        return self.CHECKWISE_ENV == "local"

    @property
    def api_docs_enabled(self) -> bool:
        """Whether FastAPI's /docs, /redoc, /openapi.json should be served.

        Default: enabled only in local. Set ``ENABLE_API_DOCS=true`` to
        opt in (e.g. a temporary staging tier); ``ENABLE_API_DOCS=false``
        forces off even in local.
        """
        flag = (self.ENABLE_API_DOCS or "").strip().lower()
        if flag in {"1", "true", "yes", "on"}:
            return True
        if flag in {"0", "false", "no", "off"}:
            return False
        return self.is_local_env

    @property
    def expose_legacy_submissions(self) -> bool:
        """Whether the deprecated browser-posted tenant route is registered."""
        if self.EXPOSE_LEGACY_SUBMISSIONS is not None:
            return self.EXPOSE_LEGACY_SUBMISSIONS
        return self.is_local_env

    @property
    def expose_metadata_dry_run(self) -> bool:
        """Whether the local/n8n metadata dry-run route is registered."""
        if self.EXPOSE_METADATA_DRY_RUN is not None:
            return self.EXPOSE_METADATA_DRY_RUN
        return self.is_local_env

    @property
    def allowed_csrf_origins(self) -> set[str]:
        """Origins permitted to issue cookie-authenticated mutating requests.

        Sourced from ``CORS_ORIGINS`` plus ``FRONTEND_BASE_URL`` so the
        portal's own UI is always in the set. Bearer-token requests
        bypass this check (see ``portal.enforce_portal_csrf``).
        """
        origins = {o.rstrip("/") for o in self.cors_origins_list if o}
        if self.FRONTEND_BASE_URL:
            origins.add(self.FRONTEND_BASE_URL.rstrip("/"))
        return origins

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
        return _normalize_pg_url(self.DATABASE_URL, require_ssl=not self.is_local_env)

    @property
    def alembic_url(self) -> str:
        """URL Alembic should use.

        Prefers ``DIRECT_DATABASE_URL`` (pooled endpoints lack advisory
        locks). Falls back to ``DATABASE_URL`` when no direct URL is set,
        which matches single-endpoint dev setups.
        """
        return _normalize_pg_url(
            self.DIRECT_DATABASE_URL or self.DATABASE_URL,
            require_ssl=not self.is_local_env,
        )


def _ensure_sslmode_require(url: str) -> str:
    """Pin ``sslmode=require`` on a Postgres URL that omits an explicit mode.

    ENC-1 — psycopg/libpq defaults to ``sslmode=prefer``, which silently
    downgrades to an *unencrypted* connection when the server permits it.
    For any non-local deploy we want encryption-in-transit to fail closed,
    so we require TLS unless the operator has already chosen an explicit
    (and presumably stricter, e.g. ``verify-full``) mode. We only append —
    never override — so a deliberate choice is respected.
    """
    if "sslmode=" in url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}sslmode=require"


def _normalize_pg_url(url: str, *, require_ssl: bool = False) -> str:
    if not url:
        return url
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    if require_ssl and url.startswith("postgresql+psycopg://"):
        url = _ensure_sslmode_require(url)
    return url


_AUTH_JWT_PLACEHOLDER = (
    "checkwise-local-dev-secret-change-me-please-min-32-chars"
)


class InsecureBootError(RuntimeError):
    """Raised when boot config would silently expose a security risk.

    Today: the in-code ``AUTH_JWT_SECRET`` placeholder leaking into a
    non-local environment (audit P4-01 — 2026-05-25). The placeholder
    is committed to a public repo, so any process running with it
    would accept JWTs minted by anyone reading the source.
    """


def _validate_boot_security(settings: Settings) -> None:
    """Refuse to boot the API with an unsafe security configuration.

    Called once from :func:`get_settings` so the check fires the first
    time anything in the codebase imports ``settings``. In local
    (``CHECKWISE_ENV=local``) the guard is a no-op so the placeholder
    keeps dev workflows fast; outside local it raises before any
    request can be served.

    Also emits soft warnings — non-fatal, log-only — for configuration
    that's wrong but won't break boot. Today: a non-local deploy whose
    ``FRONTEND_BASE_URL`` still points at localhost (audit P2-05).
    """
    if settings.is_local_env:
        return
    if settings.AUTH_JWT_SECRET == _AUTH_JWT_PLACEHOLDER:
        raise InsecureBootError(
            "Refusing to start: AUTH_JWT_SECRET is still set to the public "
            "in-code placeholder. Set AUTH_JWT_SECRET to a fresh 32+ char "
            "random string in the Render dashboard (openssl rand -hex 32) "
            "before redeploying."
        )
    # The placeholder check above only catches the *exact* committed string.
    # An empty or short secret (e.g. AUTH_JWT_SECRET set blank or to a
    # 1-char value in the dashboard) would otherwise boot and sign every
    # JWT with a trivially brute-forceable key. Enforce the documented
    # 32-char minimum here so weak/empty secrets fail closed too.
    if len(settings.AUTH_JWT_SECRET) < 32:
        raise InsecureBootError(
            "Refusing to start: AUTH_JWT_SECRET is too short (min 32 chars). "
            "An empty or weak secret lets anyone forge JWTs. Set "
            "AUTH_JWT_SECRET to a fresh 32+ char random string in the Render "
            "dashboard (openssl rand -hex 32) before redeploying."
        )
    # Soft warning — FRONTEND_BASE_URL is what every transactional
    # email CTA links to. A non-local deploy that still points at
    # localhost will send password-reset / reviewer-decision /
    # renewal-reminder emails whose links lead nowhere. Doesn't
    # block boot (a deploy might intentionally test without
    # outbound email), but logs loudly so it's visible in Render
    # logs on first start.
    import logging

    if settings.FRONTEND_BASE_URL.startswith("http://localhost"):
        logging.getLogger("checkwise.config").warning(
            "FRONTEND_BASE_URL is still '%s' on a non-local deploy "
            "(CHECKWISE_ENV=%s). Email CTAs will link to localhost — "
            "set FRONTEND_BASE_URL to the production hostname (e.g. "
            "https://app.checkwise.mx) in the Render dashboard.",
            settings.FRONTEND_BASE_URL,
            settings.CHECKWISE_ENV,
        )

    # CORS-1 — soft warning: an empty CORS allowlist on a non-local deploy
    # makes CORSMiddleware emit no Access-Control-Allow-Origin, so every
    # credentialed cross-site request from the Vercel frontend is blocked
    # (silent, total breakage). It also empties allowed_csrf_origins when
    # FRONTEND_BASE_URL is likewise blank, rejecting every cookie-authed
    # mutation. CORS_ORIGINS is sync:false in render.yaml, so a first-deploy
    # operator who forgets to paste the origin gets no signal today. Log-only
    # (an empty allowlist can be a deliberate, harsh production choice).
    if not settings.cors_origins_list:
        logging.getLogger("checkwise.config").warning(
            "CORS_ORIGINS is empty on a non-local deploy (CHECKWISE_ENV=%s). "
            "The API will send no Access-Control-Allow-Origin and the browser "
            "will block every credentialed request from the frontend. Set "
            "CORS_ORIGINS to the frontend origin(s) (e.g. https://app.checkwise.mx) "
            "in the Render dashboard.",
            settings.CHECKWISE_ENV,
        )

    # INFRA-2 — soft warning: the in-memory rate limiter keeps its
    # sliding-window counters per process. On a single uvicorn worker
    # (today's prod) that's correct, but the moment the worker/instance
    # count goes above 1 without a shared backend, every brute-force cap
    # (login, forgot-password, share-unlock, AI cost) silently weakens by
    # the worker multiple. Provision Redis and set REDIS_URL *before*
    # scaling out. Log-only so it can't break a deliberate single-worker
    # deploy.
    if not settings.REDIS_URL:
        logging.getLogger("checkwise.config").warning(
            "REDIS_URL is unset on a non-local deploy (CHECKWISE_ENV=%s). "
            "The rate limiter is in-memory and only enforces correctly on "
            "a SINGLE worker/instance. Provision Redis and set REDIS_URL "
            "before raising the worker or instance count.",
            settings.CHECKWISE_ENV,
        )

    # ENC-1 — encryption-in-transit to Postgres. ``sqlalchemy_url`` /
    # ``alembic_url`` auto-append ``sslmode=require`` when the URL omits a
    # mode, so the default is fail-closed. Warn loudly if an operator has
    # explicitly selected an insecure mode, which would re-open a plaintext
    # downgrade despite the auto-append.
    _db_url = (settings.DATABASE_URL or "").lower()
    if any(f"sslmode={mode}" in _db_url for mode in ("disable", "allow", "prefer")):
        logging.getLogger("checkwise.config").warning(
            "DATABASE_URL sets an insecure sslmode on a non-local deploy "
            "(CHECKWISE_ENV=%s). Data to the database may transit without "
            "TLS. Use sslmode=require (or verify-full) for encryption in "
            "transit.",
            settings.CHECKWISE_ENV,
        )


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    _validate_boot_security(s)
    return s


settings = get_settings()
