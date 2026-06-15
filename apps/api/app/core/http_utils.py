"""Shared HTTP response helpers."""

from __future__ import annotations

from urllib.parse import quote


def content_disposition_header(disposition_kind: str, filename: str) -> str:
    """Build an ASCII-safe, injection-proof ``Content-Disposition`` value.

    ``filename`` is frequently attacker-controlled — it originates from
    the provider-supplied upload name (``Document.original_filename``),
    which is stored verbatim. Interpolating it raw into the header
    (``filename="{name}"``) lets a name containing ``"`` / ``;`` break
    out of the quoted value and spoof the saved filename or inject extra
    disposition params for whoever downloads it (client / admin /
    auditor).

    This strips quotes, backslashes, semicolons and control/non-ASCII
    chars from the ASCII fallback so it can't escape the quoted value,
    and preserves the real (UTF-8) name via the RFC 5987 ``filename*``
    parameter. Mirrors the hardened reviewer-download path so every
    file-serving endpoint sanitizes identically.
    """
    safe_fallback = (
        "".join(
            char if 32 <= ord(char) < 127 and char not in {'"', "\\", ";"} else "_"
            for char in filename
        ).strip()
        or "documento.pdf"
    )
    return (
        f'{disposition_kind}; filename="{safe_fallback}"; '
        f"filename*=UTF-8''{quote(filename)}"
    )
