"""
Tests for draft_creator robustness helpers.

Run with:  .venv/bin/python -m pytest tests/test_draft_robustness.py -v
"""
import pytest
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# 1. Category alias normalisation — _resolve_category_key
# ---------------------------------------------------------------------------

class TestResolveCategoryKey:
    """_resolve_category_key maps raw AI strings to CATEGORY_NAV keys."""

    def _resolve(self, raw, style=None):
        from app.draft_creator import _resolve_category_key
        return _resolve_category_key(raw, style)

    # --- Direct CATEGORY_NAV keys pass through unchanged ---

    def test_direct_key_returned_unchanged(self):
        assert self._resolve("Men > Jeans > Straight") == "Men > Jeans > Straight"

    def test_direct_key_with_clothing_segment_normalised(self):
        """AI sometimes inserts 'Clothing' — _normalise_category strips it."""
        assert self._resolve("Men > Clothing > Jeans > Straight") == "Men > Jeans > Straight"

    # --- Alias lookups ---

    def test_straight_fit_jeans_alias(self):
        assert self._resolve("Men > Jeans > Straight fit jeans") == "Men > Jeans > Straight"

    def test_slim_fit_jeans_alias(self):
        assert self._resolve("Men > Jeans > Slim fit jeans") == "Men > Jeans > Slim"

    def test_skinny_jeans_full_label_alias(self):
        assert self._resolve("Men > Jeans > Skinny jeans") == "Men > Jeans > Skinny"

    def test_ripped_jeans_alias(self):
        assert self._resolve("Men > Jeans > Ripped jeans") == "Men > Jeans > Ripped"

    def test_women_straight_fit_jeans_alias(self):
        assert self._resolve("Women > Jeans > Straight fit jeans") == "Women > Jeans > Straight"

    def test_women_boyfriend_jeans_alias(self):
        assert self._resolve("Women > Jeans > Boyfriend jeans") == "Women > Jeans > Boyfriend"

    def test_joggers_with_clothing_segment(self):
        """Combination: strip 'Clothing' + alias."""
        # After stripping Clothing: "Men > Trousers > Joggers" — already in CATEGORY_NAV
        assert self._resolve("Men > Clothing > Trousers > Joggers") == "Men > Trousers > Joggers"

    def test_suits_blazers_alias(self):
        assert self._resolve("Men > Suits & Blazers > Blazers") == "Men > Suits > Blazers"

    def test_outerwear_coats_alias(self):
        assert self._resolve("Men > Outerwear > Coats") == "Men > Coats"

    # --- Style-qualified lookup ---

    def test_style_qualified_slim(self):
        result = self._resolve("Men > Jeans", style="Slim")
        assert result == "Men > Jeans > Slim"

    def test_style_qualified_straight(self):
        result = self._resolve("Men > Jeans", style="Straight")
        assert result == "Men > Jeans > Straight"

    # --- Fuzzy fallback ---

    def test_fuzzy_straight_fit_jeans_not_in_aliases(self):
        """Variant not in CATEGORY_ALIASES should still fuzzy-match."""
        # "Men > Jeans > Straight-leg jeans" is in aliases, but test a variant that isn't
        result = self._resolve("Men > Jeans > Straight cut jeans")
        # "straight" is in "straight cut jeans" → should match "Men > Jeans > Straight"
        assert result == "Men > Jeans > Straight"

    def test_fuzzy_slim_fit_variant(self):
        result = self._resolve("Men > Jeans > Slim tapered jeans")
        assert result == "Men > Jeans > Slim"

    # --- T-shirt graphic vs plain routing ---

    def test_graphic_tee_alias_print(self):
        """AI emitting 'Print' sub-type maps to Graphic t-shirts."""
        assert self._resolve("Men > T-shirts > Print") == "Men > T-shirts > Graphic"

    def test_graphic_tee_alias_printed(self):
        assert self._resolve("Men > T-shirts > Printed") == "Men > T-shirts > Graphic"

    def test_graphic_tee_alias_band_tee(self):
        assert self._resolve("Men > T-shirts > Band tee") == "Men > T-shirts > Graphic"

    def test_graphic_tee_alias_slogan(self):
        assert self._resolve("Men > T-shirts > Slogan") == "Men > T-shirts > Graphic"

    def test_plain_tee_resolves_to_plain(self):
        """Solid-colour tee: base + style=Plain → Men > T-shirts > Plain."""
        assert self._resolve("Men > T-shirts", style="Plain") == "Men > T-shirts > Plain"

    def test_graphic_tee_style_qualified(self):
        """Base category + style=Graphic resolves to Graphic t-shirts."""
        assert self._resolve("Men > T-shirts", style="Graphic") == "Men > T-shirts > Graphic"

    def test_graphic_tee_direct_key(self):
        """Direct CATEGORY_NAV key passes through unchanged."""
        assert self._resolve("Men > T-shirts > Graphic") == "Men > T-shirts > Graphic"

    def test_graphic_tee_nav_path(self):
        """Men > T-shirts > Graphic maps to Vinted's 'Print' nav path."""
        from app.draft_creator import CATEGORY_NAV
        assert CATEGORY_NAV["Men > T-shirts > Graphic"][-1] == "Print"

    def test_plain_tee_nav_path(self):
        """Men > T-shirts > Plain maps to Vinted's 'Plain t-shirts' nav path."""
        from app.draft_creator import CATEGORY_NAV
        assert CATEGORY_NAV["Men > T-shirts > Plain"][-1] == "Plain t-shirts"

    # --- Unknown category returns None ---

    def test_unknown_category_returns_none(self):
        assert self._resolve("Men > Pyjamas > Bottoms") is None

    def test_empty_string_returns_none(self):
        assert self._resolve("") is None


# ---------------------------------------------------------------------------
# 2. Jeans size normalisation — _wl_candidates
# ---------------------------------------------------------------------------

class TestWlCandidates:
    def _candidates(self, size):
        from app.draft_creator import _wl_candidates
        return _wl_candidates(size)

    def test_w34_l32_standard(self):
        c = self._candidates("W34 L32")
        assert "W34 L32" in c

    def test_w34_l32_slash_format(self):
        c = self._candidates("W34 L32")
        assert "34/32" in c

    def test_w34_l32_spaced_slash(self):
        c = self._candidates("W34 L32")
        assert "34 / 32" in c

    def test_w34_l32_waist_only_fallback(self):
        c = self._candidates("W34 L32")
        assert "W34" in c

    def test_w34_l32_bare_number_fallback(self):
        c = self._candidates("W34 L32")
        assert "34" in c

    def test_handles_slash_input(self):
        """Input may already be slash format: 34/32."""
        c = self._candidates("34/32")
        assert "34/32" in c or "W34 L32" in c

    def test_handles_lowercase_w(self):
        c = self._candidates("w32 l30")
        assert "W32 L30" in c or "32/30" in c

    def test_non_wl_size_returns_empty(self):
        from app.draft_creator import _wl_candidates
        assert _wl_candidates("M") == []
        assert _wl_candidates("44R") == []

    def test_no_duplicates(self):
        c = self._candidates("W34 L32")
        assert len(c) == len(set(c)), "candidates contain duplicates"


# ---------------------------------------------------------------------------
# 3. Option matching logic — _match_option
# ---------------------------------------------------------------------------

class TestMatchOption:
    def _match(self, target, options):
        from app.draft_creator import _match_option
        return _match_option(target, options)

    def test_exact_match(self):
        result = self._match("Very good", ["Good", "Very good", "New with tags"])
        assert result == ("Very good", "exact")

    def test_normalised_case_insensitive(self):
        result = self._match("very good", ["Good", "Very good", "New with tags"])
        assert result is not None
        assert result[0] == "Very good"
        assert result[1] == "normalized"

    def test_normalised_extra_whitespace(self):
        result = self._match("W34  L32", ["W34 L32", "W32 L30"])
        assert result is not None
        assert result[0] == "W34 L32"

    def test_contains_match_substring(self):
        # "Straight" is contained in "Straight fit jeans"
        result = self._match("Straight", ["Straight fit jeans", "Slim fit jeans"])
        assert result is not None
        assert "Straight" in result[0]
        assert result[1] == "contains"

    def test_contains_match_reverse(self):
        # opt is shorter and contained in target
        result = self._match("Straight fit jeans", ["Straight", "Slim"])
        assert result is not None
        assert result[0] == "Straight"

    def test_no_match_returns_none(self):
        result = self._match("Pyjamas", ["Good", "Very good", "New with tags"])
        assert result is None

    def test_prefers_longer_option_on_contains(self):
        """Longer (more specific) option should be preferred."""
        result = self._match("W34", ["W34 L32", "W34", "W34/L30"])
        # Exact match should win
        assert result == ("W34", "exact")

    def test_empty_options_returns_none(self):
        result = self._match("Medium", [])
        assert result is None

    def test_leading_trailing_whitespace_ignored(self):
        result = self._match("  Medium  ", ["Small", "Medium", "Large"])
        assert result == ("Medium", "exact")


# ---------------------------------------------------------------------------
# 4. Brand dropdown fallback — _open_brand_dropdown
# ---------------------------------------------------------------------------

class TestOpenBrandDropdown:
    """Test the 5-attempt brand dropdown opener using mocked Page."""

    def _make_page(self, content_visible_on_attempt: int):
        """Build a mock Page where content.is_visible() returns True on the Nth attempt."""
        page = MagicMock()
        content = MagicMock()
        loc = MagicMock()

        attempt = [0]  # mutable counter

        def is_visible():
            attempt[0] += 1
            return attempt[0] >= content_visible_on_attempt

        content.is_visible.side_effect = is_visible
        loc.wait_for = MagicMock()
        loc.scroll_into_view_if_needed = MagicMock()

        def locator(selector):
            if "brand-select-dropdown-content" in selector:
                return content
            if "brand-select-dropdown-input" in selector:
                m = MagicMock()
                m.first = loc
                return m
            return MagicMock()

        page.locator.side_effect = locator
        page.wait_for_timeout = MagicMock()
        page.evaluate = MagicMock(return_value=None)
        page.keyboard = MagicMock()
        return page, content

    def test_returns_true_on_attempt1(self):
        from app.draft_creator import _open_brand_dropdown
        page, content = self._make_page(content_visible_on_attempt=1)
        assert _open_brand_dropdown(page) is True

    def test_returns_true_on_attempt2(self):
        from app.draft_creator import _open_brand_dropdown
        page, content = self._make_page(content_visible_on_attempt=2)
        assert _open_brand_dropdown(page) is True

    def test_returns_true_on_attempt3(self):
        from app.draft_creator import _open_brand_dropdown
        page, _ = self._make_page(content_visible_on_attempt=3)
        assert _open_brand_dropdown(page) is True

    def test_returns_true_on_attempt4(self):
        from app.draft_creator import _open_brand_dropdown
        page, _ = self._make_page(content_visible_on_attempt=4)
        assert _open_brand_dropdown(page) is True

    def test_returns_true_on_attempt5_keyboard(self):
        from app.draft_creator import _open_brand_dropdown
        page, _ = self._make_page(content_visible_on_attempt=5)
        assert _open_brand_dropdown(page) is True
        page.keyboard.press.assert_called_with("Enter")

    def test_returns_false_when_all_attempts_fail(self):
        from app.draft_creator import _open_brand_dropdown
        page, _ = self._make_page(content_visible_on_attempt=99)
        assert _open_brand_dropdown(page) is False
