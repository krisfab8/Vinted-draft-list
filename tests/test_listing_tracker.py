"""
Unit tests for app/services/listing_tracker.py

All DB operations use a real in-memory SQLite via monkeypatching the _connect()
function. Playwright scraping is fully mocked — no network calls.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _in_memory_connect():
    """Return an in-memory SQLite connection with row_factory set."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    return con


def _make_tracker(monkeypatch):
    """Return tracker module with DB wired to an in-memory SQLite."""
    from app.services import listing_tracker
    # Shared in-memory DB so all calls see each other's writes
    _db = sqlite3.connect(":memory:")
    _db.row_factory = sqlite3.Row
    monkeypatch.setattr(listing_tracker, "_connect", lambda: _db)
    listing_tracker.init_tracker_tables()
    return listing_tracker


def _draft_listing(folder="test_item", draft_url="https://www.vinted.co.uk/items/987654321-blazer"):
    return {
        "folder": folder,
        "draft_url": draft_url,
        "title": "Test Blazer size M",
        "description": "Nice blazer.",
        "ai_price_gbp": 45.0,
        "price_gbp": 55,
        "brand": "Reiss",
        "category": "Men > Blazers",
        "brand_confidence": "high",
        "material_confidence": "medium",
        "warnings": [],
        "pricing_flags": [],
        "profit_warning": False,
    }


# ── _extract_listing_id ────────────────────────────────────────────────────────

class TestExtractListingId:

    def test_extracts_numeric_id(self):
        from app.services.listing_tracker import _extract_listing_id
        url = "https://www.vinted.co.uk/items/987654321-some-blazer"
        assert _extract_listing_id(url) == "987654321"

    def test_returns_none_for_empty_url(self):
        from app.services.listing_tracker import _extract_listing_id
        assert _extract_listing_id("") is None
        assert _extract_listing_id(None) is None

    def test_returns_none_for_no_match(self):
        from app.services.listing_tracker import _extract_listing_id
        assert _extract_listing_id("https://www.vinted.co.uk/profile") is None


# ── init_tracker_tables ───────────────────────────────────────────────────────

class TestInitTrackerTables:

    def test_creates_all_three_tables(self, monkeypatch):
        tracker = _make_tracker(monkeypatch)
        # Tables should already exist after _make_tracker; verify via sqlite_master
        con = tracker._connect()
        names = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "listing_drafts" in names
        assert "listing_snapshots" in names
        assert "listing_performance" in names

    def test_idempotent(self, monkeypatch):
        tracker = _make_tracker(monkeypatch)
        # Calling again should not raise
        tracker.init_tracker_tables()


# ── record_draft_snapshot ─────────────────────────────────────────────────────

class TestRecordDraftSnapshot:

    def test_inserts_row_into_listing_drafts(self, monkeypatch):
        tracker = _make_tracker(monkeypatch)
        listing = _draft_listing()
        tracker.record_draft_snapshot("test_item", listing)

        con = tracker._connect()
        row = con.execute("SELECT * FROM listing_drafts WHERE folder = ?", ("test_item",)).fetchone()
        assert row is not None
        assert row["listing_id"] == "987654321"
        assert row["draft_url"] == listing["draft_url"]
        assert row["brand"] == "Reiss"
        assert row["brand_confidence"] == "high"

    def test_extracts_listing_id_from_url(self, monkeypatch):
        tracker = _make_tracker(monkeypatch)
        listing = _draft_listing(draft_url="https://www.vinted.co.uk/items/111222333-jacket")
        tracker.record_draft_snapshot("item2", listing)

        con = tracker._connect()
        row = con.execute("SELECT listing_id FROM listing_drafts WHERE folder = ?", ("item2",)).fetchone()
        assert row["listing_id"] == "111222333"

    def test_records_price_fields(self, monkeypatch):
        tracker = _make_tracker(monkeypatch)
        listing = _draft_listing()
        tracker.record_draft_snapshot("test_item", listing)

        con = tracker._connect()
        row = con.execute("SELECT ai_price_gbp, final_price_gbp FROM listing_drafts WHERE folder = ?", ("test_item",)).fetchone()
        assert row["ai_price_gbp"] == 45.0
        assert row["final_price_gbp"] == 55

    def test_upserts_on_duplicate_folder(self, monkeypatch):
        tracker = _make_tracker(monkeypatch)
        listing = _draft_listing()
        tracker.record_draft_snapshot("test_item", listing)

        # Second call with different data — should update
        listing2 = dict(listing)
        listing2["price_gbp"] = 70
        listing2["brand"] = "Reiss Updated"
        tracker.record_draft_snapshot("test_item", listing2)

        con = tracker._connect()
        rows = con.execute("SELECT COUNT(*) as cnt FROM listing_drafts WHERE folder = ?", ("test_item",)).fetchone()
        assert rows["cnt"] == 1  # still one row
        updated = con.execute("SELECT brand FROM listing_drafts WHERE folder = ?", ("test_item",)).fetchone()
        assert updated["brand"] == "Reiss Updated"

    def test_never_raises_on_bad_input(self, monkeypatch):
        tracker = _make_tracker(monkeypatch)
        # Should not raise even with empty listing
        tracker.record_draft_snapshot("bad_folder", {})

    def test_stores_pricing_flags_as_json(self, monkeypatch):
        tracker = _make_tracker(monkeypatch)
        listing = _draft_listing()
        listing["pricing_flags"] = ["low_margin"]
        tracker.record_draft_snapshot("test_item", listing)

        con = tracker._connect()
        row = con.execute("SELECT pricing_flags FROM listing_drafts WHERE folder = ?", ("test_item",)).fetchone()
        assert json.loads(row["pricing_flags"]) == ["low_margin"]

    def test_stores_ebay_mid_price(self, monkeypatch):
        tracker = _make_tracker(monkeypatch)
        listing = _draft_listing()
        listing["ebay_suggested_range"] = {"low": 40, "mid": 60, "high": 80, "currency": "GBP"}
        tracker.record_draft_snapshot("test_item", listing)

        con = tracker._connect()
        row = con.execute("SELECT ebay_suggested_price FROM listing_drafts WHERE folder = ?", ("test_item",)).fetchone()
        assert row["ebay_suggested_price"] == 60.0


# ── get_tracker_status ────────────────────────────────────────────────────────

class TestGetTrackerStatus:

    def test_returns_none_when_not_tracked(self, monkeypatch):
        tracker = _make_tracker(monkeypatch)
        result = tracker.get_tracker_status("nonexistent_folder")
        assert result is None

    def test_returns_draft_data_without_performance(self, monkeypatch):
        tracker = _make_tracker(monkeypatch)
        listing = _draft_listing()
        tracker.record_draft_snapshot("test_item", listing)

        result = tracker.get_tracker_status("test_item")
        assert result is not None
        assert result["folder"] == "test_item"
        assert result["listing_id"] == "987654321"
        assert result["draft_url"] == listing["draft_url"]
        # No performance data yet
        assert "views" not in result or result.get("views") is None

    def test_returns_performance_when_present(self, monkeypatch):
        tracker = _make_tracker(monkeypatch)
        listing = _draft_listing()
        tracker.record_draft_snapshot("test_item", listing)

        # Manually insert performance data
        con = tracker._connect()
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        con.execute(
            """INSERT INTO listing_performance
               (folder, listing_id, last_scraped_at, views, favourites, current_price, status, total_scrapes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("test_item", "987654321", now, 42, 7, 55.0, "active", 1)
        )
        con.commit()

        result = tracker.get_tracker_status("test_item")
        assert result["views"] == 42
        assert result["favourites"] == 7
        assert result["status"] == "active"


# ── _append_snapshot ─────────────────────────────────────────────────────────

class TestAppendSnapshot:

    def test_appends_row_to_snapshots(self, monkeypatch):
        tracker = _make_tracker(monkeypatch)
        tracker._append_snapshot("folder1", "123456", views=10, favourites=3, price_gbp=45.0, status_scraped="active")

        con = tracker._connect()
        row = con.execute("SELECT * FROM listing_snapshots WHERE folder = ?", ("folder1",)).fetchone()
        assert row is not None
        assert row["views"] == 10
        assert row["favourites"] == 3
        assert row["price_gbp"] == 45.0

    def test_records_scrape_error(self, monkeypatch):
        tracker = _make_tracker(monkeypatch)
        tracker._append_snapshot("folder1", "123456", scrape_error="timeout")

        con = tracker._connect()
        row = con.execute("SELECT scrape_error FROM listing_snapshots WHERE folder = ?", ("folder1",)).fetchone()
        assert row["scrape_error"] == "timeout"

    def test_multiple_snapshots_accumulate(self, monkeypatch):
        tracker = _make_tracker(monkeypatch)
        tracker._append_snapshot("folder1", "123456", views=10)
        tracker._append_snapshot("folder1", "123456", views=20)

        con = tracker._connect()
        count = con.execute("SELECT COUNT(*) as cnt FROM listing_snapshots WHERE folder = ?", ("folder1",)).fetchone()
        assert count["cnt"] == 2


# ── _upsert_performance ───────────────────────────────────────────────────────

class TestUpsertPerformance:

    def test_inserts_performance_row(self, monkeypatch):
        tracker = _make_tracker(monkeypatch)
        # Insert draft first (needed for days_live JOIN)
        tracker.record_draft_snapshot("folder1", _draft_listing(folder="folder1"))

        data = {
            "views": 15, "favourites": 5, "price_gbp": 50.0,
            "status_scraped": "active", "offers_count": None,
            "sold_price_gbp": None, "sold_price_source": None,
            "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        tracker._upsert_performance("folder1", "987654321", data)

        con = tracker._connect()
        row = con.execute("SELECT * FROM listing_performance WHERE folder = ?", ("folder1",)).fetchone()
        assert row["views"] == 15
        assert row["current_price"] == 50.0
        assert row["total_scrapes"] == 1

    def test_increments_total_scrapes(self, monkeypatch):
        tracker = _make_tracker(monkeypatch)
        tracker.record_draft_snapshot("folder1", _draft_listing(folder="folder1"))

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        data = {"views": 10, "scraped_at": now}
        tracker._upsert_performance("folder1", "987654321", data)
        tracker._upsert_performance("folder1", "987654321", data)

        con = tracker._connect()
        row = con.execute("SELECT total_scrapes FROM listing_performance WHERE folder = ?", ("folder1",)).fetchone()
        assert row["total_scrapes"] == 2

    def test_preserves_sold_date_on_upsert(self, monkeypatch):
        tracker = _make_tracker(monkeypatch)
        tracker.record_draft_snapshot("folder1", _draft_listing(folder="folder1"))

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        sold_data = {
            "views": 50, "price_gbp": 45.0, "status_scraped": "sold",
            "sold_price_gbp": 45.0, "sold_price_source": "scraped",
            "scraped_at": now,
        }
        tracker._upsert_performance("folder1", "987654321", sold_data)

        # Second upsert without sold info should NOT clear sold_date
        active_data = {"views": 51, "status_scraped": "active", "scraped_at": now}
        tracker._upsert_performance("folder1", "987654321", active_data)

        con = tracker._connect()
        row = con.execute("SELECT sold_price_gbp FROM listing_performance WHERE folder = ?", ("folder1",)).fetchone()
        assert row["sold_price_gbp"] == 45.0  # preserved


# ── refresh_tracker (mocked Playwright) ───────────────────────────────────────

class TestRefreshTracker:

    def test_returns_error_when_no_listing_id(self, monkeypatch, tmp_path):
        tracker = _make_tracker(monkeypatch)
        # No draft recorded → no listing_id
        result = tracker.refresh_tracker("no_folder", listing_id=None)
        assert "scrape_error" in result

    def test_returns_error_when_no_auth_state(self, monkeypatch, tmp_path):
        tracker = _make_tracker(monkeypatch)
        # Patch ROOT to tmp_path so auth_state.json definitely doesn't exist
        cfg_mock = MagicMock()
        cfg_mock.ROOT = tmp_path
        monkeypatch.setattr(tracker, "_cfg", lambda: cfg_mock)

        result = tracker.refresh_tracker("some_folder", listing_id="123456")
        assert "scrape_error" in result
        assert "auth_state" in result["scrape_error"]

    def test_scrapes_and_writes_performance(self, monkeypatch, tmp_path):
        tracker = _make_tracker(monkeypatch)

        # Create fake auth_state.json
        auth_state = tmp_path / "auth_state.json"
        auth_state.write_text("{}")
        cfg_mock = MagicMock()
        cfg_mock.ROOT = tmp_path
        monkeypatch.setattr(tracker, "_cfg", lambda: cfg_mock)

        # Mock Playwright scrape
        scraped_data = {
            "views": 33, "favourites": 4, "price_gbp": 55.0,
            "status_scraped": "active", "offers_count": None,
            "sold_price_gbp": None, "sold_price_source": None,
            "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        monkeypatch.setattr(tracker, "_scrape_with_playwright", lambda folder, lid, path: (
            tracker._upsert_performance(folder, lid, scraped_data) or
            tracker._append_snapshot(folder, lid, **{k: v for k, v in scraped_data.items()}) or
            scraped_data
        ))

        # First record a draft
        tracker.record_draft_snapshot("folder1", _draft_listing(folder="folder1"))

        result = tracker.refresh_tracker("folder1", listing_id="987654321")
        assert result.get("views") == 33
        assert result.get("price_gbp") == 55.0

    def test_never_raises_on_playwright_error(self, monkeypatch, tmp_path):
        tracker = _make_tracker(monkeypatch)

        auth_state = tmp_path / "auth_state.json"
        auth_state.write_text("{}")
        cfg_mock = MagicMock()
        cfg_mock.ROOT = tmp_path
        monkeypatch.setattr(tracker, "_cfg", lambda: cfg_mock)

        # Playwright throws
        def _boom(folder, lid, path):
            raise RuntimeError("Playwright crash")

        monkeypatch.setattr(tracker, "_scrape_with_playwright", _boom)

        result = tracker.refresh_tracker("folder1", listing_id="123456")
        assert "scrape_error" in result


# ── item_store integration ────────────────────────────────────────────────────

class TestItemStoreSold:
    """Verify 'sold' is now an accepted status value."""

    def test_sold_is_valid_status(self):
        from app.services.item_store import _STATUS_VALUES
        assert "sold" in _STATUS_VALUES
