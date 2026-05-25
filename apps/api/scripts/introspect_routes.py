"""Introspect every FastAPI route and emit a JSON snapshot.

Used by:
- ``tests/test_route_policy_manifest.py`` — compares the live route
  set against ``app/security/route_policy_manifest.json`` and fails
  when a new route lands without a policy entry.
- Operators / auditors who want a current snapshot of the API
  surface for a security review.

Output schema (JSON list, one object per route × HTTP method):

    {
        "method": "GET",
        "path": "/api/v1/admin/clients/{client_id}",
        "name": "get_client",
        "router_module": "app.api.v1.admin",
        "endpoint_qualname": "get_client",
        "endpoint_file": "apps/api/app/api/v1/admin.py",
        "endpoint_lineno": 354,
        "depends_on": ["DbSession", "AdminUser"]
    }

Run from ``apps/api`` directory:

    python -m scripts.introspect_routes > /tmp/checkwise_routes.json

The script is read-only — no DB, no network, no environment side
effects.
"""

from __future__ import annotations

import inspect
import json
import sys
import typing
from pathlib import Path

from app.main import app

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _annotation_name(annotation: object) -> str | None:
    """Return the most useful short name for a parameter annotation.

    Handles ``Annotated[X, ...]``, ``X | None``, plain ``X``, and the
    typed aliases the routers define (``AdminUser``, ``ClientUser``,
    ``ReviewerDep``, ``DbSession``).
    """
    if annotation is inspect.Parameter.empty:
        return None
    origin = typing.get_origin(annotation)
    if origin is typing.Annotated:
        args = typing.get_args(annotation)
        if args:
            return _annotation_name(args[0])
    if hasattr(annotation, "__name__"):
        return annotation.__name__
    return str(annotation)


def _classify_depends(annotation: object) -> str | None:
    """Map an Annotated/Depends signature to a short policy tag.

    Used by the manifest tests to confirm declared policy matches the
    actual function signature. Handles three forms:

    - Live type object (no ``from __future__ import annotations``).
    - String (PEP 563 future annotations) — pattern-matched for the
      most common shapes the routers use.
    - Plain class without ``Annotated`` wrapping.
    """
    if annotation is inspect.Parameter.empty:
        return None
    if isinstance(annotation, str):
        # Strip ``Annotated[...]`` wrapping when present so the first
        # token inside is what we report. The PDF audit treats the
        # short alias (AdminUser, ClientUser, ReviewerDep,
        # current_portal_workspace, etc.) as the canonical gate label.
        text = annotation.strip()
        if text.startswith("Annotated[") and text.endswith("]"):
            inner = text[len("Annotated[") : -1]
            # First comma at depth 0 separates the wrapped type from
            # the metadata.
            depth = 0
            head_end = len(inner)
            for idx, ch in enumerate(inner):
                if ch == "[":
                    depth += 1
                elif ch == "]":
                    depth -= 1
                elif ch == "," and depth == 0:
                    head_end = idx
                    break
            head = inner[:head_end].strip()
            metadata = inner[head_end + 1 :].strip() if head_end < len(inner) else ""
            # If the metadata declares Depends(<fn>), the dependency
            # function name is the most useful classifier.
            if "Depends(" in metadata:
                dep_start = metadata.index("Depends(") + len("Depends(")
                dep_end = metadata.find(")", dep_start)
                if dep_end > dep_start:
                    return metadata[dep_start:dep_end].strip()
            return head
        return text
    origin = typing.get_origin(annotation)
    if origin is typing.Annotated:
        args = typing.get_args(annotation)
        if not args:
            return None
        head = args[0]
        for meta in args[1:]:
            depends_callable = getattr(meta, "dependency", None)
            if depends_callable is not None:
                return getattr(depends_callable, "__name__", str(depends_callable))
        return _annotation_name(head)
    return _annotation_name(annotation)


def _endpoint_metadata(endpoint: object) -> tuple[str | None, int | None, str | None]:
    try:
        src_file = inspect.getsourcefile(endpoint)
    except TypeError:
        src_file = None
    try:
        lineno = inspect.getsourcelines(endpoint)[1]
    except (OSError, TypeError):
        lineno = None
    module = getattr(endpoint, "__module__", None)
    return (
        str(Path(src_file).relative_to(_PROJECT_ROOT)) if src_file else None,
        lineno,
        module,
    )


def introspect() -> list[dict]:
    rows: list[dict] = []
    for route in app.routes:
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", "")
        if not path.startswith("/api/v1/"):
            # Out of audit scope: root, /health, /docs (when on),
            # FastAPI auto-routes.
            continue
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            continue
        src_file, lineno, module = _endpoint_metadata(endpoint)
        depends_on: list[str] = []
        try:
            sig = inspect.signature(endpoint)
        except (TypeError, ValueError):
            sig = None
        if sig is not None:
            for param in sig.parameters.values():
                tag = _classify_depends(param.annotation)
                if tag and tag not in {"NoneType", "Request"}:
                    depends_on.append(tag)

        for method in sorted(methods - {"HEAD", "OPTIONS"}):
            rows.append(
                {
                    "method": method,
                    "path": path,
                    "name": getattr(route, "name", ""),
                    "router_module": module,
                    "endpoint_qualname": getattr(endpoint, "__qualname__", endpoint.__name__),
                    "endpoint_file": src_file,
                    "endpoint_lineno": lineno,
                    "depends_on": depends_on,
                }
            )
    rows.sort(key=lambda r: (r["path"], r["method"]))
    return rows


def main() -> None:
    rows = introspect()
    json.dump(rows, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
