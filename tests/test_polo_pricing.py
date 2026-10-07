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


@pytest.mark.parametrize("item_type, expected", [
    ("striped short-sleeve shirt", "polo shirt"),
    ("performance short-sleeve shirt", "polo shirt"),
    ("golf top", "polo shirt"),
    ("long-sleeve button-down shirt", "long-sleeve button-down shirt"),
    ("polo shirt", "polo shirt"),
])
def test_golf_brand_short_sleeve_shirts_become_polos(item_type, expected):
    from app.extractor import _normalise_polo
    result = {"brand": "Peter Millar", "item_type": item_type}
    _normalise_polo(result)
    assert result["item_type"] == expected


def test_other_brands_shirts_untouched():
    from app.extractor import _normalise_polo
    result = {"brand": "Fred Perry", "item_type": "checked shirt"}
    _normalise_polo(result)
    assert result["item_type"] == "checked shirt"


@pytest.mark.parametrize("size, text", [("S", "S / Small"), ("m", "m / Medium"), ("XL", "XL / Extra Large"),
                                        ("W32 L32", "W32 L32"), ("44R", "44R")])
def test_letter_sizes_spelled_out(size, text):
    from app.services.description_layout import size_text
    assert size_text({"normalized_size": size, "tagged_size": size}) == text


def test_mens_polo_always_filed_under_polo_shirts():
    from app.listing_writer import finalize_listing
    item = dict(brand="Peter Millar", item_type="polo shirt", gender="men's", normalized_size="S", tagged_size="S",
                materials=["92% Polyester"], colour="Blue", condition_summary="New with tags")
    result = finalize_listing(dict(item, title="Peter Millar Polo Shirt Mens Blue S", description="Polo.",
                                   category="Men > Shirts > Plain", price_gbp=30), item)
    assert result["category"] == "Men > Polo Shirts"
    assert "- Size: S / Small" in result["description"]
