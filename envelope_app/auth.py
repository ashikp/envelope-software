"""Fixed local login (app gate only — not for remote or high-security use)."""

from __future__ import annotations

import hmac

APP_USERNAME = "ashik"
APP_PASSWORD = "ashik@123"


def verify_fixed_login(username: str, password: str) -> bool:
    """Constant-time compare against fixed credentials."""
    return hmac.compare_digest(username, APP_USERNAME) and hmac.compare_digest(
        password, APP_PASSWORD
    )
