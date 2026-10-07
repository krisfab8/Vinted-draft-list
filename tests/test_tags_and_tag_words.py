"""Retail tags force "New with tags"; words read off tags always reach the listing."""
import pytest

from app.services import condition, description_layout


@pytest.mark.parametrize("summary", [
    "Unworn with original hang tag attached.",
    "Excellent used condition — unworn with original hang tag",
    "Brand new, swing tags still on",
    "BNWT",
    "Unworn, tags attached",
    "Comes with original tags",
    "New with tags — original labels attached.",
])
def test_retail_tags_mean_new_with_tags(summary):
    listing = {"condition_summary": summary, "flaws_note": None}
    condition.apply_condition(listing)
    assert listing["condition_summary"] == "New with tags — original labels attached."
    assert listing["condition_line"] == "New with original tags attached."


@pytest.mark.parametrize("summary, level", [
    ("New without tags — unworn, no original tags.", "New without tags"),
    ("Excellent used condition — hang tag removed", "Excellent"),
    ("Very good used condition, no tags", "Very good"),
    ("Excellent used condition — brand label intact", "Excellent"),
    ("Good used condition — care tag faded", "Good"),
])
def test_missing_or_non_retail_tags_keep_level(summary, level):
    assert condition.canonical_level(summary) == level


def test_flaws_never_downgrade_new_with_tags():
    listing = {"condition_summary": "Unworn with hang tag", "flaws_note": "small mark on cuff"}
    condition.apply_condition(listing)
    assert condition.canonical_level(listing["condition_summary"]) == "New with tags"


def listing(**extra):
    return dict(description="Galvin Green polo shirt in blue.\n\nKeywords: Galvin Green polo golf.",
                normalized_size="S", tagged_size="S", **extra)


def test_tag_words_are_added_to_keywords_even_when_uncertain():
    # Tag words go in whatever the confidence; an unclear logo reading does not.
    item = listing(tag_keywords=["Color Wave"], tag_keywords_confidence="low",
                   garment_text=[{"text": "Ventil8", "location": "sleeve", "confidence": "medium"}])
    description_layout.apply(item)
    keywords = [line for line in item["description"].splitlines() if line.startswith("Keywords:")]
    assert keywords == ["Keywords: Galvin Green polo golf, Color Wave."]
    assert "Ventil8" not in item["description"]
    # Uncertain logo words are not presented as a confirmed detail bullet.
    assert "Logo / print" not in item["description"]


def test_words_already_in_description_are_not_repeated():
    item = listing(tag_keywords=["color wave"])
    item["description"] = "Color Wave polo.\n\nKeywords: polo."
    description_layout.apply(item)
    assert item["description"].lower().count("color wave") == 1


def test_keywords_line_created_when_missing():
    item = dict(description="Plain shirt.", tag_keywords=["Color Wave"])
    description_layout.apply(item)
    assert item["description"].endswith("Keywords: Color Wave.")


def test_full_finalize_keeps_tag_word_and_new_with_tags():
    from app.listing_writer import finalize_listing
    item = dict(brand="Galvin Green", item_type="polo shirt", gender="men's", colour="Blue",
                tagged_size="S", normalized_size="S", materials=["92% Polyester", "8% Spandex"],
                tag_keywords=["Color Wave"], tag_keywords_confidence="low",
                condition_summary="Unworn with original hang tag attached.")
    result = dict(item, title="Galvin Green Polo Shirt Mens Blue S", category="Men > Polo Shirts",
                  price_gbp=30, description="Galvin Green polo shirt.\n\nKeywords: Galvin Green polo.",
                  condition_summary="Excellent used condition — unworn with original hang tag")
    result = finalize_listing(result, item)
    assert result["condition_summary"].startswith("New with tags")
    assert "Color Wave" in result["description"]
    assert "New with original tags attached." in result["description"]


def test_tag_colour_or_model_name_reading_reaches_keywords():
    item = listing(colour_from_tag="Color Wave", model_name="E4")
    item["description"] = "Peter Millar E4 polo.\n\nKeywords: Peter Millar polo."
    description_layout.apply(item)
    assert item["description"].endswith("Keywords: Peter Millar polo, Color Wave.")


def test_clear_tag_names_go_in_title_after_brand():
    from app.services.premium_features import ensure_tag_terms
    result = {"brand": "Peter Millar", "title": "Peter Millar E4 Performance Polo Shirt Mens Multicoloured S"}
    item = {"tag_keywords": ["E4 Performance", "Summer Comfort", "Machine Washable"],
            "tag_keywords_confidence": "high"}
    ensure_tag_terms(result, item)
    assert result["title"] == "Peter Millar Summer Comfort E4 Performance Polo Shirt Mens Multicoloured S"


def test_uncertain_or_too_long_tag_names_stay_out_of_title():
    from app.services.premium_features import ensure_tag_terms
    title = "Peter Millar Polo Shirt Mens S"
    result = {"brand": "Peter Millar", "title": title}
    ensure_tag_terms(result, {"tag_keywords": ["Color Wave"], "tag_keywords_confidence": "low"})
    assert result["title"] == title
    ensure_tag_terms(result, {"tag_keywords": ["Summer Comfort"], "tag_keywords_confidence": "high"},
                     max_length=len(title) + 5)
    assert result["title"] == title
