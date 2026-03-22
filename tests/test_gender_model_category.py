"""
Unit tests for:
  - Gender confidence inference (_infer_gender_confidence)
  - Deterministic model extraction (_extract_model_deterministic)
  - Category alias resolution for jogger/track-pant variants

Pure-function tests — no I/O, no AI, no Flask.
"""
import pytest

from app.extractor import _infer_gender_confidence, _extract_model_deterministic
from app.draft_creator import _resolve_category_key


# ── _infer_gender_confidence ──────────────────────────────────────────────────

class TestInferGenderConfidence:

    def test_low_when_gender_in_low_confidence_fields(self):
        result = {"low_confidence_fields": ["gender", "brand"]}
        assert _infer_gender_confidence(result) == "low"

    def test_high_when_women_in_tag_keywords(self):
        result = {"tag_keywords": ["Women", "Size 12"]}
        assert _infer_gender_confidence(result) == "high"

    def test_high_when_ladies_in_tag_keywords(self):
        result = {"tag_keywords": ["Ladies fit", "Cotton"]}
        assert _infer_gender_confidence(result) == "high"

    def test_high_when_wmn_in_tag_keywords(self):
        result = {"tag_keywords": ["WMN", "Activewear"]}
        assert _infer_gender_confidence(result) == "high"

    def test_high_when_womens_in_tag_keywords(self):
        result = {"tag_keywords": ["Womens", "Regular Fit"]}
        assert _infer_gender_confidence(result) == "high"

    def test_medium_when_no_explicit_evidence(self):
        result = {"tag_keywords": ["Super 120s", "Full canvas"]}
        assert _infer_gender_confidence(result) == "medium"

    def test_medium_when_empty_tag_keywords(self):
        result = {"tag_keywords": []}
        assert _infer_gender_confidence(result) == "medium"

    def test_medium_when_no_tag_keywords_key(self):
        result = {}
        assert _infer_gender_confidence(result) == "medium"

    def test_low_overrides_explicit_keyword(self):
        # If gender is already low-confidence per AI, tag evidence still defers
        # (AI uncertainty wins for safety — better to show a warning)
        result = {
            "low_confidence_fields": ["gender"],
            "tag_keywords": ["Women"],
        }
        assert _infer_gender_confidence(result) == "low"

    def test_case_insensitive_keyword_match(self):
        result = {"tag_keywords": ["WOMEN", "Size M"]}
        assert _infer_gender_confidence(result) == "high"


# ── _extract_model_deterministic ─────────────────────────────────────────────

class TestExtractModelDeterministic:
    """Uses brands in data/brands.txt (Barbour is a confirmed single-word brand)."""

    def test_splits_known_brand_plus_model(self):
        # "Barbour Beaufort" — Barbour is in brands.txt
        result = {"brand": "Barbour Beaufort", "tag_keywords": []}
        model, conf = _extract_model_deterministic(result)
        assert conf == "high"
        assert model == "Beaufort"
        assert result["brand"] == "Barbour"

    def test_does_not_split_single_word_brand(self):
        result = {"brand": "Barbour", "tag_keywords": []}
        model, conf = _extract_model_deterministic(result)
        assert conf == "low"
        assert model is None
        # brand unchanged
        assert result["brand"] == "Barbour"

    def test_does_not_split_unknown_brand(self):
        # "Acme Widget" — neither word is a known brand
        result = {"brand": "Acme Widget", "tag_keywords": []}
        model, conf = _extract_model_deterministic(result)
        assert conf == "low"
        assert model is None

    def test_preserves_multi_word_brand_ralph_lauren(self):
        # "Ralph Lauren" is in brands.txt as two words — should NOT be split
        result = {"brand": "Ralph Lauren", "tag_keywords": []}
        model, conf = _extract_model_deterministic(result)
        assert conf == "low"
        assert model is None
        assert result["brand"] == "Ralph Lauren"

    def test_splits_multi_word_brand_plus_model(self):
        # "Ralph Lauren Polo" — "ralph lauren" matches, model = "Polo"
        result = {"brand": "Ralph Lauren Polo", "tag_keywords": []}
        model, conf = _extract_model_deterministic(result)
        assert conf == "high"
        assert model == "Polo"
        assert result["brand"] == "Ralph Lauren"

    def test_empty_brand_returns_low(self):
        result = {"brand": "", "tag_keywords": []}
        model, conf = _extract_model_deterministic(result)
        assert conf == "low"
        assert model is None

    def test_none_brand_returns_low(self):
        result = {"brand": None, "tag_keywords": []}
        model, conf = _extract_model_deterministic(result)
        assert conf == "low"
        assert model is None

    def test_does_not_raise_on_missing_brand_key(self):
        result = {"tag_keywords": []}
        model, conf = _extract_model_deterministic(result)
        assert conf == "low"
        assert model is None


# ── Category alias resolution — jogger variants ───────────────────────────────

class TestJoggerCategoryAliases:

    def _resolve(self, raw: str) -> str | None:
        return _resolve_category_key(raw)

    # Men's
    def test_mens_running_pants_resolves(self):
        assert self._resolve("Men > Trousers > Running Pants") == "Men > Trousers > Joggers"

    def test_mens_tracksuit_bottoms_resolves(self):
        assert self._resolve("Men > Trousers > Tracksuit Bottoms") == "Men > Trousers > Joggers"

    def test_mens_track_pants_resolves(self):
        assert self._resolve("Men > Trousers > Track Pants") == "Men > Trousers > Joggers"

    def test_mens_sweatpants_resolves(self):
        assert self._resolve("Men > Trousers > Sweatpants") == "Men > Trousers > Joggers"

    def test_mens_joggers_direct(self):
        assert self._resolve("Men > Trousers > Joggers") == "Men > Trousers > Joggers"

    # Women's
    def test_womens_running_pants_resolves(self):
        assert self._resolve("Women > Trousers > Running Pants") == "Women > Trousers > Joggers"

    def test_womens_track_pants_resolves(self):
        assert self._resolve("Women > Trousers > Track Pants") == "Women > Trousers > Joggers"

    def test_womens_tracksuit_bottoms_resolves(self):
        assert self._resolve("Women > Trousers > Tracksuit Bottoms") == "Women > Trousers > Joggers"

    def test_womens_sweatpants_resolves(self):
        assert self._resolve("Women > Trousers > Sweatpants") == "Women > Trousers > Joggers"

    def test_womens_joggers_direct(self):
        assert self._resolve("Women > Trousers > Joggers") == "Women > Trousers > Joggers"

    # Fallback: unmapped string returns None (existing behaviour preserved)
    def test_completely_unknown_category_returns_none(self):
        assert self._resolve("Men > Trousers > HoverPants") is None


# ── Gender prompt default ─────────────────────────────────────────────────────

class TestGenderPromptDefault:

    def test_prompt_contains_default_mens(self):
        """Verify the extraction prompt tells the model to default to men's."""
        from app.extractor import _EXTRACT_PROMPT
        assert "default to men's" in _EXTRACT_PROMPT.lower()

    def test_prompt_no_longer_says_never_default_mens(self):
        """Old wording removed."""
        from app.extractor import _EXTRACT_PROMPT
        assert "never default to men" not in _EXTRACT_PROMPT.lower()
