"""
Unit tests for Ralph Lauren feature detection (app/services/rl_features.py)
and the resulting pricing adjustments in app/services/pricing.py.

Pure-function tests — no I/O, no AI, no Flask.
"""
import pytest
from unittest.mock import patch

from app.services.rl_features import detect_rl_features
from app.services.pricing import apply_pricing


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_memory(*entries):
    return patch("app.services.pricing._load_memory", return_value=list(entries))


def _rl_listing(brand="Polo Ralph Lauren", price=40, **kwargs):
    base = {
        "brand": brand,
        "item_type": "polo shirt",
        "price_gbp": price,
        "materials": ["cotton"],
        "condition_summary": "Very good condition",
        "tag_keywords": [],
        "title": "",
        "description": "",
    }
    base.update(kwargs)
    return base


# ── TestDetectRlFeatures ─────────────────────────────────────────────────────

class TestDetectRlFeatures:

    def test_returns_none_for_non_rl_brand(self):
        assert detect_rl_features({"brand": "Barbour"}) is None

    def test_returns_none_for_empty_brand(self):
        assert detect_rl_features({"brand": ""}) is None

    def test_returns_none_for_null_brand(self):
        assert detect_rl_features({"brand": None}) is None

    def test_detects_polo_rl(self):
        result = detect_rl_features({"brand": "Polo Ralph Lauren"})
        assert result is not None
        assert result["rl_line"] == "polo"

    def test_detects_polo_by_rl(self):
        result = detect_rl_features({"brand": "Polo by Ralph Lauren"})
        assert result is not None
        assert result["rl_line"] == "polo"

    def test_detects_lauren_line(self):
        result = detect_rl_features({"brand": "Lauren Ralph Lauren"})
        assert result is not None
        assert result["rl_line"] == "lauren"

    def test_detects_lauren_by_rl(self):
        result = detect_rl_features({"brand": "Lauren by Ralph Lauren"})
        assert result is not None
        assert result["rl_line"] == "lauren"

    def test_detects_purple_label(self):
        result = detect_rl_features({"brand": "Ralph Lauren Purple Label"})
        assert result is not None
        assert result["rl_line"] == "purple_label"

    def test_detects_plain_ralph_lauren(self):
        # Plain "Ralph Lauren" — line is unspecified, NOT "lauren"
        result = detect_rl_features({"brand": "Ralph Lauren"})
        assert result is not None
        assert result["rl_line"] is None

    def test_detects_rlx(self):
        result = detect_rl_features({"brand": "RLX Ralph Lauren"})
        assert result is not None
        assert result["rl_line"] == "rlx"

    def test_detects_big_pony_from_tag_keywords(self):
        listing = _rl_listing(tag_keywords=["Big Pony", "Cotton"])
        result = detect_rl_features(listing)
        assert result["rl_logo_size"] == "big"

    def test_detects_big_pony_case_insensitive(self):
        listing = _rl_listing(tag_keywords=["BIG PONY"])
        result = detect_rl_features(listing)
        assert result["rl_logo_size"] == "big"

    def test_detects_large_pony(self):
        listing = _rl_listing(tag_keywords=["large pony polo"])
        result = detect_rl_features(listing)
        assert result["rl_logo_size"] == "big"

    def test_detects_small_pony(self):
        listing = _rl_listing(tag_keywords=["Small Pony"])
        result = detect_rl_features(listing)
        assert result["rl_logo_size"] == "small"

    def test_no_logo_size_when_absent(self):
        listing = _rl_listing(tag_keywords=["Super 120s"])
        result = detect_rl_features(listing)
        assert result["rl_logo_size"] is None

    def test_detects_embroidery_from_keywords(self):
        listing = _rl_listing(tag_keywords=["Embroidered logo"])
        result = detect_rl_features(listing)
        assert result["rl_embroidery"] is True

    def test_detects_embroidery_from_description(self):
        listing = _rl_listing(description="Features embroidery on chest.")
        result = detect_rl_features(listing)
        assert result["rl_embroidery"] is True

    def test_no_embroidery_when_absent(self):
        listing = _rl_listing()
        result = detect_rl_features(listing)
        assert result["rl_embroidery"] is False

    def test_detects_terry_from_materials(self):
        listing = _rl_listing(materials=["cotton terry"])
        result = detect_rl_features(listing)
        assert result["rl_fabric_type"] == "terry"

    def test_detects_towelling_from_materials(self):
        listing = _rl_listing(materials=["towelling cotton"])
        result = detect_rl_features(listing)
        assert result["rl_fabric_type"] == "terry"

    def test_detects_terry_from_keywords(self):
        listing = _rl_listing(tag_keywords=["Terry cloth"])
        result = detect_rl_features(listing)
        assert result["rl_fabric_type"] == "terry"

    def test_detects_towelling_from_keywords(self):
        listing = _rl_listing(tag_keywords=["Towelling fabric"])
        result = detect_rl_features(listing)
        assert result["rl_fabric_type"] == "terry"

    def test_no_fabric_type_for_plain_cotton(self):
        listing = _rl_listing(materials=["cotton"])
        result = detect_rl_features(listing)
        assert result["rl_fabric_type"] is None


# ── TestRlPricingAdjustments ─────────────────────────────────────────────────

class TestRlPricingAdjustments:
    """Tests that pricing.py applies RL multipliers correctly."""

    def test_big_pony_increases_price_25pct(self):
        listing = _rl_listing(price=40, tag_keywords=["Big Pony"])
        with _make_memory():
            apply_pricing(listing)
        assert listing["price_gbp"] == round(40 * 1.25)

    def test_embroidery_increases_price_15pct(self):
        listing = _rl_listing(price=40, tag_keywords=["Embroidered logo"])
        with _make_memory():
            apply_pricing(listing)
        assert listing["price_gbp"] == round(40 * 1.15)

    def test_terry_increases_price_20pct(self):
        listing = _rl_listing(price=40, materials=["cotton terry"])
        with _make_memory():
            apply_pricing(listing)
        assert listing["price_gbp"] == round(40 * 1.20)

    def test_lauren_line_decreases_price_20pct(self):
        listing = _rl_listing(brand="Lauren Ralph Lauren", price=40)
        with _make_memory():
            apply_pricing(listing)
        assert listing["price_gbp"] == round(40 * 0.80)

    def test_big_pony_and_embroidery_stack(self):
        listing = _rl_listing(price=40, tag_keywords=["Big Pony", "Embroidered logo"])
        with _make_memory():
            apply_pricing(listing)
        expected = round(round(40 * 1.25) * 1.15)
        assert listing["price_gbp"] == expected

    def test_adjustments_logged_for_big_pony(self):
        listing = _rl_listing(price=40, tag_keywords=["Big Pony"])
        with _make_memory():
            apply_pricing(listing)
        assert any("big pony" in a.lower() for a in listing["price_adjustments"])

    def test_adjustments_logged_for_lauren_line(self):
        listing = _rl_listing(brand="Lauren Ralph Lauren", price=40)
        with _make_memory():
            apply_pricing(listing)
        assert any("lauren line" in a.lower() for a in listing["price_adjustments"])

    def test_no_rl_adjustment_for_non_rl_brand(self):
        listing = {
            "brand": "Barbour",
            "item_type": "wax jacket",
            "price_gbp": 50,
            "materials": ["cotton"],
            "condition_summary": "Very good condition",
            "tag_keywords": [],
        }
        with _make_memory():
            apply_pricing(listing)
        assert listing["price_gbp"] == 50
        assert not any("RL" in a or "Lauren" in a for a in listing.get("price_adjustments", []))

    def test_rl_features_stored_in_listing(self):
        listing = _rl_listing(price=40, tag_keywords=["Big Pony"])
        with _make_memory():
            apply_pricing(listing)
        assert "rl_features" in listing
        assert listing["rl_features"]["rl_logo_size"] == "big"

    def test_rl_features_not_stored_for_non_rl(self):
        listing = {
            "brand": "Barbour",
            "item_type": "jacket",
            "price_gbp": 50,
            "materials": [],
            "condition_summary": "Very good condition",
            "tag_keywords": [],
        }
        with _make_memory():
            apply_pricing(listing)
        assert "rl_features" not in listing

    def test_rl_adjustment_skipped_when_no_final_price(self):
        listing = _rl_listing(tag_keywords=["Big Pony"])
        listing["price_gbp"] = None
        with _make_memory():
            apply_pricing(listing)
        # Should not crash; rl_features still stored
        assert "rl_features" in listing
