"""
SQLite-backed metadata index for item status and review state.

This module is an index over listing.json — it does NOT replace it.
listing.json remains the source of truth for all listing data.

The DB answers:
- What is the current lifecycle status of this item?
- Which items need operator review?

DB location: data/items.db  (runtime artifact, excluded from git)

Status values:
    new           — just created, not yet evaluated
    needs_review  — has low confidence, warnings, or error tags
    ready         — pipeline clean or operator approved
    drafted       — Vinted draft created successfully
    error         — last draft creation failed

All DB writes are wrapped in try/except — a DB failure must never
crash the main pipeline.
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_DATA_DIR = Path(__file__).parent.parent.parent / "data"
DB_PATH = _DATA_DIR / "items.db"

_STATUS_VALUES = frozenset({"new", "needs_review", "ready", "drafted", "error", "sold"})

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS items (
    folder            TEXT PRIMARY KEY,
    status            TEXT NOT NULL DEFAULT 'new',
    review_needed     INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT,
    status_updated_at TEXT,
    last_error        TEXT
);
"""


# ── Connection helper ─────────────────────────────────────────────────────────

def _connect() -> sqlite3.Connection:
    _DATA_DIR.mkdir(exist_ok=True)
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    return con


# ── Public API ────────────────────────────────────────────────────────────────

def init_db() -> None:
    """Create the items table and tracker tables if they do not exist.

    Safe to call multiple times (idempotent).
    Called once at Flask app startup.
    """
    with _connect() as con:
        con.execute(_CREATE_TABLE)
    # Tracker tables live in the same DB — init lazily to avoid circular imports
    try:
        from app.services import listing_tracker
        listing_tracker.init_tracker_tables()
    except Exception:
        pass


def get_status(folder: str) -> str | None:
    """Return the current status for a folder, or None if not in DB."""
    try:
        with _connect() as con:
            row = con.execute(
                "SELECT status FROM items WHERE folder = ?", (folder,)
            ).fetchone()
            return row["status"] if row else None
    except Exception:
        return None


def set_status(
    folder: str,
    status: str,
    *,
    review_needed: bool = False,
    last_error: str | None = None,
) -> None:
    """Upsert the status for a folder.

    Creates the row if it does not exist, updates it if it does.
    All errors are silently swallowed — callers must not depend on this succeeding.
    """
    if status not in _STATUS_VALUES:
        return
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        with _connect() as con:
            con.execute(
                """
                INSERT INTO items (folder, status, review_needed, created_at, status_updated_at, last_error)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(folder) DO UPDATE SET
                    status            = excluded.status,
                    review_needed     = excluded.review_needed,
                    status_updated_at = excluded.status_updated_at,
                    last_error        = excluded.last_error
                """,
                (folder, status, int(review_needed), now, now, last_error),
            )
    except Exception:
        pass


def derive_status(listing: dict) -> tuple[str, bool]:
    """Derive (status, review_needed) from a listing dict.

    Pure function — no DB access. Uses this priority order:
    1. draft_error present           → error
    2. draft_url present             → drafted
    3. error_tags non-empty          → needs_review
    4. warnings non-empty            → needs_review
    5. brand_confidence == "low"     → needs_review
    6. low_confidence_fields present → needs_review
    7. otherwise                     → ready
    """
    if listing.get("draft_error"):
        return "error", False

    if listing.get("draft_url"):
        return "drafted", False

    needs_review = (
        bool(listing.get("error_tags"))
        or bool(listing.get("warnings"))
        or listing.get("brand_confidence") == "low"
        or bool(listing.get("low_confidence_fields"))
    )
    return ("needs_review" if needs_review else "ready"), needs_review


def sync_from_listing(folder: str, listing: dict) -> None:
    """Write status to DB if this folder has no existing record.

    Used for lazy migration of pre-existing items.
    Does nothing if a record already exists.
    All errors silently swallowed.
    """
    try:
        with _connect() as con:
            row = con.execute(
                "SELECT folder FROM items WHERE folder = ?", (folder,)
            ).fetchone()
            if row:
                return  # already tracked — do not overwrite
        status, review_needed = derive_status(listing)
        set_status(folder, status, review_needed=review_needed)
    except Exception:
        pass


def get_items_needing_review() -> list[str]:
    """Return folder names where review_needed = 1, most recently updated first."""
    try:
        with _connect() as con:
            rows = con.execute(
                """
                SELECT folder FROM items
                WHERE review_needed = 1
                ORDER BY status_updated_at DESC
                """,
            ).fetchall()
            return [r["folder"] for r in rows]
    except Exception:
        return []
