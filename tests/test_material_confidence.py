"""
Tests for material-confidence gating of the material re-read call.

Run with:  .venv/bin/python -m pytest tests/test_material_confidence.py -v
"""
from unittest.mock import MagicMock, patch
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _result(**kw) -> dict:
    """Build a minimal extraction result dict."""
    base = {
        "brand": "Barbour",
        "brand_confidence": "high",
        "item_type": "wax jacket",
        "materials": ["100% Cotton"],
        "material_confidence": "high",
        "material_reason": "Label clearly readable.",
        "material_candidates": [],
        "pricing_sensitive_material": False,
        "fabric_mill": None,
        "gender": "men's",
        "confidence": 0.9,
        "low_confidence_fields": [],
        "condition_summary": "Very good used condition — minimal wear.",
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# 1. _should_reread_material — pure function tests
# ---------------------------------------------------------------------------

class TestShouldRereadMaterial:
    def test_empty_materials_always_rerereads(self):
        from app.extractor import _should_reread_material
        assert _should_reread_material(_result(materials=[])) is True

    def test_none_materials_always_rerereads(self):
        from app.extractor import _should_reread_material
        assert _should_reread_material(_result(materials=None)) is True

    def test_missing_materials_treated_as_empty(self):
        from app.extractor import _should_reread_material
        r = _result()
        del r["materials"]
        assert _should_reread_material(r) is True

    def test_low_confidence_always_rerereads(self):
        from app.extractor import _should_reread_material
        assert _should_reread_material(_result(
            materials=["100% Cotton"], material_confidence="low"
        )) is True

    def test_missing_confidence_treated_as_low(self):
        """Backward compat: result without material_confidence → reread."""
        from app.extractor import _should_reread_material
        r = _result(materials=["100% Cotton"])
        del r["material_confidence"]
        assert _should_reread_material(r) is True

    def test_high_confidence_basic_cotton_skips(self):
        from app.extractor import _should_reread_material
        assert _should_reread_material(_result(
            materials=["100% Cotton"], material_confidence="high",
            pricing_sensitive_material=False
        )) is False

    def test_high_confidence_polyester_skips(self):
        from app.extractor import _should_reread_material
        assert _should_reread_material(_result(
            materials=["65% Polyester", "35% Cotton"], material_confidence="high",
            pricing_sensitive_material=False
        )) is False

    def test_high_confidence_wool_still_skips(self):
        """High confidence overrides pricing sensitivity — trust the read."""
        from app.extractor import _should_reread_material
        assert _should_reread_material(_result(
            materials=["100% Wool"], material_confidence="high",
            pricing_sensitive_material=True
        )) is False

    def test_medium_confidence_pricing_sensitive_flag_rerereads(self):
        from app.extractor import _should_reread_material
        assert _should_reread_material(_result(
            materials=["80% Wool", "20% Polyester"],
            material_confidence="medium",
            pricing_sensitive_material=True,
        )) is True

    def test_medium_confidence_cashmere_in_materials_rerereads(self):
        """Deterministic fibre check triggers reread even if flag is False."""
        from app.extractor import _should_reread_material
        assert _should_reread_material(_result(
            materials=["90% Cashmere", "10% Nylon"],
            material_confidence="medium",
            pricing_sensitive_material=False,   # model forgot to set flag
        )) is True

    def test_medium_confidence_wool_in_materials_rerereads(self):
        from app.extractor import _should_reread_material
        assert _should_reread_material(_result(
            materials=["70% Wool", "30% Polyester"],
            material_confidence="medium",
            pricing_sensitive_material=False,
        )) is True

    def test_medium_confidence_linen_rerereads(self):
        from app.extractor import _should_reread_material
        assert _should_reread_material(_result(
            materials=["100% Linen"],
            material_confidence="medium",
            pricing_sensitive_material=False,
        )) is True

    def test_medium_confidence_silk_rerereads(self):
        from app.extractor import _should_reread_material
        assert _should_reread_material(_result(
            materials=["100% Silk"],
            material_confidence="medium",
            pricing_sensitive_material=False,
        )) is True

    def test_medium_confidence_leather_rerereads(self):
        from app.extractor import _should_reread_material
        assert _should_reread_material(_result(
            materials=["Leather upper"],
            material_confidence="medium",
            pricing_sensitive_material=False,
        )) is True

    def test_medium_confidence_polyester_tshirt_skips(self):
        """Non-premium material + non-premium item → skip at medium."""
        from app.extractor import _should_reread_material
        assert _should_reread_material(_result(
            materials=["100% Polyester"],
            material_confidence="medium",
            pricing_sensitive_material=False,
            item_type="t-shirt",
        )) is False

    def test_medium_confidence_cotton_polo_skips(self):
        from app.extractor import _should_reread_material
        assert _should_reread_material(_result(
            materials=["100% Cotton"],
            material_confidence="medium",
            pricing_sensitive_material=False,
            item_type="polo shirt",
        )) is False

    def test_medium_confidence_polyester_blazer_rerereads(self):
        """Even synthetic fibre triggers reread for tailoring — material matters."""
        from app.extractor import _should_reread_material
        assert _should_reread_material(_result(
            materials=["100% Polyester"],
            material_confidence="medium",
            pricing_sensitive_material=False,
            item_type="blazer",
        )) is True

    def test_medium_confidence_cotton_jumper_rerereads(self):
        """Knitwear item type triggers reread — could be misread cashmere/acrylic."""
        from app.extractor import _should_reread_material
        assert _should_reread_material(_result(
            materials=["100% Cotton"],
            material_confidence="medium",
            pricing_sensitive_material=False,
            item_type="cotton jumper",
        )) is True

    def test_medium_confidence_trouser_rerereads(self):
        from app.extractor import _should_reread_material
        assert _should_reread_material(_result(
            materials=["65% Polyester", "35% Viscose"],
            material_confidence="medium",
            pricing_sensitive_material=False,
            item_type="wool trousers",
        )) is True

    def test_pricing_sensitive_fibres_set_nonempty(self):
        from app.extractor import _PRICING_SENSITIVE_FIBRES
        assert len(_PRICING_SENSITIVE_FIBRES) >= 10
        for f in ("cashmere", "wool", "linen", "silk", "leather", "down"):
            assert f in _PRICING_SENSITIVE_FIBRES

    def test_pricing_sensitive_item_types_set_nonempty(self):
        from app.extractor import _PRICING_SENSITIVE_ITEM_TYPES
        assert len(_PRICING_SENSITIVE_ITEM_TYPES) >= 6
        for t in ("blazer", "jumper", "coat", "trouser"):
            assert t in _PRICING_SENSITIVE_ITEM_TYPES


# ---------------------------------------------------------------------------
# 2. Extraction prompt — material_confidence fields present
# ---------------------------------------------------------------------------

class TestExtractionPromptMaterialFields:
    def test_prompt_has_material_confidence(self):
        from app.extractor import _EXTRACT_PROMPT
        assert "material_confidence" in _EXTRACT_PROMPT

    def test_prompt_has_material_reason(self):
        from app.extractor import _EXTRACT_PROMPT
        assert "material_reason" in _EXTRACT_PROMPT

    def test_prompt_has_material_candidates(self):
        from app.extractor import _EXTRACT_PROMPT
        assert "material_candidates" in _EXTRACT_PROMPT

    def test_prompt_has_pricing_sensitive_material(self):
        from app.extractor import _EXTRACT_PROMPT
        assert "pricing_sensitive_material" in _EXTRACT_PROMPT

    def test_prompt_has_material_confidence_rules(self):
        from app.extractor import _EXTRACT_PROMPT
        assert "MATERIAL CONFIDENCE" in _EXTRACT_PROMPT

    def test_prompt_rules_mention_care_label_noise(self):
        """Model should be told NOT to include care instructions as materials."""
        from app.extractor import _EXTRACT_PROMPT
        assert "care instructions" in _EXTRACT_PROMPT or "Machine Wash" in _EXTRACT_PROMPT


# ---------------------------------------------------------------------------
# 3. _reread_material_photo — full_reread vs mill-only
# ---------------------------------------------------------------------------

class TestRereadMaterialPhoto:
    def _mock_response(self, payload: dict, max_tok: int = 150):
        import json
        mock = MagicMock()
        mock.content = [MagicMock(text=json.dumps(payload))]
        mock.usage.input_tokens = 1500
        mock.usage.output_tokens = max_tok
        return mock

    def test_mill_only_returns_dict_with_fabric_mill(self, tmp_path):
        from PIL import Image
        Image.new("RGB", (400, 300)).save(str(tmp_path / "material.jpg"))

        with patch("app.extractor.anthropic") as mock_anth:
            mock_anth.Anthropic.return_value.messages.create.return_value = (
                self._mock_response({"fabric_mill": "Tessuti Sondrio"})
            )
            from app.extractor import _reread_material_photo
            result = _reread_material_photo(tmp_path, "claude-haiku-4-5-20251001", full_reread=False)

        assert result is not None
        assert result.get("fabric_mill") == "Tessuti Sondrio"
        # mill-only should NOT return materials
        assert "materials" not in result or result.get("materials") is None

    def test_full_reread_returns_materials_and_mill(self, tmp_path):
        from PIL import Image
        Image.new("RGB", (400, 300)).save(str(tmp_path / "material.jpg"))

        with patch("app.extractor.anthropic") as mock_anth:
            mock_anth.Anthropic.return_value.messages.create.return_value = (
                self._mock_response({
                    "materials": ["80% Wool", "20% Polyester"],
                    "fabric_mill": "Vitale Barberis Canonico"
                })
            )
            from app.extractor import _reread_material_photo
            result = _reread_material_photo(tmp_path, "claude-haiku-4-5-20251001", full_reread=True)

        assert result is not None
        assert result["materials"] == ["80% Wool", "20% Polyester"]
        assert result["fabric_mill"] == "Vitale Barberis Canonico"

    def test_full_reread_uses_1024px(self, tmp_path):
        from PIL import Image
        Image.new("RGB", (3024, 3024)).save(str(tmp_path / "material.jpg"))

        captured = {}
        from app.extractor import _compress_with_autocrop as real_cwa

        def spy(path, max_dim):
            captured["max_dim"] = max_dim
            return real_cwa(path, max_dim)

        with patch("app.extractor._compress_with_autocrop", side_effect=spy), \
             patch("app.extractor.anthropic") as mock_anth:
            mock_anth.Anthropic.return_value.messages.create.return_value = (
                self._mock_response({"materials": ["100% Cotton"], "fabric_mill": None})
            )
            from app.extractor import _reread_material_photo
            _reread_material_photo(tmp_path, "claude-haiku-4-5-20251001", full_reread=True)

        assert captured.get("max_dim") == 1024

    def test_missing_photo_returns_none(self, tmp_path):
        from app.extractor import _reread_material_photo
        result = _reread_material_photo(tmp_path, "claude-haiku-4-5-20251001")
        assert result is None


# ---------------------------------------------------------------------------
# 4. Integration: extract() gates material reread correctly
# ---------------------------------------------------------------------------

def _make_extraction_mock(payload: dict, input_tokens: int = 5000, output_tokens: int = 200):
    import json
    mock = MagicMock()
    mock.content = [MagicMock(text=json.dumps(payload))]
    mock.usage.input_tokens = input_tokens
    mock.usage.output_tokens = output_tokens
    return mock


class TestExtractMaterialGating:
    def _setup_folder(self, tmp_path):
        from PIL import Image
        for name in ("front", "brand", "material"):
            Image.new("RGB", (400, 300)).save(str(tmp_path / f"{name}.jpg"))

    def _run(self, tmp_path, extraction_payload: dict):
        self._setup_folder(tmp_path)
        mock_resp = _make_extraction_mock(extraction_payload)
        reread_calls = []

        def fake_reread(folder, model, full_reread=False):
            reread_calls.append({"full_reread": full_reread})
            if full_reread:
                return {"materials": extraction_payload.get("materials", []), "fabric_mill": None}
            return {"fabric_mill": None}

        with patch("app.extractor.anthropic") as mock_anth, \
             patch("app.extractor._reread_material_photo", side_effect=fake_reread), \
             patch("app.extractor._reread_brand_photo", return_value=None):
            mock_anth.Anthropic.return_value.messages.create.return_value = mock_resp
            from app.extractor import extract
            result, _ = extract(str(tmp_path))

        return result, reread_calls

    def _base_payload(self, **overrides):
        base = {
            "brand": "Next", "brand_confidence": "high",
            "brand_reason": "Clear.", "brand_candidates": [], "sub_brand": None,
            "model_name": None, "item_type": "t-shirt",
            "tagged_size": "M", "normalized_size": "M",
            "trouser_waist": None, "trouser_length": None,
            "style": None, "cut": None, "fabric_mill": "Tessuti Sondrio",
            "made_in": None, "colour": "White", "colour_secondary": None,
            "pattern": "Plain", "gender": "men's",
            "condition_summary": "Very good used condition — minimal wear.",
            "flaws_note": None, "tag_keywords": [], "tag_keywords_confidence": "high",
            "confidence": 0.9, "low_confidence_fields": [],
        }
        base.update(overrides)
        return base

    def test_high_confidence_basic_material_skips_full_reread(self, tmp_path):
        payload = self._base_payload(
            materials=["100% Cotton"],
            material_confidence="high",
            material_reason="Clear.", material_candidates=[],
            pricing_sensitive_material=False,
        )
        _, calls = self._run(tmp_path, payload)
        full_rereads = [c for c in calls if c["full_reread"]]
        assert len(full_rereads) == 0, "high confidence basic material should skip full reread"

    def test_low_confidence_triggers_full_reread(self, tmp_path):
        payload = self._base_payload(
            materials=["80% Wool", "20% Polyester"],
            material_confidence="low",
            material_reason="Label blurry.", material_candidates=[],
            pricing_sensitive_material=True,
        )
        _, calls = self._run(tmp_path, payload)
        full_rereads = [c for c in calls if c["full_reread"]]
        assert len(full_rereads) == 1, "low confidence should trigger full reread"

    def test_missing_materials_triggers_full_reread(self, tmp_path):
        payload = self._base_payload(
            materials=[],
            material_confidence="low",
            material_reason="No label found.", material_candidates=[],
            pricing_sensitive_material=False,
        )
        _, calls = self._run(tmp_path, payload)
        full_rereads = [c for c in calls if c["full_reread"]]
        assert len(full_rereads) == 1, "empty materials should trigger full reread"

    def test_medium_confidence_wool_triggers_full_reread(self, tmp_path):
        payload = self._base_payload(
            materials=["80% Wool", "20% Polyester"],
            material_confidence="medium",
            material_reason="Partially obscured.", material_candidates=[],
            pricing_sensitive_material=False,  # model forgot the flag
            item_type="blazer",
        )
        _, calls = self._run(tmp_path, payload)
        full_rereads = [c for c in calls if c["full_reread"]]
        assert len(full_rereads) == 1

    def test_medium_confidence_polyester_tshirt_skips_full_reread(self, tmp_path):
        payload = self._base_payload(
            materials=["100% Polyester"],
            material_confidence="medium",
            material_reason="Slightly faded.", material_candidates=[],
            pricing_sensitive_material=False,
            item_type="t-shirt",
        )
        _, calls = self._run(tmp_path, payload)
        full_rereads = [c for c in calls if c["full_reread"]]
        assert len(full_rereads) == 0, "non-premium t-shirt at medium should skip full reread"

    def test_high_confidence_without_fabric_mill_does_mill_only_reread(self, tmp_path):
        """When material is confident but no fabric_mill found — still do mill-only reread."""
        payload = self._base_payload(
            materials=["100% Cotton"],
            material_confidence="high",
            material_reason="Clear.", material_candidates=[],
            pricing_sensitive_material=False,
            fabric_mill=None,   # no mill found
        )
        _, calls = self._run(tmp_path, payload)
        mill_only_calls = [c for c in calls if not c["full_reread"]]
        assert len(mill_only_calls) == 1, "high confidence + no fabric_mill should trigger mill-only reread"

    def test_high_confidence_with_fabric_mill_skips_all_rereads(self, tmp_path):
        """High confidence AND fabric_mill already set → no reread at all."""
        payload = self._base_payload(
            materials=["100% Cotton"],
            material_confidence="high",
            material_reason="Clear.", material_candidates=[],
            pricing_sensitive_material=False,
            fabric_mill="Tessuti Sondrio",  # already found
        )
        _, calls = self._run(tmp_path, payload)
        assert len(calls) == 0, "high confidence + fabric_mill set should skip all material rereads"


# ---------------------------------------------------------------------------
# 5. Care-label noise
# ---------------------------------------------------------------------------

class TestCareInstructionNoise:
    def test_care_instructions_excluded_from_materials_prompt(self):
        """Extraction prompt must explicitly exclude care instructions."""
        from app.extractor import _EXTRACT_PROMPT
        # The prompt should mention not to include wash/care symbols
        assert any(term in _EXTRACT_PROMPT for term in (
            "care instructions", "Machine Wash", "Dry Clean", "wash symbols"
        ))

    def test_full_reread_prompt_excludes_care_instructions(self, tmp_path):
        """The full_reread prompt text should tell model to exclude care label noise."""
        from PIL import Image
        Image.new("RGB", (400, 300)).save(str(tmp_path / "material.jpg"))

        captured_prompts = []

        def fake_create(**kwargs):
            msgs = kwargs.get("messages", [])
            for m in msgs:
                for block in (m.get("content") or []):
                    if isinstance(block, dict) and block.get("type") == "text":
                        captured_prompts.append(block["text"])
            mock = MagicMock()
            mock.content = [MagicMock(text='{"materials": [], "fabric_mill": null}')]
            return mock

        with patch("app.extractor.anthropic") as mock_anth:
            mock_anth.Anthropic.return_value.messages.create.side_effect = fake_create
            from app.extractor import _reread_material_photo
            _reread_material_photo(tmp_path, "test-model", full_reread=True)

        assert captured_prompts, "Expected prompt text to be captured"
        prompt = captured_prompts[0]
        assert "care" in prompt.lower() or "Machine Wash" in prompt or "Dry Clean" in prompt
