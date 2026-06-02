"""Verify EXPOSE_LEGACY_SUBMISSIONS / EXPOSE_METADATA_DRY_RUN kill switches.

Both flags are read at module-import time (the conditional decorator
on ``create_submission`` and the conditional ``include_router`` on
``metadata_dry_run``). The flags default to True, so the in-process
TestClient already exercises the on-state; this module verifies the
off-state by spinning up a fresh Python subprocess with the env
vars overridden and inspecting the registered routes through the
TestClient.

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
            **env_overrides,
        },
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
    """Default-on (flags omitted) keeps the legacy routes registered."""
    routes = _routes_with_env({"CHECKWISE_ENV": "local"})
    assert routes["legacy_submissions"] is True
    assert routes["metadata_dry_run"] is True
