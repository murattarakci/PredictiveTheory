"""
Centralised writable paths.

On shinyapps.io the app directory is **read-only**, so anything that needs
writing (SQLite database, uploaded data files, log files) must live under
a writable location such as /tmp.

Dropbox sync is NOT affected — it continues to be the persistent store.
On startup the app pulls from Dropbox into the writable directory, and
every commit / upload pushes back to Dropbox as before.

Detection: shinyapps.io sets the SHINY_PORT environment variable.
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

_on_shinyapps = bool(os.environ.get("SHINY_PORT"))

if _on_shinyapps:
    # /tmp is writable on shinyapps.io
    WRITABLE_ROOT = Path("/tmp/app_data")
else:
    WRITABLE_ROOT = PROJECT_ROOT

DB_DIR = WRITABLE_ROOT / "db"
DB_PATH = DB_DIR / "poc.db"
DATA_DIR = WRITABLE_ROOT / "data"
LOG_DIR = WRITABLE_ROOT / "logs"

# Ensure all writable directories exist at import time
DB_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
