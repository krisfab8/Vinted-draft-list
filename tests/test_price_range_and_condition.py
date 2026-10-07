"""Repricing follows condition changes; every price gets a small explainable range."""
import pytest

from app.services import pricing


@pytest.fixture(autouse=True)
def no_memory_or_history(monkeypatch):
    monkeypatch.setattr(pricing, "lookup_memory", lambda **kwargs: None)
    from app.services import sales_history
    monkeypatch.setattr(sales_history, "comparisons", lambda listing: {})


def priced(**fields):
    listing = dict(brand="Peter Millar", item_type="polo shirt", price_gbp=28, **fields)
    return pricing.apply_pricing(listing)


def test_new_with_tags_raises_an_ai_price_set_for_used_condition():
    listing = priced(condition_summary="New with tags — original labels attached.",
                     ai_price_condition="Excellent")
    assert listing["price_gbp"] == 35  # 28 x 1.30 / 1.05
    assert any("New with tags vs Excellent" in a for a in listing["price_adjustments"])


def test_worse_condition_lowers_price_and_same_condition_keeps_it():
    assert priced(condition_summary="Good used condition", ai_price_condition="Very good")["price_gbp"] == 24
    same = priced(condition_summary="Very good used condition", ai_price_condition="Very good")
    assert same["price_gbp"] == 28
    assert not any("condition" in a for a in same["price_adjustments"])


def test_older_drafts_only_adjust_when_now_new():
    assert priced(condition_summary="Good used condition")["price_gbp"] == 28
    assert priced(condition_summary="New with tags — original labels attached.")["price_gbp"] == 35


def test_reference_band_already_handles_condition(monkeypatch):
    monkeypatch.setattr(pricing, "lookup_memory", lambda **kwargs: {
        "brand": "Peter Millar", "item_type": "polo shirt", "low": 20, "high": 40, "confidence": "medium"})
    listing = priced(condition_summary="New with tags", ai_price_condition="Excellent")
    assert listing["price_gbp"] == 38  # band position only, no extra condition multiplier
    assert not any("vs Excellent" in a for a in listing["price_adjustments"])
    r = listing["price_range"]
    assert r["basis"] == "reference" and r["low"] < 38 < r["high"]
    assert r["scale_low"] <= 20 and r["scale_high"] >= 40


def test_range_is_small_and_needle_inside_scale():
    r = priced(condition_summary="Very good used condition", ai_price_condition="Very good")["price_range"]
    assert r == {"low": 24, "high": 32, "scale_low": 15, "scale_high": 41,
                 "position": round((28 - 15) / (41 - 15), 3), "basis": "estimate"}


def test_no_price_means_no_range():
    assert pricing.price_range({"price_gbp": None}) is None


def test_accepting_a_suggestion_keeps_its_range_and_reasons():
    from app.services.listing_edits import apply as apply_updates
    existing = {"price_gbp": 28, "price_proposal": {
        "price_gbp": 35, "range": {"low": 32, "high": 38}, "adjustments": ["condition New with tags"]}}
    result = apply_updates(existing, {"price_gbp": 35})
    assert result["price_range"] == {"low": 32, "high": 38}
    assert result["price_adjustments"] == ["condition New with tags"]
    typed = apply_updates(existing, {"price_gbp": 30})
    assert typed["price_range"]["low"] < 30 < typed["price_range"]["high"]


def test_needle_moves_towards_max_return_when_new_with_tags():
    r = priced(condition_summary="New with tags", ai_price_condition="Excellent")["price_range"]
    assert r["position"] > 0.6  # £35 against a scale anchored on the £28 AI price
