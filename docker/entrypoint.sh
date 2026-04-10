#!/bin/sh
set -e
cd /app
# Load .env if present; pull poc.db from Dropbox before db.models initializes (via init_db).
python -c "
from pathlib import Path
import os
try:
    from dotenv import load_dotenv
    load_dotenv(Path('.env').resolve())
except ImportError:
    pass
from utils.dropbox_token import is_dropbox_configured
if is_dropbox_configured():
    from utils.dropbox_data import download_data_from_dropbox
    from utils.dropbox_sqlite import download_database_from_dropbox
    download_database_from_dropbox()
    download_data_from_dropbox()
"
python -m db.init_db
python -m db.seed_users
exec shiny run app:app --host 0.0.0.0 --port 8500
