"""
Regression tests for the graphic-vs-plain t-shirt routing pipeline.

Covers three layers:
  1. Extractor schema  — pattern="Graphic" is a valid extractor output
  2. Listing writer    — _apply_top_style converts pattern/item_type to style
  3. Draft creator     — _resolve_category_key routes base + style to CATEGORY_NAV

Run with:  .venv/bin/python -m pytest tests/test_graphic_tee_pipeline.py -v
"""
import pytest


# ---------------------------------------------------------------------------
# 1. Extractor schema — pattern="Graphic" is a documented valid value
# ---------------------------------------------------------------------------

class TestExtractorPatternField:
    """The extractor prompt includes 'Graphic' in its pattern enum."""

    def test_graphic_is_valid_pattern_value(self):
        """'Graphic' must appear in the extractor prompt schema string."""
        from app.extractor import _EXTRACT_PROMPT
        assert "Graphic" in _EXTRACT_PROMPT

    def test_plain_is_valid_pattern_value(self):
        from app.extractor import _EXTRACT_PROMPT
        assert "Plain" in _EXTRACT_PROMPT


# ---------------------------------------------------------------------------
# 2. Listing writer — _apply_top_style deterministic post-processing
# ---------------------------------------------------------------------------

class TestApplyTopStyle:
    def _apply(self, listing, pattern=None, item_type=None):
        from app.listing_writer import _apply_top_style
        return _apply_top_style(dict(listing), pattern, item_type)

    # --- Graphic signal from pattern ---

    def test_pattern_graphic_sets_style_graphic(self):
        result = self._apply({}, pattern="Graphic", item_type="t-shirt")
        assert result["style"] == "Graphic"

    def test_pattern_graphic_overrides_plain_style_from_llm(self):
        """If LLM hallucinated style=Plain but pattern=Graphic, Graphic wins."""
        result = self._apply({"style": "Plain"}, pattern="Graphic", item_type="t-shirt")
        assert result["style"] == "Graphic"

    # --- Graphic signal from item_type ---

    def test_item_type_band_tee_sets_graphic(self):
        result = self._apply({}, pattern=None, item_type="band tee")
        assert result["style"] == "Graphic"

    def test_item_type_slogan_tee_sets_graphic(self):
        result = self._apply({}, pattern=None, item_type="slogan tee")
        assert result["style"] == "Graphic"

    def test_item_type_graphic_tee_sets_graphic(self):
        result = self._apply({}, pattern=None, item_type="graphic tee")
        assert result["style"] == "Graphic"

    def test_item_type_printed_tshirt_sets_graphic(self):
        result = self._apply({}, pattern=None, item_type="printed t-shirt")
        assert result["style"] == "Graphic"

    # --- Plain signal ---

    def test_pattern_plain_fills_style_when_unset(self):
        result = self._apply({"style": None}, pattern="Plain", item_type="t-shirt")
        assert result["style"] == "Plain"

    def test_pattern_plain_does_not_override_llm_style(self):
        """LLM already set style (e.g. Long-sleeve) — plain pattern must not stomp it."""
        result = self._apply({"style": "Long-sleeve"}, pattern="Plain", item_type="t-shirt")
        assert result["style"] == "Long-sleeve"

    # --- Non-tshirt items are untouched ---

    def test_non_tshirt_item_type_not_modified(self):
        result = self._apply({"style": None}, pattern="Graphic", item_type="hoodie")
        assert result["style"] is None

    def test_blazer_not_modified(self):
        result = self._apply({"style": "Slim"}, pattern="Plain", item_type="blazer")
        assert result["style"] == "Slim"

    # --- Missing pattern does not force Plain on a generic category ---

    def test_missing_pattern_leaves_style_unchanged(self):
        """No pattern signal: don't touch whatever the LLM set."""
        result = self._apply({"style": None}, pattern=None, item_type="t-shirt")
        assert result["style"] is None

    def test_missing_pattern_does_not_blindly_set_plain(self):
        result = self._apply({}, pattern=None, item_type="t-shirt")
        assert result.get("style") != "Plain"


# ---------------------------------------------------------------------------
# 3. Draft creator — base category + style resolves to correct CATEGORY_NAV key
# ---------------------------------------------------------------------------

class TestGraphicTeeDraftRouting:
    def _resolve(self, raw, style=None):
        from app.draft_creator import _resolve_category_key
        return _resolve_category_key(raw, style)

    def _nav(self, key):
        from app.draft_creator import CATEGORY_NAV
        return CATEGORY_NAV.get(key)

    # --- Full pipeline: base + Graphic style ---

    def test_base_plus_graphic_style_resolves(self):
        assert self._resolve("Men > T-shirts", style="Graphic") == "Men > T-shirts > Graphic"

    def test_graphic_nav_path_ends_with_print(self):
        path = self._nav("Men > T-shirts > Graphic")
        assert path is not None
        assert path[-1] == "Print"

    # --- Full pipeline: base + Plain style ---

    def test_base_plus_plain_style_resolves(self):
        assert self._resolve("Men > T-shirts", style="Plain") == "Men > T-shirts > Plain"

    def test_plain_nav_path_ends_with_plain_tshirts(self):
        path = self._nav("Men > T-shirts > Plain")
        assert path is not None
        assert path[-1] == "Plain t-shirts"

    # --- Aliases from the draft creator CATEGORY_ALIASES ---

    def test_alias_band_tee_resolves_to_graphic(self):
        assert self._resolve("Men > T-shirts > Band tee") == "Men > T-shirts > Graphic"

    def test_alias_slogan_resolves_to_graphic(self):
        assert self._resolve("Men > T-shirts > Slogan") == "Men > T-shirts > Graphic"

    def test_alias_print_resolves_to_graphic(self):
        assert self._resolve("Men > T-shirts > Print") == "Men > T-shirts > Graphic"

    def test_alias_printed_resolves_to_graphic(self):
        assert self._resolve("Men > T-shirts > Printed") == "Men > T-shirts > Graphic"

    # --- Direct key pass-through ---

    def test_direct_graphic_key_unchanged(self):
        assert self._resolve("Men > T-shirts > Graphic") == "Men > T-shirts > Graphic"

    # --- End-to-end: extractor dict -> _apply_top_style -> _resolve_category_key ---

    def test_full_path_pattern_graphic(self):
        """Simulate: extractor outputs pattern=Graphic, item_type=t-shirt.
        listing_writer _apply_top_style sets style=Graphic.
        draft_creator resolves base category + Graphic to CATEGORY_NAV key."""
        from app.listing_writer import _apply_top_style

        # Extractor output (simplified)
        extracted = {"pattern": "Graphic", "item_type": "t-shirt"}
        # Listing writer LLM gave us base category + no style yet
        listing = {"category": "Men > T-shirts", "style": None}
        listing = _apply_top_style(listing, extracted["pattern"], extracted["item_type"])

        assert listing["style"] == "Graphic"
        nav_key = self._resolve(listing["category"], style=listing["style"])
        assert nav_key == "Men > T-shirts > Graphic"
        assert self._nav(nav_key)[-1] == "Print"

    def test_full_path_pattern_plain(self):
        from app.listing_writer import _apply_top_style

        extracted = {"pattern": "Plain", "item_type": "t-shirt"}
        listing = {"category": "Men > T-shirts", "style": None}
        listing = _apply_top_style(listing, extracted["pattern"], extracted["item_type"])

        assert listing["style"] == "Plain"
        nav_key = self._resolve(listing["category"], style=listing["style"])
        assert nav_key == "Men > T-shirts > Plain"
        assert self._nav(nav_key)[-1] == "Plain t-shirts"
