"""
Tests for category-rules slicing in listing_writer.

Run with:  .venv/bin/python -m pytest tests/test_category_rules.py -v
"""
import pytest


class TestSliceCategoryRules:
    def test_mens_excludes_womens_section(self):
        from app.listing_writer import _slice_category_rules
        result = _slice_category_rules("men's")
        # Women's entries should not appear before the Notes section
        pre_notes = result.split("# Notes")[0]
        assert "Women > " not in pre_notes, "Men's slice should not contain Women's category paths"

    def test_womens_excludes_mens_section(self):
        from app.listing_writer import _slice_category_rules
        result = _slice_category_rules("women's")
        pre_notes = result.split("# Notes")[0]
        assert "Men > " not in pre_notes, "Women's slice should not contain Men's category paths"

    def test_mens_retains_mens_entries(self):
        from app.listing_writer import _slice_category_rules
        result = _slice_category_rules("men's")
        assert "Men > Suits > Blazers" in result
        assert "Men > Jeans" in result

    def test_womens_retains_womens_entries(self):
        from app.listing_writer import _slice_category_rules
        result = _slice_category_rules("women's")
        assert "Women > Suits > Blazers" in result
        assert "Women > Jeans" in result

    def test_notes_section_always_present_mens(self):
        from app.listing_writer import _slice_category_rules
        assert "# Notes" in _slice_category_rules("men's")

    def test_notes_section_always_present_womens(self):
        from app.listing_writer import _slice_category_rules
        assert "# Notes" in _slice_category_rules("women's")

    def test_unisex_returns_full_content(self):
        from app.listing_writer import _slice_category_rules
        result = _slice_category_rules("unisex")
        assert "Men > " in result
        assert "Women > " in result
        assert "# Notes" in result

    def test_empty_gender_returns_full_content(self):
        from app.listing_writer import _slice_category_rules
        result = _slice_category_rules("")
        assert "Men > " in result
        assert "Women > " in result

    def test_mens_is_smaller_than_full(self):
        from app.listing_writer import _slice_category_rules
        full = _slice_category_rules("")
        mens = _slice_category_rules("men's")
        assert len(mens) < len(full), "Men's slice should be shorter than full rules"

    def test_womens_is_smaller_than_full(self):
        from app.listing_writer import _slice_category_rules
        full = _slice_category_rules("")
        womens = _slice_category_rules("women's")
        assert len(womens) < len(full)

    def test_mens_token_saving(self):
        """Men's slice should save at least 400 tokens vs full rules."""
        from app.listing_writer import _slice_category_rules
        full = _slice_category_rules("")
        mens = _slice_category_rules("men's")
        saved_tokens = (len(full) - len(mens)) // 4
        assert saved_tokens >= 400, f"Expected ≥400 token saving, got {saved_tokens}"

    def test_womens_token_saving(self):
        from app.listing_writer import _slice_category_rules
        full = _slice_category_rules("")
        womens = _slice_category_rules("women's")
        saved_tokens = (len(full) - len(womens)) // 4
        assert saved_tokens >= 400, f"Expected ≥400 token saving, got {saved_tokens}"


class TestBuildPromptUsesSlice:
    """Verify that _build_prompt() calls _slice_category_rules, not the raw file."""

    def test_mens_prompt_excludes_womens_paths(self):
        from app.listing_writer import _build_prompt
        item = {
            "brand": "Barbour",
            "brand_confidence": "high",
            "item_type": "wax jacket",
            "gender": "men's",
            "tagged_size": "M",
            "normalized_size": "M",
            "materials": ["100% Cotton"],
            "colour": "Olive",
            "confidence": 0.9,
            "low_confidence_fields": [],
            "condition_summary": "Very good used condition — minimal wear.",
        }
        prompt = _build_prompt(item)
        # Women's specific paths should not appear
        assert "Women > Suits" not in prompt
        assert "Women > Jeans" not in prompt
        # Men's paths must be there
        assert "Men > Suits" in prompt or "Men > Coats" in prompt

    def test_womens_prompt_excludes_mens_paths(self):
        from app.listing_writer import _build_prompt
        item = {
            "brand": "Whistles",
            "brand_confidence": "high",
            "item_type": "midi dress",
            "gender": "women's",
            "tagged_size": "12",
            "normalized_size": "12",
            "materials": ["100% Polyester"],
            "colour": "Black",
            "confidence": 0.9,
            "low_confidence_fields": [],
            "condition_summary": "Very good used condition — minimal wear.",
        }
        prompt = _build_prompt(item)
        # The category rules section starts at "# Category Rules" — check only that block
        cat_start = prompt.index("# Category Rules")
        cat_end = prompt.index("# Pricing Rules")
        cat_block = prompt[cat_start:cat_end]
        assert "Men > Suits" not in cat_block, "Cat rules for women's should not contain Men > Suits"
        assert "Women > Dresses" in cat_block
