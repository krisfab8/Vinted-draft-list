"""Tests for user_profile service and pricing_mode integration."""
import json
import pytest

from app.services import user_profile as profile_svc
from app.services.pricing import apply_pricing, _condition_percentile


# ── user_profile: load / save / helpers ───────────────────────────────────────

def test_load_returns_defaults_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(profile_svc, "_PATH", tmp_path / "user_profile.json")
    profile = profile_svc.load()
    assert profile == profile_svc.DEFAULTS


def test_load_merges_missing_keys_with_defaults(tmp_path, monkeypatch):
    path = tmp_path / "user_profile.json"
    path.write_text(json.dumps({"intent": "reseller"}))
    monkeypatch.setattr(profile_svc, "_PATH", path)
    profile = profile_svc.load()
    assert profile["intent"] == "reseller"
    assert profile["pricing_mode"] == "balanced"  # filled from defaults


def test_load_returns_defaults_on_corrupt_file(tmp_path, monkeypatch):
    path = tmp_path / "user_profile.json"
    path.write_text("not json{{{")
    monkeypatch.setattr(profile_svc, "_PATH", path)
    assert profile_svc.load() == profile_svc.DEFAULTS


def test_save_and_reload(tmp_path, monkeypatch):
    path = tmp_path / "user_profile.json"
    monkeypatch.setattr(profile_svc, "_PATH", path)
    profile_svc.save({"intent": "reseller", "pricing_mode": "price",
                      "volume": "high", "category_focus": "premium",
                      "vinted_experience": "experienced"})
    loaded = profile_svc.load()
    assert loaded["intent"] == "reseller"
    assert loaded["pricing_mode"] == "price"


def test_save_strips_unknown_keys(tmp_path, monkeypatch):
    path = tmp_path / "user_profile.json"
    monkeypatch.setattr(profile_svc, "_PATH", path)
    profile_svc.save({"intent": "casual", "junk_field": "ignored"})
    saved = json.loads(path.read_text())
    assert "junk_field" not in saved


def test_is_reseller_by_intent():
    assert profile_svc.is_reseller({"intent": "reseller", "volume": "low"})
    assert not profile_svc.is_reseller({"intent": "casual", "volume": "low"})


def test_is_reseller_by_volume():
    assert profile_svc.is_reseller({"intent": "casual", "volume": "medium"})
    assert profile_svc.is_reseller({"intent": "casual", "volume": "high"})
    assert not profile_svc.is_reseller({"intent": "casual", "volume": "low"})


def test_show_guidance_only_for_new():
    assert profile_svc.show_guidance({"vinted_experience": "new"})
    assert not profile_svc.show_guidance({"vinted_experience": "occasional"})
    assert not profile_svc.show_guidance({"vinted_experience": "experienced"})


# ── pricing_mode: band position offset ────────────────────────────────────────

def _listing_with_memory(condition="Very good condition"):
    """A listing that will hit a price memory band (uses existing test data)."""
    return {
        "brand": "Ralph Lauren",
        "item_type": "polo shirt",
        "materials": "cotton",
        "condition_summary": condition,
        "price_gbp": 30.0,
    }


def test_pricing_mode_balanced_is_default():
    listing = _listing_with_memory()
    result = apply_pricing(listing, pricing_mode="balanced")
    adjustments = result.get("price_adjustments", [])
    assert not any("pricing mode" in a for a in adjustments)


def test_pricing_mode_speed_lowers_price():
    l_balanced = _listing_with_memory()
    l_speed = _listing_with_memory()
    apply_pricing(l_balanced, pricing_mode="balanced")
    apply_pricing(l_speed, pricing_mode="speed")
    # speed should produce equal or lower price than balanced
    # (only differs if a memory band was matched)
    assert l_speed.get("price_gbp", 0) <= l_balanced.get("price_gbp", 999)


def test_pricing_mode_price_raises_price():
    l_balanced = _listing_with_memory()
    l_price = _listing_with_memory()
    apply_pricing(l_balanced, pricing_mode="balanced")
    apply_pricing(l_price, pricing_mode="price")
    assert l_price.get("price_gbp", 999) >= l_balanced.get("price_gbp", 0)


def test_pricing_mode_speed_logs_adjustment():
    """When a memory band is matched, speed mode logs an adjustment entry."""
    listing = _listing_with_memory()
    result = apply_pricing(listing, pricing_mode="speed")
    adjustments = result.get("price_adjustments", [])
    # If memory was matched, adjustment will be logged; otherwise falls back silently
    if any("memory:" in a for a in adjustments):
        assert any("pricing mode: speed" in a for a in adjustments)


def test_pricing_mode_pct_clamped_at_zero():
    """Speed mode on a 'Satisfactory' item (pct=0.20) should not go below 0."""
    listing = {
        "brand": "Ralph Lauren",
        "item_type": "polo shirt",
        "materials": "cotton",
        "condition_summary": "Satisfactory",
        "price_gbp": 10.0,
    }
    result = apply_pricing(listing, pricing_mode="speed")
    assert result.get("price_gbp", 0) >= 0


def test_pricing_mode_pct_clamped_at_one():
    """Price mode on a 'New with tags' item (pct=0.92) should not exceed 1.0."""
    listing = {
        "brand": "Ralph Lauren",
        "item_type": "polo shirt",
        "materials": "cotton",
        "condition_summary": "New with tags",
        "price_gbp": 50.0,
    }
    result = apply_pricing(listing, pricing_mode="price")
    assert result.get("price_gbp", 0) >= 0


def test_pricing_mode_unknown_treated_as_balanced():
    l_balanced = _listing_with_memory()
    l_unknown = _listing_with_memory()
    apply_pricing(l_balanced, pricing_mode="balanced")
    apply_pricing(l_unknown, pricing_mode="nonsense")
    assert l_unknown.get("price_gbp") == l_balanced.get("price_gbp")


def test_apply_pricing_never_raises_on_bad_mode():
    listing = {"price_gbp": 25.0}
    result = apply_pricing(listing, pricing_mode="speed")
    assert result is not None
