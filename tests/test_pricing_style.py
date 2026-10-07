"""The onboarding pricing style always moves the price and the dial."""
import pytest

from app.services import pricing


@pytest.fixture(autouse=True)
def no_memory_or_history(monkeypatch):
    monkeypatch.setattr(pricing, "lookup_memory", lambda **kwargs: None)
    from app.services import sales_history
    monkeypatch.setattr(sales_history, "comparisons", lambda listing: {})


def priced(mode, **extra):
    listing = dict(brand="Peter Millar", item_type="polo shirt", price_gbp=30,
                   condition_summary="Very good used condition", ai_price_condition="Very good", **extra)
    return pricing.apply_pricing(listing, pricing_mode=mode)


def test_style_moves_an_ai_price():
    # AI-only estimate: the recommended band is ±15% around the fair £30.
    assert priced("speed")["price_gbp"] == 26
    assert priced("balanced")["price_gbp"] == 30
    assert priced("price")["price_gbp"] == 34
    assert any("pricing style: Best price top of the range (£30 → £34)" in a for a in priced("price")["price_adjustments"])


def test_dial_needle_follows_style():
    left, middle, right = (priced(m)["price_range"]["position"] for m in ("speed", "balanced", "price"))
    assert left < middle < right
    assert abs(middle - 0.5) < 0.05


def test_needle_sits_on_the_band_edge_for_the_style():
    # Best price asks at the top of the recommended band, Sell fast at the bottom.
    best, fast = priced("price"), priced("speed")
    assert best["price_gbp"] == best["price_range"]["high"]
    assert fast["price_gbp"] == fast["price_range"]["low"]


def test_style_moves_a_web_price():
    web = {"typical_gbp": 32, "low_gbp": 26, "high_gbp": 40, "confidence": "medium", "sold_count": 3,
           "condition_level": "Very good"}
    assert priced("speed", web_price=web)["price_gbp"] == 29
    assert priced("price", web_price=web)["price_gbp"] == 35


def test_reference_band_is_not_styled_twice(monkeypatch):
    monkeypatch.setattr(pricing, "lookup_memory", lambda **kwargs: {
        "brand": "Peter Millar", "item_type": "polo shirt", "low": 20, "high": 40, "confidence": "low"})
    fast, best = priced("speed"), priced("price")
    assert fast["price_gbp"] < best["price_gbp"]
    for listing in (fast, best):
        assert sum("pricing style" in a for a in listing["price_adjustments"]) == 1
    assert fast["price_range"]["position"] < best["price_range"]["position"]


def test_unknown_style_is_balanced():
    assert priced("loads")["price_gbp"] == 30 and priced("loads")["pricing_mode"] == "balanced"
