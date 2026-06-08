"""Verify EXPOSE_LEGACY_SUBMISSIONS / EXPOSE_METADATA_DRY_RUN kill switches.

Both flags are read at module-import time (the conditional decorator
on ``create_submission`` and the conditional ``include_router`` on
``metadata_dry_run``). Unset means local-only registration; explicit
``true`` exposes the routes in another tier, still behind the auth
gate. This module spins up fresh Python subprocesses with env vars
overridden and inspects registered routes through the TestClient.

Subprocess isolation is required because the @router.post decorator
runs at import time — once ``app.main`` has been imported in the
current process, the route is permanently attached to the router
object and a runtime settings flip would have no effect.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]


def _routes_with_env(env_overrides: dict[str, str]) -> dict[str, bool]:
    """Spawn a fresh interpreter, import the app, return route presence."""
    script = textwrap.dedent(
        """
        import json
        from app.main import app

        paths = {getattr(route, "path", "") for route in app.routes}
        print(json.dumps({
            "legacy_submissions": "/api/v1/submissions" in paths,
            "metadata_dry_run": any(p.startswith("/api/v1/metadata-dry-run") for p in paths),
            "health": "/health" in paths,
            "catalogs": "/api/v1/catalogs" in paths,
        }))
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": str(API_DIR),
            **env_overrides,
        },
        cwd=API_DIR,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_kill_switches_off_removes_legacy_routes() -> None:
    """When both flags are false, the legacy routes are absent entirely."""
    routes = _routes_with_env(
        {
            "CHECKWISE_ENV": "local",
            "EXPOSE_LEGACY_SUBMISSIONS": "false",
            "EXPOSE_METADATA_DRY_RUN": "false",
        }
    )
    assert routes["legacy_submissions"] is False
    assert routes["metadata_dry_run"] is False
    # Non-gated routes survive the flag flip — kill switches are surgical.
    assert routes["health"] is True
    assert routes["catalogs"] is True


def test_kill_switches_on_registers_legacy_routes() -> None:
    """Unset flags keep local-dev legacy routes registered."""
    routes = _routes_with_env({"CHECKWISE_ENV": "local"})
    assert routes["legacy_submissions"] is True
    assert routes["metadata_dry_run"] is True


def test_kill_switches_default_off_outside_local() -> None:
    """Unset flags remove legacy/prototyping routes in non-local tiers."""
    routes = _routes_with_env(
        {
            "CHECKWISE_ENV": "production",
            "AUTH_JWT_SECRET": "prod-secret-prod-secret-prod-secret-12345",
        }
    )
    assert routes["legacy_submissions"] is False
    assert routes["metadata_dry_run"] is False
    assert routes["health"] is True
    assert routes["catalogs"] is True


def test_kill_switches_can_explicitly_opt_in_outside_local() -> None:
    """Explicit true preserves the operator escape hatch in production."""
    routes = _routes_with_env(
        {
            "CHECKWISE_ENV": "production",
            "AUTH_JWT_SECRET": "prod-secret-prod-secret-prod-secret-12345",
            "EXPOSE_LEGACY_SUBMISSIONS": "true",
            "EXPOSE_METADATA_DRY_RUN": "true",
        }
    )
    assert routes["legacy_submissions"] is True
    assert routes["metadata_dry_run"] is True
