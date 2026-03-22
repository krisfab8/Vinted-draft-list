"""
Tests for app/services/item_store.py

Covers:
- init_db: creates table idempotently
- get_status / set_status: read/write/upsert
- derive_status: pure function, priority rules
- sync_from_listing: lazy migration, skips existing records
- get_items_needing_review: filtered query

All tests use a temporary DB via monkeypatching DB_PATH.
No Flask app, no filesystem items, no network.
"""
import pytest
import sqlite3
from pathlib import Path
from unittest.mock import patch


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """Redirect DB_PATH to a temp directory for every test."""
    import app.services.item_store as store
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "items.db")
    monkeypatch.setattr(store, "_DATA_DIR", tmp_path)
    store.init_db()
    yield store


# ── init_db ───────────────────────────────────────────────────────────────────

class TestInitDb:

    def test_creates_table(self, tmp_db):
        con = sqlite3.connect(str(tmp_db.DB_PATH))
        tables = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='items'"
        ).fetchall()
        con.close()
        assert len(tables) == 1

    def test_idempotent(self, tmp_db):
        # Calling init_db a second time should not raise
        tmp_db.init_db()
        tmp_db.init_db()


# ── set_status / get_status ───────────────────────────────────────────────────

class TestSetGetStatus:

    def test_set_and_get(self, tmp_db):
        tmp_db.set_status("folder_1", "needs_review")
        assert tmp_db.get_status("folder_1") == "needs_review"

    def test_get_missing_returns_none(self, tmp_db):
        assert tmp_db.get_status("nonexistent") is None

    def test_upsert_updates_existing(self, tmp_db):
        tmp_db.set_status("folder_1", "needs_review")
        tmp_db.set_status("folder_1", "ready")
        assert tmp_db.get_status("folder_1") == "ready"

    def test_review_needed_flag_stored(self, tmp_db):
        tmp_db.set_status("folder_1", "needs_review", review_needed=True)
        con = sqlite3.connect(str(tmp_db.DB_PATH))
        row = con.execute("SELECT review_needed FROM items WHERE folder='folder_1'").fetchone()
        con.close()
        assert row[0] == 1

    def test_review_needed_false_by_default(self, tmp_db):
        tmp_db.set_status("folder_1", "ready")
        con = sqlite3.connect(str(tmp_db.DB_PATH))
        row = con.execute("SELECT review_needed FROM items WHERE folder='folder_1'").fetchone()
        con.close()
        assert row[0] == 0

    def test_last_error_stored(self, tmp_db):
        tmp_db.set_status("folder_1", "error", last_error="Playwright crash")
        con = sqlite3.connect(str(tmp_db.DB_PATH))
        row = con.execute("SELECT last_error FROM items WHERE folder='folder_1'").fetchone()
        con.close()
        assert row[0] == "Playwright crash"

    def test_invalid_status_ignored(self, tmp_db):
        tmp_db.set_status("folder_1", "banana")
        assert tmp_db.get_status("folder_1") is None

    def test_status_updated_at_written(self, tmp_db):
        tmp_db.set_status("folder_1", "ready")
        con = sqlite3.connect(str(tmp_db.DB_PATH))
        row = con.execute("SELECT status_updated_at FROM items WHERE folder='folder_1'").fetchone()
        con.close()
        assert row[0] is not None

    def test_created_at_written(self, tmp_db):
        tmp_db.set_status("folder_1", "new")
        con = sqlite3.connect(str(tmp_db.DB_PATH))
        row = con.execute("SELECT created_at FROM items WHERE folder='folder_1'").fetchone()
        con.close()
        assert row[0] is not None


# ── derive_status ─────────────────────────────────────────────────────────────

class TestDeriveStatus:

    def test_draft_error_gives_error(self, tmp_db):
        listing = {"draft_error": "Playwright crash"}
        status, review = tmp_db.derive_status(listing)
        assert status == "error"
        assert review is False

    def test_draft_url_gives_drafted(self, tmp_db):
        listing = {"draft_url": "https://vinted.co.uk/items/123"}
        status, review = tmp_db.derive_status(listing)
        assert status == "drafted"
        assert review is False

    def test_draft_error_takes_priority_over_draft_url(self, tmp_db):
        listing = {"draft_error": "fail", "draft_url": "https://vinted.co.uk/items/123"}
        status, _ = tmp_db.derive_status(listing)
        assert status == "error"

    def test_error_tags_gives_needs_review(self, tmp_db):
        listing = {"error_tags": ["brand"]}
        status, review = tmp_db.derive_status(listing)
        assert status == "needs_review"
        assert review is True

    def test_warnings_gives_needs_review(self, tmp_db):
        listing = {"warnings": ["low_brand_confidence"]}
        status, review = tmp_db.derive_status(listing)
        assert status == "needs_review"
        assert review is True

    def test_low_brand_confidence_gives_needs_review(self, tmp_db):
        listing = {"brand_confidence": "low"}
        status, review = tmp_db.derive_status(listing)
        assert status == "needs_review"
        assert review is True

    def test_medium_brand_confidence_does_not_trigger_review(self, tmp_db):
        listing = {"brand_confidence": "medium"}
        status, review = tmp_db.derive_status(listing)
        assert status == "ready"
        assert review is False

    def test_low_confidence_fields_gives_needs_review(self, tmp_db):
        listing = {"low_confidence_fields": ["material"]}
        status, review = tmp_db.derive_status(listing)
        assert status == "needs_review"
        assert review is True

    def test_clean_listing_gives_ready(self, tmp_db):
        listing = {
            "brand": "Barbour",
            "brand_confidence": "high",
            "warnings": [],
            "low_confidence_fields": [],
            "error_tags": [],
        }
        status, review = tmp_db.derive_status(listing)
        assert status == "ready"
        assert review is False

    def test_empty_listing_gives_ready(self, tmp_db):
        status, review = tmp_db.derive_status({})
        assert status == "ready"
        assert review is False


# ── sync_from_listing ─────────────────────────────────────────────────────────

class TestSyncFromListing:

    def test_writes_status_when_missing(self, tmp_db):
        listing = {"warnings": ["low_brand_confidence"]}
        tmp_db.sync_from_listing("folder_1", listing)
        assert tmp_db.get_status("folder_1") == "needs_review"

    def test_does_not_overwrite_existing(self, tmp_db):
        tmp_db.set_status("folder_1", "drafted")
        listing = {"warnings": ["low_brand_confidence"]}
        tmp_db.sync_from_listing("folder_1", listing)
        # Should still be "drafted" — existing record not overwritten
        assert tmp_db.get_status("folder_1") == "drafted"

    def test_clean_listing_syncs_to_ready(self, tmp_db):
        tmp_db.sync_from_listing("folder_2", {"brand_confidence": "high"})
        assert tmp_db.get_status("folder_2") == "ready"


# ── get_items_needing_review ──────────────────────────────────────────────────

class TestGetItemsNeedingReview:

    def test_returns_review_needed_folders(self, tmp_db):
        tmp_db.set_status("a", "needs_review", review_needed=True)
        tmp_db.set_status("b", "ready", review_needed=False)
        tmp_db.set_status("c", "needs_review", review_needed=True)
        result = tmp_db.get_items_needing_review()
        assert set(result) == {"a", "c"}

    def test_excludes_non_review_folders(self, tmp_db):
        tmp_db.set_status("clean", "ready", review_needed=False)
        result = tmp_db.get_items_needing_review()
        assert "clean" not in result

    def test_empty_when_no_review_items(self, tmp_db):
        tmp_db.set_status("x", "drafted", review_needed=False)
        assert tmp_db.get_items_needing_review() == []

    def test_returns_empty_list_when_db_empty(self, tmp_db):
        assert tmp_db.get_items_needing_review() == []
