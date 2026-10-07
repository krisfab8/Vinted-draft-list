"""Golf polos: new-with-tags band, used band and item-type wording fallback."""
import pytest

from app.services import pricing


@pytest.fixture(autouse=True)
def no_sales(monkeypatch):
    from app.services import sales_history
    monkeypatch.setattr(sales_history, "comparisons", lambda listing: {})


def priced(item_type, condition, brand="Peter Millar", price=18):
    return pricing.apply_pricing(dict(brand=brand, item_type=item_type, materials=["92% Polyester"],
                                      condition_summary=condition, price_gbp=price))


@pytest.mark.parametrize("item_type", ["polo shirt", "striped shirt", "performance short-sleeve shirt"])
def test_new_with_tags_peter_millar_polo_prices_in_30s(item_type):
    listing = priced(item_type, "New with tags — original labels attached.")
    assert listing["price_gbp"] == 35
    assert "new with tags band" in listing["price_adjustments"][0]
    assert listing["price_range"]["basis"] == "reference"


def test_used_polo_uses_the_used_band():
    assert priced("polo shirt", "Very good used condition")["price_gbp"] == 25
    assert priced("polo shirt", "Good used condition")["price_gbp"] == 22


def test_shirt_fallback_only_for_brands_with_a_polo_band():
    # Unknown brand with an unusual item type: no polo band borrowed.
    assert pricing.lookup_memory("Unknown Label", "striped shirt") is None
    assert pricing.lookup_memory("Unknown Label", "polo shirt")["brand"] is None
    assert pricing.lookup_memory("Galvin Green", "golf top")["item_type"] == "polo shirt"


def test_galvin_green_new_with_tags():
    assert priced("polo shirt", "New with tags", brand="Galvin Green")["price_gbp"] == 33
