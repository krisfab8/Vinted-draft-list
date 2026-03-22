"""
Unit tests for app/services/pricing.py

Pure-function tests only — no I/O, no Flask, no AI calls.
price_memory.json is loaded from disk; tests that need controlled data
inject a custom memory list via monkeypatching.
"""
import pytest
from unittest.mock import patch


# ── Helpers ────────────────────────────────────────────────────────────────

def _make_memory(*entries):
    """Return a patched _load_memory that returns the given entries."""
    return patch("app.services.pricing._load_memory", return_value=list(entries))


def _entry(brand=None, item_type="blazer", material_group="wool",
           low=20, high=80, confidence="high"):
    return {
        "brand": brand,
        "item_type": item_type,
        "material_group": material_group,
        "low": low,
        "high": high,
        "confidence": confidence,
    }


# ── lookup_memory ─────────────────────────────────────────────────────────

class TestLookupMemory:

    def test_returns_none_when_no_entries(self):
        from app.services.pricing import lookup_memory
        with _make_memory():
            result = lookup_memory("barbour", "wax jacket")
        assert result is None

    def test_brand_item_type_material_match(self):
        from app.services.pricing import lookup_memory
        e = _entry(brand="barbour", item_type="wax jacket", material_group=None)
        with _make_memory(e):
            result = lookup_memory("Barbour", "wax jacket")
        assert result is e

    def test_falls_back_to_generic_item_type(self):
        from app.services.pricing import lookup_memory
        generic = _entry(brand=None, item_type="blazer", material_group="wool")
        with _make_memory(generic):
            result = lookup_memory("unknown brand", "blazer", materials=["wool"])
        assert result is generic

    def test_prefers_brand_match_over_generic(self):
        from app.services.pricing import lookup_memory
        generic = _entry(brand=None, item_type="blazer", material_group="wool", low=20, high=80)
        branded = _entry(brand="suitsupply", item_type="blazer", material_group="wool", low=55, high=130)
        with _make_memory(generic, branded):
            result = lookup_memory("suitsupply", "blazer", materials=["100% wool"])
        assert result is branded

    def test_returns_none_for_unknown_item_type(self):
        from app.services.pricing import lookup_memory
        e = _entry(brand=None, item_type="blazer", material_group="wool")
        with _make_memory(e):
            result = lookup_memory(None, "socks")
        assert result is None

    def test_case_insensitive_brand_match(self):
        from app.services.pricing import lookup_memory
        e = _entry(brand="Barbour", item_type="wax jacket", material_group=None)
        with _make_memory(e):
            result = lookup_memory("BARBOUR", "Wax Jacket")
        assert result is e


# ── _condition_percentile ─────────────────────────────────────────────────

class TestConditionPercentile:

    def _pct(self, summary):
        from app.services.pricing import _condition_percentile
        return _condition_percentile(summary)

    def test_very_good(self):
        assert self._pct("Very good condition") == 0.75

    def test_pristine(self):
        assert self._pct("Pristine — mint condition") == 0.92

    def test_good(self):
        assert self._pct("Good condition") == 0.50

    def test_fair(self):
        assert self._pct("Fair condition") == 0.20

    def test_none_returns_midpoint(self):
        assert self._pct(None) == 0.50

    def test_empty_returns_midpoint(self):
        assert self._pct("") == 0.50

    def test_new_with_tags(self):
        assert self._pct("New with tags") == 0.92


# ── apply_pricing ─────────────────────────────────────────────────────────

class TestApplyPricing:

    def test_preserves_ai_price_when_no_memory(self):
        from app.services.pricing import apply_pricing
        listing = {"price_gbp": 65.0}
        with _make_memory():
            apply_pricing(listing)
        assert listing["ai_price_gbp"] == 65.0
        assert listing["price_gbp"] == 65.0

    def test_memory_band_overrides_ai_price(self):
        """Memory entry found → price calculated from band, not AI."""
        from app.services.pricing import apply_pricing
        e = _entry(brand="suitsupply", item_type="blazer", material_group="wool",
                   low=55, high=130)
        listing = {
            "price_gbp": 40.0,       # AI said £40 — too low
            "brand": "suitsupply",
            "item_type": "blazer",
            "materials": ["100% wool"],
            "condition_summary": "Very good condition",
        }
        with _make_memory(e):
            apply_pricing(listing)
        assert listing["ai_price_gbp"] == 40.0
        # 55 + 0.75 * (130-55) = 55 + 56.25 = 111 → rounded
        assert listing["price_gbp"] == 111

    def test_flaws_discount_applied(self):
        from app.services.pricing import apply_pricing
        e = _entry(brand=None, item_type="blazer", material_group="wool",
                   low=20, high=80, confidence="medium")
        listing = {
            "price_gbp": 50.0,
            "item_type": "blazer",
            "materials": ["wool"],
            "condition_summary": "Very good condition",
            "flaws_note": "Small stain on lapel",
        }
        with _make_memory(e):
            apply_pricing(listing)
        # band: 20 + 0.75 * 60 = 65, then * 0.85 = 55.25 → 55
        assert listing["price_gbp"] == 55
        assert any("flaws" in a for a in listing["price_adjustments"])

    def test_buy_price_does_not_force_price_up(self):
        """buy_price_gbp is analytics only — should not push price_gbp upward."""
        from app.services.pricing import apply_pricing
        e = _entry(brand=None, item_type="blazer", material_group="wool",
                   low=20, high=80, confidence="high")
        listing = {
            "price_gbp": 50.0,
            "item_type": "blazer",
            "materials": ["wool"],
            "condition_summary": "Fair condition",   # band → 20 + 0.2*60 = 32
            "buy_price_gbp": 20.0,
        }
        with _make_memory(e):
            apply_pricing(listing)
        # Market drives price to 32 — no floor override
        assert listing["price_gbp"] == 32
        assert not any("floor" in a for a in listing["price_adjustments"])

    def test_ceiling_clamp_high_confidence(self):
        from app.services.pricing import apply_pricing
        e = _entry(brand=None, item_type="blazer", material_group="wool",
                   low=20, high=80, confidence="high")
        listing = {
            "price_gbp": 50.0,
            "item_type": "blazer",
            "materials": ["wool"],
            "condition_summary": "Very good condition",  # 20 + 0.75*60 = 65, within ceiling
        }
        with _make_memory(e):
            apply_pricing(listing)
        assert listing["price_gbp"] == 65

    def test_ceiling_clamp_triggered_above_high(self):
        from app.services.pricing import apply_pricing
        e = _entry(brand=None, item_type="blazer", material_group="wool",
                   low=20, high=80, confidence="high")
        listing = {
            "price_gbp": 120.0,   # AI overshot
            "item_type": "blazer",
            "materials": ["wool"],
            "condition_summary": "Pristine",           # 0.92 → 20 + 0.92*60 = 75.2 → 75, under ceiling
        }
        with _make_memory(e):
            apply_pricing(listing)
        # 75 is under ceiling — no clamp, but AI was 120 and memory wins at 75
        assert listing["price_gbp"] == 75

    def test_memory_band_used_regardless_of_confidence(self):
        """Memory band positions the price even for low-confidence entries."""
        from app.services.pricing import apply_pricing
        e = _entry(brand=None, item_type="blazer", material_group="wool",
                   low=20, high=80, confidence="low")
        listing = {
            "price_gbp": 120.0,
            "item_type": "blazer",
            "materials": ["wool"],
        }
        with _make_memory(e):
            apply_pricing(listing)
        # Memory band used: 20 + 0.5*60 = 50 (midpoint, no condition_summary)
        assert listing["price_gbp"] == 50

    def test_price_adjustments_is_list(self):
        from app.services.pricing import apply_pricing
        listing = {"price_gbp": 50.0}
        with _make_memory():
            apply_pricing(listing)
        assert isinstance(listing["price_adjustments"], list)

    def test_no_crash_on_missing_price_gbp(self):
        from app.services.pricing import apply_pricing
        listing = {"brand": "something"}
        with _make_memory():
            apply_pricing(listing)
        assert "price_adjustments" in listing

    def test_final_price_is_integer(self):
        from app.services.pricing import apply_pricing
        e = _entry(brand=None, item_type="blazer", material_group="wool",
                   low=20, high=80, confidence="high")
        listing = {
            "price_gbp": 50.0,
            "item_type": "blazer",
            "materials": ["wool"],
            "condition_summary": "Very good condition",
        }
        with _make_memory(e):
            apply_pricing(listing)
        # Should be an int after rounding
        assert listing["price_gbp"] == int(listing["price_gbp"])

    def test_no_crash_on_corrupt_entry(self):
        """Corrupt memory entry should not crash apply_pricing."""
        from app.services.pricing import apply_pricing
        e = {"item_type": "blazer", "low": "bad", "high": None}
        listing = {"price_gbp": 50.0, "item_type": "blazer"}
        with _make_memory(e):
            # Should not raise
            apply_pricing(listing)
        assert "price_adjustments" in listing

    # ── Profitability metrics ─────────────────────────────────────────────

    def test_profit_metrics_calculated_when_buy_price_exists(self):
        from app.services.pricing import apply_pricing
        listing = {"price_gbp": 50.0, "buy_price_gbp": 10.0}
        with _make_memory():
            apply_pricing(listing)
        # net = 50 * 0.95 - 0.70 - 10 = 47.5 - 0.70 - 10 = 36.8
        assert listing["estimated_profit_gbp"] == pytest.approx(36.8)
        assert listing["profit_multiple"] == pytest.approx(5.0)
        assert isinstance(listing["pricing_flags"], list)
        assert isinstance(listing["profit_warning"], bool)

    def test_no_profit_metrics_without_buy_price(self):
        from app.services.pricing import apply_pricing
        listing = {"price_gbp": 50.0}
        with _make_memory():
            apply_pricing(listing)
        assert "estimated_profit_gbp" not in listing
        assert "profit_multiple" not in listing
        assert "profit_warning" not in listing

    def test_profit_warning_set_for_low_margin(self):
        """price_gbp < 1.5× buy_price → low_margin flag."""
        from app.services.pricing import apply_pricing
        listing = {"price_gbp": 20.0, "buy_price_gbp": 15.0}
        with _make_memory():
            apply_pricing(listing)
        assert listing["profit_warning"] is True
        assert "low_margin" in listing["pricing_flags"]

    def test_profit_warning_set_for_loss(self):
        """Net proceeds after fee < buy_price → loss flag."""
        from app.services.pricing import apply_pricing
        # net = 10 * 0.95 - 0.70 - 10 = 9.50 - 0.70 - 10 = -1.20
        listing = {"price_gbp": 10.0, "buy_price_gbp": 10.0}
        with _make_memory():
            apply_pricing(listing)
        assert listing["profit_warning"] is True
        assert "loss" in listing["pricing_flags"]

    def test_no_profit_warning_for_good_margin(self):
        from app.services.pricing import apply_pricing
        listing = {"price_gbp": 60.0, "buy_price_gbp": 15.0}  # 4× multiple
        with _make_memory():
            apply_pricing(listing)
        assert listing["profit_warning"] is False
        assert listing["pricing_flags"] == []

    def test_buy_price_does_not_appear_in_adjustments(self):
        """buy_price_gbp is analytics only — nothing about it in price_adjustments."""
        from app.services.pricing import apply_pricing
        listing = {"price_gbp": 30.0, "buy_price_gbp": 20.0}
        with _make_memory():
            apply_pricing(listing)
        assert not any("floor" in a or "buy" in a for a in listing["price_adjustments"])


# ── price_hint_text ───────────────────────────────────────────────────────

class TestPriceHintText:

    def test_returns_none_when_no_prices(self):
        from app.services.pricing import price_hint_text
        assert price_hint_text({}) is None

    def test_returns_none_when_prices_same(self):
        from app.services.pricing import price_hint_text
        listing = {"price_gbp": 65, "ai_price_gbp": 65, "price_adjustments": []}
        assert price_hint_text(listing) is None

    def test_returns_diff_when_prices_differ(self):
        from app.services.pricing import price_hint_text
        listing = {
            "price_gbp": 95,
            "ai_price_gbp": 65,
            "price_adjustments": ["memory: barbour wax jacket → £60–£140"],
        }
        hint = price_hint_text(listing)
        assert hint is not None
        assert "65" in hint
        assert "95" in hint

    def test_includes_adjustment_reason(self):
        from app.services.pricing import price_hint_text
        listing = {
            "price_gbp": 95,
            "ai_price_gbp": 65,
            "price_adjustments": ["memory match"],
        }
        hint = price_hint_text(listing)
        assert "memory match" in hint

    def test_returns_first_adjustment_when_same_price(self):
        from app.services.pricing import price_hint_text
        listing = {
            "price_gbp": 65,
            "ai_price_gbp": 65,
            "price_adjustments": ["no memory match — using AI price"],
        }
        hint = price_hint_text(listing)
        assert "no memory match" in hint
