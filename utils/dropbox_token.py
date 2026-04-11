"""
Resolve Dropbox OAuth token with automatic refresh.

Dropbox short-lived access tokens expire after ~4 hours.  To avoid manual
rotation we use the *refresh-token* flow:

  1.  Store DROPBOX_APP_KEY, DROPBOX_APP_SECRET, and DROPBOX_REFRESH_TOKEN
      (either as env vars or as the constants below).
  2.  The Dropbox SDK will transparently obtain a fresh short-lived token
      every time one is needed — no manual copy-paste required.

If only a short-lived access token is available (legacy setup), it will
still be used but will stop working once it expires.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("app_debug")

# ── Legacy short-lived access token (expires in ~4 h) ───────────────────
# Keep this as a fallback until the refresh-token flow is set up.
HARDCODED_DROPBOX_ACCESS_TOKEN = "sl.u.AGbEGgv4gp2QQ1gJd6Dk8xXqfa54m3440bnwzfnzmgHi07FjqVBjx65ewuaM5f1HuE996KtUqRVyrZqyUFdpPd8Eo7ef501BV384E-ltgfo0OJ2WBZ-eqJ0-1_ZveEe22Sf6PJsorpOE0o7ifox3SBYVx_IOD0tSGRxZBbQzr1JFRVitAg8Uvqa8AlhArOc2tb26M1LSzflyaBfIj_eAmmVWk7_BhL5tfrH45qUXaeQcty-aFp_i4Mw2afuJMO_xmdpKtn0fK9szau2T0YRTmxduG3xDE0QZdGvHnkLoYgU1r4CuTW4BzU3Lc0IrJXLAUExJytjUc2R3OMF9CulFcWlWduU69jSzIn-6RKNtxCsYIGPDfiarHkHe_GvPlGcB-jm_yqJ4b7dwH83_m-9Tdh0xfUSwSDyc8dtoZmtaQyyYFgbI0P2AfgLD_yyr4eB62Ve79q-wjHBwluIhVRpLDHtUN_HkCKrgC4tr8rSs8GTuZY5tTUBJE8MGhIaqxIdSzFwhSOAv8q4ytq7ELmowPX6z8cI79jkMxSZ4UkJ2Up_TkBFkuF4-g00q05rNKeBocyHgFQKrSNAAAbIw2FJwHWy9PZNqAJnIHgfdBWyVy_r9IY843SZWd7czkBtWkroBCHwmHIuo5EOfW_P07dbikFHB88caAvEpblGCHsMA55vOszzLOtsOz-fZ6Jq5b5chMvYQrbcKOtVWeqhACZUxyJquYpoHK_Mp7lP-SVnJA66iiLvO1q9QZARGL1gM_GWQH44ow0V71vW9mXqeDTiAvhkl-KZSGprY-GYToz6rMNfvaXJ8j_Wzne8T_60R-uVE_kRcuDyfj64l8Az6W8gCBb8clVBs7FndFepHQP1tiMcL67KYXZ0IBmQnXNbI_a-XQ-RKgkhzyN2IJM8FhQSKWbr0O9bKcuWLUC-TDJs65PTqGOv4hAJiZaE3vVzJP63R1sI_MiGrLOdxv8t331oTra8H0o5y_abc9vwWPbz2NXpib074OamZhyQKcaaFwC1GlyHlAo14syhmK4ipkP9qt7uDHwRpwrMNU65vkqYlhuvNKLsh_iLrf2cvkfcTaLTLFmtnr5NCbU1eMYYHp2saHGxYpsvP5Rfp_ThXW9Xn-TXTOyg7z9qn6yIdz4M1gG-9onOreWTgTuqXNLZOnz6EJpyaPoOuXTNucLsIsOoU4i_dwtd6cm7ymBfrdVaw6EtIjTzd7j685QU_S9iGzAgyWkrMwWFSuninkIBTS89keAnC7gf_H3q8PeKzP97Y0D5pSRniJrSUN88Yhv4b1UF2w9MD9XH2GTe_OKgJRKDNbjgUdaXGzJ59xElnnlS5uCEn4RA"

# ── Refresh-token credentials (recommended — tokens auto-renew) ─────────
# Get these from https://www.dropbox.com/developers/apps :
#   APP_KEY and APP_SECRET are on the app's Settings page.
#   REFRESH_TOKEN: use the OAuth 2 authorization flow (see README or below).
DROPBOX_APP_KEY = os.environ.get("DROPBOX_APP_KEY", "zywtzhty51qrxt0").strip()
DROPBOX_APP_SECRET = os.environ.get("DROPBOX_APP_SECRET", "v12ohz21zbldox0").strip()
DROPBOX_REFRESH_TOKEN = os.environ.get("DROPBOX_REFRESH_TOKEN", "rMQerRgp8cAAAAAAAAAAAXU2IvoXUPOW0j6KmpNZeblGAx6DLWjVheKiSf3qQGRz").strip()


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
    token = (os.environ.get("DROPBOX_ACCESS_TOKEN") or HARDCODED_DROPBOX_ACCESS_TOKEN or "").strip()
    if token:
        logger.debug("Dropbox: using legacy short-lived access token")
        return dropbox.Dropbox(oauth2_access_token=token)

    return None


# ── Backwards-compatible helpers (used by other modules) ────────────────

def get_dropbox_access_token() -> str:
    """Return a raw access token string (legacy helper)."""
    return (os.environ.get("DROPBOX_ACCESS_TOKEN") or HARDCODED_DROPBOX_ACCESS_TOKEN or "").strip()


def is_dropbox_configured() -> bool:
    return _has_refresh_credentials() or bool(get_dropbox_access_token())
