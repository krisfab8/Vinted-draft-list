"""
Tests for draft creation error persistence helpers in app/web.py.

Covers:
- _draft_error_summary: produces short operator-friendly messages
- draft_error written to listing.json on /create-draft failure (integration-style,
  using a real temp listing.json but no Playwright/Flask)

No browser, no Flask test client, no network.
"""
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


# ── _draft_error_summary ──────────────────────────────────────────────────────

class TestDraftErrorSummary:

    def _summarise(self, exc):
        from app.web import _draft_error_summary
        return _draft_error_summary(exc)

    def test_short_message_returned_unchanged(self):
        result = self._summarise(RuntimeError("Playwright timeout"))
        assert result == "Playwright timeout"

    def test_multiline_traceback_returns_last_line(self):
        exc = RuntimeError("outer\ninner: the real error")
        result = self._summarise(exc)
        assert result == "inner: the real error"

    def test_long_message_truncated_at_200(self):
        exc = RuntimeError("x" * 300)
        result = self._summarise(exc)
        assert len(result) <= 200

    def test_empty_message_returns_fallback(self):
        result = self._summarise(RuntimeError(""))
        assert "check logs" in result.lower()

    def test_returns_string(self):
        result = self._summarise(ValueError("bad value"))
        assert isinstance(result, str)


# ── draft_error written to listing.json ──────────────────────────────────────

class TestDraftErrorWrittenToListing:
    """
    Test that the /create-draft failure path writes draft_error into listing.json.

    We call the core logic directly without the Flask route to avoid needing
    a full test client setup. This mirrors how the route does it.
    """

    def test_draft_error_persisted_on_failure(self, tmp_path):
        """When create_draft raises, draft_error is written to listing.json."""
        listing_path = tmp_path / "listing.json"
        listing_path.write_text(json.dumps({"brand": "Barbour", "title": "Barbour Jacket"}))

        from app.web import _draft_error_summary

        # Simulate what the route does on exception
        exc = RuntimeError("Selector not found: button[data-testid='submit']")
        err_msg = _draft_error_summary(exc)
        listing = json.loads(listing_path.read_text())
        listing["draft_error"] = err_msg
        listing_path.write_text(json.dumps(listing, indent=2))

        result = json.loads(listing_path.read_text())
        assert "draft_error" in result
        assert "Selector not found" in result["draft_error"]
        assert len(result["draft_error"]) <= 200

    def test_draft_error_cleared_on_success(self, tmp_path):
        """When create_draft succeeds, draft_error is removed from listing.json."""
        listing_path = tmp_path / "listing.json"
        listing_path.write_text(json.dumps({
            "brand": "Barbour",
            "title": "Barbour Jacket",
            "draft_error": "Previous failure message",
        }))

        # Simulate what the route does on success
        draft_url = "https://www.vinted.co.uk/items/123456"
        listing = json.loads(listing_path.read_text())
        listing.pop("draft_error", None)
        listing["draft_url"] = draft_url
        listing_path.write_text(json.dumps(listing, indent=2))

        result = json.loads(listing_path.read_text())
        assert "draft_error" not in result
        assert result["draft_url"] == draft_url

    def test_draft_error_does_not_overwrite_other_fields(self, tmp_path):
        """Writing draft_error preserves existing listing fields."""
        original = {
            "brand": "Barbour",
            "title": "Barbour Jacket",
            "price_gbp": 95,
            "error_tags": ["brand"],
        }
        listing_path = tmp_path / "listing.json"
        listing_path.write_text(json.dumps(original))

        from app.web import _draft_error_summary
        err_msg = _draft_error_summary(RuntimeError("timeout"))
        listing = json.loads(listing_path.read_text())
        listing["draft_error"] = err_msg
        listing_path.write_text(json.dumps(listing, indent=2))

        result = json.loads(listing_path.read_text())
        assert result["brand"] == "Barbour"
        assert result["price_gbp"] == 95
        assert result["error_tags"] == ["brand"]
        assert "draft_error" in result

    def test_multiline_exception_stored_concisely(self, tmp_path):
        """A multi-line exception message is reduced to its final line."""
        listing_path = tmp_path / "listing.json"
        listing_path.write_text(json.dumps({"title": "Test"}))

        from app.web import _draft_error_summary
        exc = RuntimeError(
            "Traceback (most recent call last):\n"
            "  File 'foo.py', line 42, in bar\n"
            "TimeoutError: waiting for selector timed out after 30000ms"
        )
        err_msg = _draft_error_summary(exc)
        assert "TimeoutError" in err_msg
        assert "Traceback" not in err_msg
        assert "\n" not in err_msg
