"""
Tests for item-type category rule slicing in listing_writer.

Run with:  .venv/bin/python -m pytest tests/test_category_item_slice.py -v
"""
import pytest


# ---------------------------------------------------------------------------
# 1. _resolve_item_type_group — pure mapping logic
# ---------------------------------------------------------------------------

class TestResolveItemTypeGroup:
    def test_blazer_resolves_to_tailoring(self):
        from app.listing_writer import _resolve_item_type_group
        assert _resolve_item_type_group("blazer") == "tailoring"

    def test_suit_resolves_to_tailoring(self):
        from app.listing_writer import _resolve_item_type_group
        assert _resolve_item_type_group("suit") == "tailoring"

    def test_suit_jacket_resolves_to_tailoring(self):
        from app.listing_writer import _resolve_item_type_group
        assert _resolve_item_type_group("suit jacket") == "tailoring"

    def test_wax_jacket_resolves_to_outerwear(self):
        from app.listing_writer import _resolve_item_type_group
        assert _resolve_item_type_group("wax jacket") == "outerwear"

    def test_generic_jacket_resolves_to_outerwear(self):
        from app.listing_writer import _resolve_item_type_group
        assert _resolve_item_type_group("jacket") == "outerwear"

    def test_coat_resolves_to_outerwear(self):
        from app.listing_writer import _resolve_item_type_group
        assert _resolve_item_type_group("coat") == "outerwear"

    def test_parka_resolves_to_outerwear(self):
        from app.listing_writer import _resolve_item_type_group
        assert _resolve_item_type_group("parka") == "outerwear"

    def test_jumper_resolves_to_knitwear(self):
        from app.listing_writer import _resolve_item_type_group
        assert _resolve_item_type_group("jumper") == "knitwear"

    def test_lambswool_jumper_resolves_to_knitwear(self):
        from app.listing_writer import _resolve_item_type_group
        assert _resolve_item_type_group("lambswool jumper") == "knitwear"

    def test_hoodie_resolves_to_knitwear(self):
        from app.listing_writer import _resolve_item_type_group
        assert _resolve_item_type_group("hoodie") == "knitwear"

    def test_shirt_resolves_to_shirts_tops(self):
        from app.listing_writer import _resolve_item_type_group
        assert _resolve_item_type_group("shirt") == "shirts_tops"

    def test_polo_shirt_resolves_to_shirts_tops(self):
        from app.listing_writer import _resolve_item_type_group
        assert _resolve_item_type_group("polo shirt") == "shirts_tops"

    def test_jeans_resolves_to_jeans(self):
        from app.listing_writer import _resolve_item_type_group
        assert _resolve_item_type_group("jeans") == "jeans"

    def test_slim_fit_jeans_resolves_to_jeans(self):
        from app.listing_writer import _resolve_item_type_group
        assert _resolve_item_type_group("slim fit jeans") == "jeans"

    def test_trousers_resolves_to_trousers(self):
        from app.listing_writer import _resolve_item_type_group
        assert _resolve_item_type_group("trousers") == "trousers"

    def test_joggers_resolves_to_trousers(self):
        from app.listing_writer import _resolve_item_type_group
        assert _resolve_item_type_group("joggers") == "trousers"

    def test_dress_resolves_to_dresses(self):
        from app.listing_writer import _resolve_item_type_group
        assert _resolve_item_type_group("dress") == "dresses"

    def test_midi_dress_resolves_to_dresses(self):
        from app.listing_writer import _resolve_item_type_group
        assert _resolve_item_type_group("midi dress") == "dresses"

    def test_skirt_resolves_to_skirts(self):
        from app.listing_writer import _resolve_item_type_group
        assert _resolve_item_type_group("skirt") == "skirts"

    def test_unknown_returns_none(self):
        from app.listing_writer import _resolve_item_type_group
        assert _resolve_item_type_group("magic carpet") is None

    def test_empty_returns_none(self):
        from app.listing_writer import _resolve_item_type_group
        assert _resolve_item_type_group("") is None

    def test_compound_unknown_type_returns_none(self):
        from app.listing_writer import _resolve_item_type_group
        assert _resolve_item_type_group("something entirely unknown") is None

    def test_partial_match_wax_jacket_beats_generic_jacket(self):
        """Longest-key match: 'wax jacket' should not just resolve via bare 'jacket'."""
        from app.listing_writer import _resolve_item_type_group
        # Both 'jacket' and 'wax jacket' are in the mapping, both = outerwear.
        # The function should return outerwear regardless.
        result = _resolve_item_type_group("wax jacket")
        assert result == "outerwear"

    def test_case_insensitive(self):
        from app.listing_writer import _resolve_item_type_group
        assert _resolve_item_type_group("Blazer") == "tailoring"
        assert _resolve_item_type_group("JEANS") == "jeans"


# ---------------------------------------------------------------------------
# 2. _filter_category_by_group — line-level filtering
# ---------------------------------------------------------------------------

class TestFilterCategoryByGroup:
    def _get_mens_sliced(self) -> str:
        from app.listing_writer import _slice_category_rules
        return _slice_category_rules("men's")

    def test_tailoring_keeps_blazer_line(self):
        from app.listing_writer import _filter_category_by_group
        text = self._get_mens_sliced()
        result = _filter_category_by_group(text, "tailoring")
        assert "Blazer" in result

    def test_tailoring_excludes_jeans_lines(self):
        from app.listing_writer import _filter_category_by_group
        text = self._get_mens_sliced()
        result = _filter_category_by_group(text, "tailoring")
        # Jeans lines should be stripped (before Notes section)
        pre_notes = result.split("# Notes")[0]
        assert "Jeans" not in pre_notes, "tailoring slice must not contain Jeans lines"

    def test_jeans_keeps_jeans_lines(self):
        from app.listing_writer import _filter_category_by_group
        text = self._get_mens_sliced()
        result = _filter_category_by_group(text, "jeans")
        assert "Jeans" in result

    def test_jeans_excludes_blazer_lines(self):
        from app.listing_writer import _filter_category_by_group
        text = self._get_mens_sliced()
        result = _filter_category_by_group(text, "jeans")
        pre_notes = result.split("# Notes")[0]
        assert "Blazer" not in pre_notes

    def test_notes_always_preserved(self):
        from app.listing_writer import _filter_category_by_group
        text = self._get_mens_sliced()
        for group in ("tailoring", "outerwear", "jeans", "knitwear", "shirts_tops"):
            result = _filter_category_by_group(text, group)
            assert "# Notes" in result, f"Notes section missing from '{group}' slice"

    def test_outerwear_keeps_coats_and_jackets(self):
        from app.listing_writer import _filter_category_by_group
        text = self._get_mens_sliced()
        result = _filter_category_by_group(text, "outerwear")
        pre_notes = result.split("# Notes")[0]
        assert "Overcoat" in pre_notes or "Wax jacket" in pre_notes
        assert "Bomber jacket" in pre_notes or "Puffer jacket" in pre_notes

    def test_outerwear_excludes_jeans_and_shirts(self):
        from app.listing_writer import _filter_category_by_group
        text = self._get_mens_sliced()
        result = _filter_category_by_group(text, "outerwear")
        pre_notes = result.split("# Notes")[0]
        assert "Jeans" not in pre_notes
        assert "Polo shirt" not in pre_notes


# ---------------------------------------------------------------------------
# 3. _slice_category_rules with item_type
# ---------------------------------------------------------------------------

class TestSliceCategoryRulesByItemType:
    def test_mens_blazer_slice_smaller_than_gender_only(self):
        from app.listing_writer import _slice_category_rules
        gender_only = _slice_category_rules("men's")
        with_type   = _slice_category_rules("men's", "blazer")
        assert len(with_type) < len(gender_only), \
            "Item-type slice must be smaller than gender-only slice"

    def test_mens_blazer_has_blazer_rule(self):
        from app.listing_writer import _slice_category_rules
        result = _slice_category_rules("men's", "blazer")
        assert "Blazer" in result

    def test_mens_blazer_excludes_jeans(self):
        from app.listing_writer import _slice_category_rules
        result = _slice_category_rules("men's", "blazer")
        pre_notes = result.split("# Notes")[0]
        assert "Jeans" not in pre_notes

    def test_womens_dress_has_dress_rules(self):
        from app.listing_writer import _slice_category_rules
        result = _slice_category_rules("women's", "midi dress")
        assert "Midi dress" in result or "Dress" in result

    def test_womens_dress_excludes_jeans(self):
        from app.listing_writer import _slice_category_rules
        result = _slice_category_rules("women's", "midi dress")
        pre_notes = result.split("# Notes")[0]
        assert "Jeans" not in pre_notes

    def test_notes_always_present(self):
        from app.listing_writer import _slice_category_rules
        for gender, item_type in [("men's", "blazer"), ("women's", "jeans"), ("men's", "jacket")]:
            result = _slice_category_rules(gender, item_type)
            assert "# Notes" in result, f"Notes missing for {gender}/{item_type}"

    def test_unknown_item_type_falls_back_to_gender_slice(self):
        """Unknown item types must not error — return gender-only slice."""
        from app.listing_writer import _slice_category_rules
        gender_only = _slice_category_rules("men's")
        with_unknown = _slice_category_rules("men's", "magic carpet 500")
        assert with_unknown == gender_only, \
            "Unknown item type should fall back to gender-only slice"

    def test_empty_item_type_returns_gender_slice(self):
        from app.listing_writer import _slice_category_rules
        gender_only = _slice_category_rules("men's")
        with_empty  = _slice_category_rules("men's", "")
        assert with_empty == gender_only

    def test_mens_jeans_slice_has_jeans_rules(self):
        from app.listing_writer import _slice_category_rules
        result = _slice_category_rules("men's", "jeans")
        assert "Jeans" in result

    def test_item_type_slice_token_saving(self):
        """Item-type slice must save tokens vs gender-only slice."""
        from app.listing_writer import _slice_category_rules
        gender_only = _slice_category_rules("men's")
        blazer_slice = _slice_category_rules("men's", "blazer")
        saved = (len(gender_only) - len(blazer_slice)) // 4
        assert saved > 50, f"Expected >50 token saving for blazer slice, got {saved}"

    def test_flag_disabled_returns_gender_slice(self, monkeypatch):
        """When ENABLE_CATEGORY_ITEM_TYPE_SLICE is False, item_type is ignored."""
        import app.listing_writer
        monkeypatch.setattr(app.listing_writer, "ENABLE_CATEGORY_ITEM_TYPE_SLICE", False)
        gender_only = app.listing_writer._slice_category_rules("men's")
        with_type   = app.listing_writer._slice_category_rules("men's", "blazer")
        assert with_type == gender_only, \
            "Flag disabled: item-type slice must return same as gender-only"


# ---------------------------------------------------------------------------
# 4. _build_prompt uses item-type slice
# ---------------------------------------------------------------------------

class TestBuildPromptUsesItemTypeSlice:
    def _base_item(self, **overrides) -> dict:
        base = {
            "brand": "Barbour", "brand_confidence": "high",
            "item_type": "wax jacket", "gender": "men's",
            "tagged_size": "M", "normalized_size": "M",
            "materials": ["100% Cotton"], "colour": "Olive",
            "confidence": 0.9, "low_confidence_fields": [],
            "condition_summary": "Very good used condition — minimal wear.",
        }
        base.update(overrides)
        return base

    def test_blazer_prompt_excludes_jeans_category_rules(self):
        from app.listing_writer import _build_prompt
        item = self._base_item(item_type="blazer")
        prompt = _build_prompt(item)
        cat_start = prompt.index("# Category Rules")
        cat_end = prompt.index("# Pricing Rules")
        cat_block = prompt[cat_start:cat_end]
        assert "Jeans" not in cat_block, "blazer prompt's category rules should not contain Jeans"
        assert "Blazer" in cat_block, "blazer prompt's category rules must contain Blazer"

    def test_jeans_prompt_excludes_blazer_category_rules(self):
        from app.listing_writer import _build_prompt
        item = self._base_item(item_type="jeans", tagged_size="W32 L32", normalized_size="W32 L32")
        prompt = _build_prompt(item)
        cat_start = prompt.index("# Category Rules")
        cat_end = prompt.index("# Pricing Rules")
        cat_block = prompt[cat_start:cat_end]
        assert "Blazer" not in cat_block, "jeans prompt's category rules should not contain Blazer"
        assert "Jeans" in cat_block, "jeans prompt's category rules must contain Jeans"

    def test_unknown_item_type_prompt_has_full_gender_rules(self):
        """Unknown item type falls back to full gender-slice (no crash)."""
        from app.listing_writer import _build_prompt
        item = self._base_item(item_type="magic carpet")
        prompt = _build_prompt(item)
        cat_start = prompt.index("# Category Rules")
        cat_end = prompt.index("# Pricing Rules")
        cat_block = prompt[cat_start:cat_end]
        # With full men's slice, should have both blazers and jeans
        assert "Blazer" in cat_block or "Jeans" in cat_block, \
            "fallback to gender slice should include standard men's items"
