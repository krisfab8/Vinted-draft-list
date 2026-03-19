"""
Tests for brand-confidence gating of the brand re-read call.

Run with:  .venv/bin/python -m pytest tests/test_brand_confidence.py -v
"""
from unittest.mock import MagicMock, patch, call
import pytest


# ---------------------------------------------------------------------------
# 1. _should_reread_brand — pure logic tests (no I/O)
# ---------------------------------------------------------------------------

class TestShouldRereadBrand:
    def test_none_brand_always_rerereads(self):
        from app.extractor import _should_reread_brand
        assert _should_reread_brand({"brand": None, "brand_confidence": "high"}) is True

    def test_low_confidence_always_rerereads(self):
        from app.extractor import _should_reread_brand
        assert _should_reread_brand({"brand": "Hackett", "brand_confidence": "low"}) is True

    def test_missing_confidence_treated_as_low(self):
        """Backward compat: result without brand_confidence → reread."""
        from app.extractor import _should_reread_brand
        assert _should_reread_brand({"brand": "Barbour"}) is True

    def test_high_confidence_skips_reread(self):
        from app.extractor import _should_reread_brand
        assert _should_reread_brand({"brand": "Barbour", "brand_confidence": "high"}) is False

    def test_high_confidence_cheap_brand_skips_reread(self):
        from app.extractor import _should_reread_brand
        for brand in ("Next", "Marks & Spencer", "Ben Sherman", "Farah"):
            assert _should_reread_brand({"brand": brand, "brand_confidence": "high"}) is False, \
                f"{brand} with high confidence should skip reread"

    def test_medium_confidence_premium_brand_rerereads(self):
        from app.extractor import _should_reread_brand, _REREAD_PREMIUM_BRANDS
        for brand in ("Barbour", "Moncler", "Stone Island", "Hackett", "Ermenegildo Zegna"):
            result = {"brand": brand, "brand_confidence": "medium"}
            assert _should_reread_brand(result) is True, \
                f"{brand} with medium confidence should trigger reread"

    def test_medium_confidence_non_premium_skips_reread(self):
        from app.extractor import _should_reread_brand
        for brand in ("Next", "Marks & Spencer", "Ben Sherman", "Lyle & Scott", "Gant"):
            result = {"brand": brand, "brand_confidence": "medium"}
            assert _should_reread_brand(result) is False, \
                f"{brand} with medium confidence should skip reread"

    def test_premium_brand_set_non_empty(self):
        from app.extractor import _REREAD_PREMIUM_BRANDS
        assert len(_REREAD_PREMIUM_BRANDS) >= 10
        # Key luxury brands must be in there
        for b in ("moncler", "brioni", "stone island", "barbour"):
            assert b in _REREAD_PREMIUM_BRANDS, f"'{b}' missing from _REREAD_PREMIUM_BRANDS"

    def test_brand_case_insensitive(self):
        """Premium check should be case-insensitive."""
        from app.extractor import _should_reread_brand
        assert _should_reread_brand({"brand": "MONCLER", "brand_confidence": "medium"}) is True
        assert _should_reread_brand({"brand": "moncler", "brand_confidence": "medium"}) is True


# ---------------------------------------------------------------------------
# 2. Extraction prompt — brand_confidence fields present
# ---------------------------------------------------------------------------

class TestExtractionPromptFields:
    def test_prompt_has_brand_confidence_field(self):
        from app.extractor import _EXTRACT_PROMPT
        assert "brand_confidence" in _EXTRACT_PROMPT

    def test_prompt_has_brand_reason_field(self):
        from app.extractor import _EXTRACT_PROMPT
        assert "brand_reason" in _EXTRACT_PROMPT

    def test_prompt_has_brand_candidates_field(self):
        from app.extractor import _EXTRACT_PROMPT
        assert "brand_candidates" in _EXTRACT_PROMPT

    def test_prompt_has_sub_brand_field(self):
        from app.extractor import _EXTRACT_PROMPT
        assert "sub_brand" in _EXTRACT_PROMPT

    def test_prompt_has_brand_confidence_rules(self):
        from app.extractor import _EXTRACT_PROMPT
        assert "BRAND CONFIDENCE" in _EXTRACT_PROMPT
        assert '"high"' in _EXTRACT_PROMPT
        assert '"medium"' in _EXTRACT_PROMPT
        assert '"low"' in _EXTRACT_PROMPT


# ---------------------------------------------------------------------------
# 3. Integration: extract() gates reread based on brand_confidence
# ---------------------------------------------------------------------------

def _make_mock_response(payload: dict, input_tokens: int = 5000, output_tokens: int = 200):
    """Build a mock Anthropic response object."""
    import json
    mock = MagicMock()
    mock.content = [MagicMock(text=json.dumps(payload))]
    mock.usage.input_tokens = input_tokens
    mock.usage.output_tokens = output_tokens
    return mock


def _base_extraction_result(**overrides) -> dict:
    base = {
        "brand": "Barbour",
        "brand_confidence": "high",
        "brand_reason": "Clearly reads BARBOUR in large woven text.",
        "brand_candidates": [],
        "sub_brand": None,
        "model_name": None,
        "item_type": "wax jacket",
        "tagged_size": "M",
        "normalized_size": "M",
        "trouser_waist": None,
        "trouser_length": None,
        "style": None,
        "cut": None,
        "materials": ["100% Cotton"],
        "fabric_mill": None,
        "made_in": "England",
        "colour": "Olive",
        "colour_secondary": None,
        "pattern": "Plain",
        "gender": "men's",
        "condition_summary": "Very good used condition — minimal wear.",
        "flaws_note": None,
        "tag_keywords": [],
        "tag_keywords_confidence": "high",
        "confidence": 0.95,
        "low_confidence_fields": [],
    }
    base.update(overrides)
    return base


class TestExtractRereadGating:
    """Integration tests: verify reread is called/skipped correctly."""

    def _run_extract(self, tmp_path, extraction_result: dict):
        """Run extract() with a mocked API, return (result, reread_call_count)."""
        from PIL import Image
        for name in ("front", "brand", "material"):
            img = Image.new("RGB", (400, 300))
            img.save(str(tmp_path / f"{name}.jpg"))

        mock_resp = _make_mock_response(extraction_result)
        reread_calls = []

        def fake_reread(folder, model):
            reread_calls.append(folder)
            return {"brand": extraction_result.get("brand"), "collection_keywords": []}

        with patch("app.extractor.anthropic") as mock_anth, \
             patch("app.extractor._reread_brand_photo", side_effect=fake_reread):
            mock_anth.Anthropic.return_value.messages.create.return_value = mock_resp
            from app.extractor import extract
            result, _ = extract(str(tmp_path))

        return result, len(reread_calls)

    def test_high_confidence_skips_reread(self, tmp_path):
        result, n_rerereads = self._run_extract(
            tmp_path, _base_extraction_result(brand_confidence="high")
        )
        assert n_rerereads == 0, "high confidence should skip reread"

    def test_low_confidence_triggers_reread(self, tmp_path):
        result, n_rerereads = self._run_extract(
            tmp_path, _base_extraction_result(brand_confidence="low")
        )
        assert n_rerereads == 1, "low confidence should trigger reread"

    def test_none_brand_triggers_reread(self, tmp_path):
        result, n_rerereads = self._run_extract(
            tmp_path, _base_extraction_result(brand=None, brand_confidence="low")
        )
        assert n_rerereads == 1, "None brand should trigger reread"

    def test_medium_confidence_premium_triggers_reread(self, tmp_path):
        result, n_rerereads = self._run_extract(
            tmp_path, _base_extraction_result(
                brand="Moncler", brand_confidence="medium",
                brand_reason="Logo partially obscured."
            )
        )
        assert n_rerereads == 1, "premium brand with medium confidence should trigger reread"

    def test_medium_confidence_non_premium_skips_reread(self, tmp_path):
        result, n_rerereads = self._run_extract(
            tmp_path, _base_extraction_result(
                brand="Next", brand_confidence="medium",
                brand_reason="Readable but slightly faded."
            )
        )
        assert n_rerereads == 0, "non-premium brand with medium confidence should skip reread"


# ---------------------------------------------------------------------------
# 4. Brand separation: mill vs model vs brand
# ---------------------------------------------------------------------------

class TestBrandSeparation:
    def test_known_mill_in_brand_field_gets_cleared(self):
        """_sanitise_brand moves fabric mills out of brand field."""
        from app.extractor import _sanitise_brand
        result = {"brand": "Tessuti Sondrio", "fabric_mill": None}
        out = _sanitise_brand(result)
        assert out["brand"] is None
        assert out["fabric_mill"] == "Tessuti Sondrio"

    def test_vbc_in_brand_field_gets_cleared(self):
        from app.extractor import _sanitise_brand
        result = {"brand": "Vitale Barberis Canonico", "fabric_mill": None}
        out = _sanitise_brand(result)
        assert out["brand"] is None

    def test_legitimate_brand_not_cleared(self):
        from app.extractor import _sanitise_brand
        for brand in ("Barbour", "Hackett", "Hugo Boss", "Suitsupply", "Ermenegildo Zegna"):
            result = {"brand": brand, "fabric_mill": None}
            out = _sanitise_brand(result)
            assert out["brand"] == brand, f"'{brand}' should not be cleared by _sanitise_brand"

    def test_extraction_prompt_separates_brand_from_model(self):
        """Verify the prompt explicitly explains brand vs model distinction."""
        from app.extractor import _EXTRACT_PROMPT
        assert "BRAND vs MODEL" in _EXTRACT_PROMPT
        assert "model_name" in _EXTRACT_PROMPT
        assert "MANUFACTURER" in _EXTRACT_PROMPT

    def test_extraction_prompt_calls_out_fabric_mills(self):
        from app.extractor import _EXTRACT_PROMPT
        assert "FABRIC MILLS ARE NEVER THE BRAND" in _EXTRACT_PROMPT
        assert "Tessuti Sondrio" in _EXTRACT_PROMPT
