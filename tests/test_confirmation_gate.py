"""
Integration tests for the /create-draft pre-flight confirmation gate.

Uses Flask test client. Mocks draft_creator.create_draft to avoid Playwright.
"""
import json
import pytest
from unittest.mock import patch


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_listing(**kwargs):
    base = {
        "brand": "Barbour",
        "item_type": "wax jacket",
        "title": "Barbour Wax Jacket olive size M",
        "description": "Classic wax jacket.",
        "tagged_size": "M",
        "normalized_size": "M",
        "price_gbp": 65,
        "category": "Men > Jackets > Field",
        "brand_confidence": "high",
    }
    base.update(kwargs)
    return base


def _setup_item(tmp_path, folder, listing):
    item_dir = tmp_path / folder
    item_dir.mkdir()
    (item_dir / "listing.json").write_text(json.dumps(listing))
    return item_dir


# Valid category that resolves in CATEGORY_NAV
_VALID_CATEGORY = "Men > Jackets > Field"
# Category that does NOT resolve
_INVALID_CATEGORY = "Men > Outerwear > Unknown Style"


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app.web import app as flask_app
    monkeypatch.setattr("app.web.ITEMS_DIR", tmp_path)
    monkeypatch.setattr("app.web._DRAFT_ENABLED", True)
    with flask_app.test_client() as c:
        c._tmp_path = tmp_path
        yield c


def _post_create_draft(client, folder):
    return client.post(
        "/create-draft",
        data=json.dumps({"folder": folder}),
        content_type="application/json",
    )


# ── TestBrandConfidenceGate ───────────────────────────────────────────────────

class TestBrandConfidenceGate:

    def test_blocks_low_brand_confidence(self, client, monkeypatch):
        listing = _make_listing(brand_confidence="low", category=_VALID_CATEGORY)
        _setup_item(client._tmp_path, "item1", listing)

        resp = _post_create_draft(client, "item1")
        assert resp.status_code == 409
        data = resp.get_json()
        assert data["code"] == "LOW_BRAND_CONFIDENCE"

    def test_allows_low_confidence_when_brand_confirmed(self, client, monkeypatch):
        listing = _make_listing(
            brand_confidence="low",
            brand_confirmed=True,
            category=_VALID_CATEGORY,
        )
        _setup_item(client._tmp_path, "item2", listing)

        with patch("app.draft_creator.create_draft", return_value="https://vinted.co.uk/items/99"):
            with patch("app.services.listing_tracker.record_draft_snapshot"):
                with patch("app.services.item_store.set_status"):
                    resp = _post_create_draft(client, "item2")
        assert resp.status_code == 200

    def test_allows_medium_brand_confidence(self, client, monkeypatch):
        listing = _make_listing(brand_confidence="medium", category=_VALID_CATEGORY)
        _setup_item(client._tmp_path, "item3", listing)

        with patch("app.draft_creator.create_draft", return_value="https://vinted.co.uk/items/99"):
            with patch("app.services.listing_tracker.record_draft_snapshot"):
                with patch("app.services.item_store.set_status"):
                    resp = _post_create_draft(client, "item3")
        assert resp.status_code == 200

    def test_allows_high_brand_confidence(self, client, monkeypatch):
        listing = _make_listing(brand_confidence="high", category=_VALID_CATEGORY)
        _setup_item(client._tmp_path, "item4", listing)

        with patch("app.draft_creator.create_draft", return_value="https://vinted.co.uk/items/99"):
            with patch("app.services.listing_tracker.record_draft_snapshot"):
                with patch("app.services.item_store.set_status"):
                    resp = _post_create_draft(client, "item4")
        assert resp.status_code == 200

    def test_error_body_includes_brand_name(self, client, monkeypatch):
        listing = _make_listing(brand="Hacket", brand_confidence="low", category=_VALID_CATEGORY)
        _setup_item(client._tmp_path, "item5", listing)

        resp = _post_create_draft(client, "item5")
        data = resp.get_json()
        assert "Hacket" in data["error"]


# ── TestCategoryResolutionGate ────────────────────────────────────────────────

class TestCategoryResolutionGate:

    def test_blocks_unresolvable_category(self, client, monkeypatch):
        listing = _make_listing(category=_INVALID_CATEGORY)
        _setup_item(client._tmp_path, "item6", listing)

        resp = _post_create_draft(client, "item6")
        assert resp.status_code == 409
        data = resp.get_json()
        assert data["code"] == "CATEGORY_UNRESOLVED"

    def test_error_body_includes_category(self, client, monkeypatch):
        listing = _make_listing(category=_INVALID_CATEGORY)
        _setup_item(client._tmp_path, "item7", listing)

        resp = _post_create_draft(client, "item7")
        data = resp.get_json()
        assert data["category"] == _INVALID_CATEGORY

    def test_allows_valid_category(self, client, monkeypatch):
        listing = _make_listing(category=_VALID_CATEGORY)
        _setup_item(client._tmp_path, "item8", listing)

        with patch("app.draft_creator.create_draft", return_value="https://vinted.co.uk/items/99"):
            with patch("app.services.listing_tracker.record_draft_snapshot"):
                with patch("app.services.item_store.set_status"):
                    resp = _post_create_draft(client, "item8")
        assert resp.status_code == 200

    def test_allows_invalid_category_when_locked(self, client, monkeypatch):
        listing = _make_listing(category=_INVALID_CATEGORY, category_locked=True)
        _setup_item(client._tmp_path, "item9", listing)

        with patch("app.draft_creator.create_draft", return_value="https://vinted.co.uk/items/99"):
            with patch("app.services.listing_tracker.record_draft_snapshot"):
                with patch("app.services.item_store.set_status"):
                    resp = _post_create_draft(client, "item9")
        assert resp.status_code == 200

    def test_brand_gate_checked_before_category_gate(self, client, monkeypatch):
        """When both gates would trigger, brand gate fires first."""
        listing = _make_listing(brand_confidence="low", category=_INVALID_CATEGORY)
        _setup_item(client._tmp_path, "item10", listing)

        resp = _post_create_draft(client, "item10")
        data = resp.get_json()
        assert data["code"] == "LOW_BRAND_CONFIDENCE"
