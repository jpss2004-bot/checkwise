"""Offline common-/breached-password denylist (AUTH G-4).

The password policy already enforces length + character classes, but that
still admits high-frequency passwords that *meet* the rules — ``Password1234``,
``Bienvenido2026``, ``Checkwise2026`` — which are the first guesses in any
credential-stuffing run. ISO 27002:2022 5.17 / 8.5 expect a check against
commonly-used and compromised passwords.

This list is intentionally small, bundled (no network call, no new
dependency, no HIBP round-trip), and tuned to passwords that would otherwise
pass our ≥12-char + upper + lower + digit gate. It is not a substitute for a
full HIBP k-anonymity check (a recommended next step) — it closes the
cheapest, most-abused window.

``is_common_password`` checks two ways:
  1. case-insensitive exact match against ``_COMMON_PASSWORDS``;
  2. the alphabetic "base" (digits/symbols stripped) against
     ``_COMMON_BASE_WORDS`` — catches the ``Word + 1234`` / ``Word@123``
     family without enumerating every numeric suffix.
"""

from __future__ import annotations

# Exact passwords (lowercased) that satisfy the complexity rules yet are
# top entries in public breach corpora and Spanish-market wordlists.
_COMMON_PASSWORDS: frozenset[str] = frozenset(
    {
        "password1234",
        "password123!",
        "password@123",
        "passw0rd1234",
        "qwerty123456",
        "qwertyuiop12",
        "1q2w3e4r5t6y",
        "iloveyou1234",
        "welcome12345",
        "welcome@1234",
        "admin1234567",
        "administrator1",
        "letmein12345",
        "monkey123456",
        "dragon123456",
        "football1234",
        "superman1234",
        "trustno12345",
        "michael12345",
        "sunshine1234",
        "princess1234",
        "abcd12345678",
        "abcdefgh1234",
        "changeme1234",
        "secret123456",
        "master123456",
        "google123456",
        "facebook1234",
        "whatsapp1234",
        "samsung12345",
        # Spanish-market high-frequency
        "bienvenido123",
        "bienvenido2025",
        "bienvenido2026",
        "contraseña123",
        "contrasena123",
        "mexico123456",
        "hola12345678",
        "teamo1234567",
        "fernando1234",
        "alejandro123",
        "guadalupe123",
        "cumpleaños12",
        # Product / company terms with common suffixes
        "checkwise123",
        "checkwise1234",
        "checkwise2025",
        "checkwise2026",
        "legalshelf123",
        "legalshelf2026",
        "repse1234567",
    }
)

# Alphabetic base tokens. A password whose letters-only core equals one of
# these (and is long enough to be the dominant component) is rejected
# regardless of the numeric/symbol suffix.
_COMMON_BASE_WORDS: frozenset[str] = frozenset(
    {
        "password",
        "passw",
        "contraseña",
        "contrasena",
        "qwerty",
        "qwertyuiop",
        "welcome",
        "bienvenido",
        "bienvenida",
        "letmein",
        "iloveyou",
        "changeme",
        "administrator",
        "checkwise",
        "legalshelf",
    }
)


def is_common_password(value: str) -> bool:
    """Return True if ``value`` is a well-known/easily-guessed password."""
    lowered = value.strip().lower()
    if not lowered:
        return False
    if lowered in _COMMON_PASSWORDS:
        return True
    alpha = "".join(ch for ch in lowered if ch.isalpha())
    return len(alpha) >= 5 and alpha in _COMMON_BASE_WORDS
