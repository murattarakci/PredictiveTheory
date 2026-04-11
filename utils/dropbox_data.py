"""
Sync files under data/ with Dropbox when DROPBOX_ACCESS_TOKEN is set.
Remote tree root defaults to /data (configurable via DROPBOX_REMOTE_DATA_PREFIX).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger("app_debug")

from paths import DATA_DIR as LOCAL_DATA_DIR


def _dropbox_client():
    from utils.dropbox_token import get_dropbox_client
    return get_dropbox_client()


def remote_data_prefix() -> str:
    p = (os.environ.get("DROPBOX_REMOTE_DATA_PREFIX") or "/data").strip().replace("\\", "/").rstrip("/")
    if not p.startswith("/"):
        p = "/" + p
    return p


def _remote_path_for_relative(rel: str) -> str:
    rel = rel.replace("\\", "/").lstrip("/")
    base = remote_data_prefix().rstrip("/")
    return f"{base}/{rel}" if rel else base


def upload_data_path(local_path: Path) -> None:
    """Upload a single file under data/ to Dropbox (overwrite)."""
    dbx = _dropbox_client()
    if dbx is None:
        return
    import dropbox.files

    local_path = local_path.resolve()
    try:
        rel = local_path.relative_to(LOCAL_DATA_DIR.resolve())
    except ValueError:
        logger.warning("Dropbox data: skip upload outside data dir: %s", local_path)
        return
    remote = _remote_path_for_relative(rel.as_posix())
    try:
        data = local_path.read_bytes()
        dbx.files_upload(data, remote, mode=dropbox.files.WriteMode.overwrite, mute=True)
        logger.debug("Dropbox data: uploaded %s -> %s", local_path, remote)
    except Exception:
        logger.exception("Dropbox data: upload failed for %s", local_path)


def upload_data_paths(paths: list[Path]) -> None:
    for p in paths:
        upload_data_path(p)


def download_data_from_dropbox() -> None:
    """Download all files under the remote data prefix into local data/."""
    dbx = _dropbox_client()
    if dbx is None:
        return
    import dropbox.exceptions
    import dropbox.files

    base = remote_data_prefix()
    try:
        res = dbx.files_list_folder(base, recursive=True)
    except dropbox.exceptions.AuthError as e:
        logger.warning("Dropbox data: auth failed (token expired?): %s — skipping data download", e)
        return
    except dropbox.exceptions.ApiError as e:
        err = str(e).lower()
        if "not_found" in err or "path/not_found" in err:
            logger.info("Dropbox data: no folder at %s yet", base)
            return
        logger.warning("Dropbox data: list failed: %s", e, exc_info=True)
        return

    entries: list = list(res.entries)
    while res.has_more:
        res = dbx.files_list_folder_continue(res.cursor)
        entries.extend(res.entries)

    files = [e for e in entries if isinstance(e, dropbox.files.FileMetadata)]
    prefix_norm = base.rstrip("/")
    LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)

    for meta in files:
        path_disp = meta.path_display
        pl = path_disp.rstrip("/")
        if pl.lower() == prefix_norm.lower():
            continue
        if not pl.lower().startswith(prefix_norm.lower() + "/") and pl.lower() != prefix_norm.lower():
            continue
        rel = pl[len(prefix_norm) :].lstrip("/")
        if not rel:
            continue
        dest = LOCAL_DATA_DIR / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            dbx.files_download_to_file(str(dest), meta.path_display)
        except dropbox.exceptions.ApiError as e:
            logger.warning("Dropbox data: skip download %s: %s", meta.path_display, e)

    logger.info("Dropbox data: pulled %s files under %s -> %s", len(files), base, LOCAL_DATA_DIR)


def delete_repo_data_folder(user_id: int, repo_name: str) -> None:
    """Remove the entire {user_id}/repo folder on Dropbox (all dataset files)."""
    dbx = _dropbox_client()
    if dbx is None:
        return
    import dropbox.exceptions

    rel = f"{user_id}/{repo_name}".replace("\\", "/")
    remote = _remote_path_for_relative(rel)
    try:
        dbx.files_delete_v2(remote)
        logger.info("Dropbox data: deleted %s", remote)
    except dropbox.exceptions.ApiError as e:
        err = str(e).lower()
        if "not_found" in err or "path/not_found" in err:
            logger.info("Dropbox data: nothing to delete at %s", remote)
            return
        logger.warning("Dropbox data: delete failed: %s", e, exc_info=True)
