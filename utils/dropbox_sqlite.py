"""
Sync SQLite (db/poc.db) with Dropbox when DROPBOX_ACCESS_TOKEN is set.
Lives under utils/ so importing it does not load db.models before pull.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger("app_debug")

from paths import DB_DIR, DB_PATH as LOCAL_DB_PATH
REMOTE_DB_PATH = os.environ.get("DROPBOX_REMOTE_DB_PATH", "/poc.db").strip()
if not REMOTE_DB_PATH.startswith("/"):
    REMOTE_DB_PATH = "/" + REMOTE_DB_PATH


def _dropbox_client():
    from utils.dropbox_token import get_dropbox_client
    return get_dropbox_client()


def download_database_from_dropbox() -> None:
    """If Dropbox is configured, download remote poc.db over the local file (if remote exists)."""
    dbx = _dropbox_client()
    if dbx is None:
        return
    import dropbox.exceptions

    LOCAL_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        dbx.files_download_to_file(str(LOCAL_DB_PATH), REMOTE_DB_PATH)
        logger.info("Dropbox: downloaded %s -> %s", REMOTE_DB_PATH, LOCAL_DB_PATH)
    except dropbox.exceptions.AuthError as e:
        logger.warning("Dropbox: auth failed (token expired?): %s — starting with local/new SQLite", e)
    except dropbox.exceptions.ApiError as e:
        err_s = str(e).lower()
        if "not_found" in err_s or "path/not_found" in err_s:
            logger.info("Dropbox: no database at %s yet; using local/new SQLite", REMOTE_DB_PATH)
            return
        logger.warning("Dropbox: download failed: %s", e, exc_info=True)


def upload_database_to_dropbox() -> None:
    """Upload local poc.db to Dropbox (overwrite). No-op if not configured or file missing."""
    dbx = _dropbox_client()
    if dbx is None or not LOCAL_DB_PATH.is_file():
        return
    import dropbox.files

    try:
        data = LOCAL_DB_PATH.read_bytes()
        dbx.files_upload(data, REMOTE_DB_PATH, mode=dropbox.files.WriteMode.overwrite)
        logger.debug("Dropbox: uploaded %s -> %s", LOCAL_DB_PATH, REMOTE_DB_PATH)
    except Exception:
        logger.exception("Dropbox: upload failed")
