"""Delete my data: every listing, photo, sale, profile and log for this account.

Removed folders are recorded so phone backups and cloud copies can't restore them.
Shared reference data (price memory, categories) is not personal and is kept.
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path


def _empty_sqlite(path: Path) -> None:
    if not path.is_file():
        return
    with sqlite3.connect(path, timeout=10) as db:
        tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        for table in tables:
            db.execute(f'DELETE FROM "{table}"')


def wipe(items_dir: Path, cloud=None) -> dict:
    from app import run_logger
    from app.services import item_store, model_usage, removed_items, sales_history, user_profile
    folders = [d for d in Path(items_dir).iterdir() if d.is_dir() and not d.name.startswith("_")] \
        if Path(items_dir).exists() else []
    removed_items.add(*(d.name for d in folders))
    for folder in folders:
        shutil.rmtree(folder, ignore_errors=True)
    _empty_sqlite(Path(sales_history.DB_PATH))
    _empty_sqlite(Path(item_store.DB_PATH))
    for path in (user_profile._PATH, run_logger.LOG_PATH, run_logger.CORRECTIONS_PATH, model_usage.LEDGER_PATH):
        Path(path).unlink(missing_ok=True)
    from app import web
    Path(web.COST_LOG).unlink(missing_ok=True)
    if cloud:
        cloud.delete_profile()
        cloud.request_sync()        # deletes the cloud copies of every removed listing
    return {"listings": len(folders)}
