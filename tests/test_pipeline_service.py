"""
Tests for app/services/pipeline.py

Covers:
- build_hints_from_listing: brand, gender, size, item_type, made_in preservation
- preserve_user_fields: meta fields, condition, style, category lock
- run_pipeline: wiring (mocked extractor + listing_writer)

These are pure-function / unit tests — no Flask app, no files, no browser.
"""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from app.services.pipeline import (
    build_hints_from_listing,
    preserve_user_fields,
    run_pipeline,
)


# ── build_hints_from_listing ──────────────────────────────────────────────────

class TestBuildHintsFromListing:

    def test_brand_preserved_from_existing(self):
        existing = {"brand": "Barbour", "gender": "men's"}
        hints = build_hints_from_listing(existing)
        assert hints["brand"] == "Barbour"

    def test_brand_update_takes_priority(self):
        existing = {"brand": "Barbour"}
        hints = build_hints_from_listing(existing, updates={"brand": "Hugo Boss"})
        assert hints["brand"] == "Hugo Boss"

    def test_brand_missing_not_in_hints(self):
        hints = build_hints_from_listing({})
        assert "brand" not in hints

    def test_gender_preserved(self):
        existing = {"gender": "women's"}
        hints = build_hints_from_listing(existing)
        assert hints["gender"] == "women's"

    def test_made_in_preserved(self):
        existing = {"brand": "Loake", "made_in": "England"}
        hints = build_hints_from_listing(existing)
        assert hints["made_in"] == "England"

    def test_item_type_preserved_from_existing(self):
        existing = {"item_type": "chelsea boots"}
        hints = build_hints_from_listing(existing)
        assert hints["item_type"] == "chelsea boots"

    def test_item_type_update_takes_priority(self):
        existing = {"item_type": "boots"}
        hints = build_hints_from_listing(existing, updates={"item_type": "chelsea boots"})
        assert hints["item_type"] == "chelsea boots"

    def test_wl_size_preserved(self):
        existing = {"normalized_size": "W32 L32"}
        hints = build_hints_from_listing(existing)
        assert hints["size"] == "W32 L32"

    def test_letter_size_preserved(self):
        existing = {"normalized_size": "M"}
        hints = build_hints_from_listing(existing)
        assert hints["size"] == "M"

    def test_size_update_overrides_existing(self):
        existing = {"normalized_size": "W32 L32"}
        hints = build_hints_from_listing(existing, updates={"normalized_size": "W34 L32"})
        assert hints["size"] == "W34 L32"

    def test_wl_built_from_measurements(self):
        existing = {"trouser_waist": "32", "trouser_length": "30", "normalized_size": "52"}
        hints = build_hints_from_listing(existing)
        assert hints["size"] == "W32 L30"

    def test_bare_eu_size_no_wl_hint(self):
        # EU number with no measurements — no size hint should be generated
        existing = {"normalized_size": "44"}
        hints = build_hints_from_listing(existing)
        assert "size" not in hints

    def test_all_fields_together(self):
        existing = {
            "brand": "Loake",
            "gender": "men's",
            "made_in": "England",
            "item_type": "oxford shoes",
            "normalized_size": "9",
        }
        hints = build_hints_from_listing(existing)
        assert hints["brand"] == "Loake"
        assert hints["gender"] == "men's"
        assert hints["made_in"] == "England"
        assert hints["item_type"] == "oxford shoes"


# ── preserve_user_fields ──────────────────────────────────────────────────────

class TestPreserveUserFields:

    def test_meta_fields_preserved(self):
        existing = {"draft_url": "https://vinted.co.uk/items/123", "cost_gbp": 0.003}
        new_listing = {}
        preserve_user_fields(existing, new_listing)
        assert new_listing["draft_url"] == "https://vinted.co.uk/items/123"
        assert new_listing["cost_gbp"] == 0.003

    def test_meta_field_not_overwritten_if_already_in_new(self):
        existing = {"draft_url": "https://old.url"}
        new_listing = {"draft_url": "https://new.url"}
        preserve_user_fields(existing, new_listing)
        # setdefault — new value wins
        assert new_listing["draft_url"] == "https://new.url"

    def test_condition_summary_preserved_when_not_in_updates(self):
        existing = {"condition_summary": "Very good used condition — clean throughout."}
        new_listing = {"condition_summary": "Excellent used condition — unworn."}
        preserve_user_fields(existing, new_listing, updates={})
        assert new_listing["condition_summary"] == "Very good used condition — clean throughout."

    def test_condition_summary_updated_when_in_updates(self):
        existing = {"condition_summary": "Very good used condition — clean throughout."}
        new_listing = {"condition_summary": "Good used condition — light wear."}
        preserve_user_fields(existing, new_listing, updates={"condition_summary": "Good used condition — light wear."})
        assert new_listing["condition_summary"] == "Good used condition — light wear."

    def test_style_preserved_if_ai_omits_it(self):
        existing = {"style": "Chelsea"}
        new_listing = {}  # AI didn't return style
        preserve_user_fields(existing, new_listing)
        assert new_listing["style"] == "Chelsea"

    def test_style_not_overwritten_if_ai_returned_it(self):
        existing = {"style": "Chelsea"}
        new_listing = {"style": "Ankle"}
        preserve_user_fields(existing, new_listing)
        # existing style only fills gap; if new_listing already has it, it stays
        assert new_listing["style"] == "Ankle"

    def test_category_locked_restored(self):
        existing = {
            "category": "Men > Shoes > Boots > Chelsea",
            "category_locked": True,
        }
        new_listing = {"category": "Men > Shoes > Boots > Desert"}
        preserve_user_fields(existing, new_listing)
        assert new_listing["category"] == "Men > Shoes > Boots > Chelsea"
        assert new_listing["category_locked"] is True

    def test_category_not_locked_when_flag_absent(self):
        existing = {"category": "Men > Shoes > Boots > Chelsea"}
        new_listing = {"category": "Men > Shoes > Boots > Desert"}
        preserve_user_fields(existing, new_listing)
        # no lock — AI category wins
        assert new_listing["category"] == "Men > Shoes > Boots > Desert"


# ── run_pipeline (wired, mocked) ──────────────────────────────────────────────

class TestRunPipeline:

    def _make_extract_result(self):
        return (
            {"brand": "Barbour", "item_type": "wax jacket", "_extract_log": {"photos_found": ["front"]}},
            {"input_tokens": 100, "output_tokens": 50, "model": "claude-haiku-4-5"},
        )

    def _make_write_result(self):
        return (
            {"title": "Barbour Jacket Mens M Olive Waxed Cotton", "price_gbp": 95},
            {"input_tokens": 200, "output_tokens": 80, "model": "claude-haiku-4-5", "_write_log": {"category_slice_level": "gender"}},
        )

    @patch("app.services.pipeline.listing_writer")
    @patch("app.services.pipeline.extractor")
    def test_returns_five_tuple(self, mock_extractor, mock_writer):
        mock_extractor.extract.return_value = self._make_extract_result()
        mock_writer.write.return_value = self._make_write_result()

        result = run_pipeline(Path("/fake/folder"), hints={"brand": "Barbour"})
        assert len(result) == 5

    @patch("app.services.pipeline.listing_writer")
    @patch("app.services.pipeline.extractor")
    def test_extract_log_popped_from_item(self, mock_extractor, mock_writer):
        mock_extractor.extract.return_value = self._make_extract_result()
        mock_writer.write.return_value = self._make_write_result()

        listing, extract_usage, write_usage, extract_log, write_log = run_pipeline(
            Path("/fake/folder"), hints={}
        )
        # _extract_log should be returned separately, not in item passed to writer
        assert "_extract_log" not in mock_writer.write.call_args[0][0]
        assert extract_log == {"photos_found": ["front"]}

    @patch("app.services.pipeline.listing_writer")
    @patch("app.services.pipeline.extractor")
    def test_write_log_popped_from_usage(self, mock_extractor, mock_writer):
        mock_extractor.extract.return_value = self._make_extract_result()
        mock_writer.write.return_value = self._make_write_result()

        listing, extract_usage, write_usage, extract_log, write_log = run_pipeline(
            Path("/fake/folder"), hints={}
        )
        assert "_write_log" not in write_usage
        assert write_log == {"category_slice_level": "gender"}

    @patch("app.services.pipeline.listing_writer")
    @patch("app.services.pipeline.extractor")
    def test_buy_price_set_on_item(self, mock_extractor, mock_writer):
        mock_extractor.extract.return_value = self._make_extract_result()
        mock_writer.write.return_value = self._make_write_result()

        run_pipeline(Path("/fake/folder"), hints={}, buy_price_gbp=12.50)
        item_passed = mock_writer.write.call_args[0][0]
        assert item_passed["buy_price_gbp"] == 12.50

    @patch("app.services.pipeline.listing_writer")
    @patch("app.services.pipeline.extractor")
    def test_buy_price_none_not_set(self, mock_extractor, mock_writer):
        mock_extractor.extract.return_value = self._make_extract_result()
        mock_writer.write.return_value = self._make_write_result()

        run_pipeline(Path("/fake/folder"), hints={}, buy_price_gbp=None)
        item_passed = mock_writer.write.call_args[0][0]
        assert "buy_price_gbp" not in item_passed

    @patch("app.services.pipeline.listing_writer")
    @patch("app.services.pipeline.extractor")
    def test_hints_forwarded_to_both_calls(self, mock_extractor, mock_writer):
        mock_extractor.extract.return_value = self._make_extract_result()
        mock_writer.write.return_value = self._make_write_result()

        hints = {"brand": "Barbour", "gender": "men's"}
        run_pipeline(Path("/fake/folder"), hints=hints)

        mock_extractor.extract.assert_called_once_with(Path("/fake/folder"), hints=hints)
        mock_writer.write.assert_called_once()
        _, write_kwargs = mock_writer.write.call_args
        assert write_kwargs.get("hints") == hints
