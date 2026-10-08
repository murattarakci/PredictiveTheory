"""
Resolve Dropbox OAuth token with automatic refresh.

Dropbox short-lived access tokens expire after ~4 hours.  To avoid manual
rotation we use the *refresh-token* flow:

  1.  Set DROPBOX_APP_KEY, DROPBOX_APP_SECRET, and DROPBOX_REFRESH_TOKEN as
      environment variables (locally in .env, on shinyapps.io in the app's
      Settings > Vars). Never put credential values in this file.
  2.  The Dropbox SDK will transparently obtain a fresh short-lived token
      every time one is needed — no manual copy-paste required.

If only a short-lived access token is available (legacy setup), it will
still be used but will stop working once it expires.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("app_debug")

# ── Legacy short-lived access token (expires in ~4 h), from the environment only ──
LEGACY_DROPBOX_ACCESS_TOKEN = os.environ.get("DROPBOX_ACCESS_TOKEN", "").strip()

# ── Refresh-token credentials (recommended — tokens auto-renew) ─────────
# Get these from https://www.dropbox.com/developers/apps :
#   APP_KEY and APP_SECRET are on the app's Settings page.
#   REFRESH_TOKEN: use the OAuth 2 authorization flow (see README or below).
DROPBOX_APP_KEY = os.environ.get("DROPBOX_APP_KEY", "").strip()
DROPBOX_APP_SECRET = os.environ.get("DROPBOX_APP_SECRET", "").strip()
DROPBOX_REFRESH_TOKEN = os.environ.get("DROPBOX_REFRESH_TOKEN", "").strip()


def _has_refresh_credentials() -> bool:
    return bool(DROPBOX_APP_KEY and DROPBOX_APP_SECRET and DROPBOX_REFRESH_TOKEN)


def get_dropbox_client():
    """
    Return a ready-to-use ``dropbox.Dropbox`` client, or *None*.

    Prefers the refresh-token flow (tokens never expire).  Falls back to the
    legacy short-lived access token if refresh credentials aren't set.
    """
    import dropbox

    # ── Refresh-token path (auto-renewing) ──────────────────────────────
    if _has_refresh_credentials():
        try:
            dbx = dropbox.Dropbox(
                oauth2_refresh_token=DROPBOX_REFRESH_TOKEN,
                app_key=DROPBOX_APP_KEY,
                app_secret=DROPBOX_APP_SECRET,
            )
            # Force a token refresh now so we fail fast rather than later
            dbx.check_and_refresh_access_token()
            logger.debug("Dropbox: using refresh-token flow (auto-renewing)")
            return dbx
        except Exception:
            logger.exception("Dropbox: refresh-token flow failed, trying legacy token")

    # ── Legacy short-lived token path ───────────────────────────────────
    token = LEGACY_DROPBOX_ACCESS_TOKEN.strip()
    if token:
        logger.debug("Dropbox: using legacy short-lived access token")
        return dropbox.Dropbox(oauth2_access_token=token)

    return None


# ── Backwards-compatible helpers (used by other modules) ────────────────

def get_dropbox_access_token() -> str:
    """Return a raw access token string (legacy helper)."""
    return LEGACY_DROPBOX_ACCESS_TOKEN.strip()


def is_dropbox_configured() -> bool:
    return _has_refresh_credentials() or bool(get_dropbox_access_token())
