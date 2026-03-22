"""
Tests for premium fabric mill recognition.

Covers:
- _is_premium_mill() helper
- pricing_sensitive_material override in write() post-processing
- brand NOT cleared for dual-use brand/mill names
- fabric_line preserved
- fabric_mill.py: normalise_mill(), infer_material_hint(), scan_for_mill()
"""
import pytest
from app.listing_writer import _is_premium_mill
from app.extractor import _KNOWN_MILLS, _sanitise_brand


# ── TestIsPremiumMill ─────────────────────────────────────────────────────────

class TestIsPremiumMill:

    def test_loro_piana_recognised(self):
        assert _is_premium_mill("Loro Piana") is True

    def test_loro_piana_fabric_recognised(self):
        assert _is_premium_mill("Loro Piana fabric") is True

    def test_vbc_recognised(self):
        assert _is_premium_mill("Vitale Barberis Canonico") is True

    def test_vbc_abbreviation(self):
        assert _is_premium_mill("VBC") is True

    def test_dormeuil_recognised(self):
        assert _is_premium_mill("Dormeuil") is True

    def test_holland_sherry_recognised(self):
        assert _is_premium_mill("Holland & Sherry") is True

    def test_scabal_recognised(self):
        assert _is_premium_mill("Scabal") is True

    def test_drago_recognised(self):
        assert _is_premium_mill("Drago") is True

    def test_reda_recognised(self):
        assert _is_premium_mill("Reda") is True

    def test_thomas_mason_recognised(self):
        assert _is_premium_mill("Thomas Mason") is True

    def test_case_insensitive(self):
        assert _is_premium_mill("LORO PIANA") is True
        assert _is_premium_mill("loro piana") is True

    def test_none_returns_false(self):
        assert _is_premium_mill(None) is False

    def test_empty_string_returns_false(self):
        assert _is_premium_mill("") is False

    def test_garment_brand_not_flagged(self):
        assert _is_premium_mill("Boggi Milano") is False
        assert _is_premium_mill("Hugo Boss") is False
        assert _is_premium_mill("Barbour") is False

    def test_partial_match_recognised(self):
        # "Tessuti Sondrio" is premium — partial text from a label
        assert _is_premium_mill("Tessuti Sondrio") is True


# ── TestBrandNotClearedForDualUseName ─────────────────────────────────────────

class TestBrandNotClearedForDualUseName:
    """Loro Piana and Ermenegildo Zegna are also garment brands.
    _sanitise_brand must not move them to fabric_mill when set as brand."""

    def test_loro_piana_brand_not_cleared(self):
        result = {"brand": "Loro Piana", "fabric_mill": None}
        out = _sanitise_brand(result)
        assert out["brand"] == "Loro Piana", "Loro Piana is a garment brand — should not be cleared"

    def test_ermenegildo_zegna_brand_not_cleared(self):
        result = {"brand": "Ermenegildo Zegna", "fabric_mill": None}
        out = _sanitise_brand(result)
        assert out["brand"] == "Ermenegildo Zegna", "Zegna is a garment brand — should not be cleared"

    def test_vbc_brand_is_cleared(self):
        """VBC is exclusively a mill — should be moved."""
        result = {"brand": "Vitale Barberis Canonico", "fabric_mill": None}
        out = _sanitise_brand(result)
        assert out["brand"] is None
        assert out["fabric_mill"] == "Vitale Barberis Canonico"

    def test_drago_brand_is_cleared(self):
        result = {"brand": "Drago", "fabric_mill": None}
        out = _sanitise_brand(result)
        assert out["brand"] is None
        assert out["fabric_mill"] == "Drago"


# ── TestPremiumMillPricingSignal ──────────────────────────────────────────────

class TestPremiumMillPricingSignal:
    """pricing_sensitive_material must be True when premium mill is set."""

    def _run_write(self, item: dict) -> dict:
        """Run listing_writer.write() with mocked AI response."""
        import json
        from unittest.mock import patch, MagicMock

        fake_listing = {
            "brand": item.get("brand", "Boggi Milano"),
            "item_type": item.get("item_type", "blazer"),
            "title": "Boggi Milano Blazer Loro Piana Mens 44R Charcoal",
            "description": "Classic blazer. Cloth: Loro Piana.\n\nKeywords: boggi milano blazer charcoal",
            "tagged_size": "44R",
            "normalized_size": "44R",
            "materials": ["100% Wool"],
            "colour": "Charcoal",
            "colour_secondary": None,
            "style": None,
            "cut": None,
            "pattern": "Plain",
            "tag_keywords": [],
            "tag_keywords_confidence": "high",
            "gender": "men's",
            "price_gbp": 65,
            "category": "Men > Suits > Blazers",
            "condition_summary": "Very good used condition.",
            "flaws_note": None,
            "made_in": "Italy",
            "fabric_mill": item.get("fabric_mill"),
            "premium": True,
            "confidence": 0.9,
            "low_confidence_fields": [],
            "pricing_sensitive_material": False,
        }

        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=json.dumps(fake_listing))]
        mock_msg.usage = MagicMock(input_tokens=100, output_tokens=50)
        mock_msg.model = "claude-haiku-4-5"

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_msg

        with patch("app.listing_writer.anthropic.Anthropic", return_value=mock_client):
            from app.listing_writer import write
            listing, _ = write(item)
        return listing

    def test_pricing_sensitive_set_when_premium_mill(self):
        item = {
            "brand": "Boggi Milano",
            "item_type": "blazer",
            "materials": ["100% Wool"],
            "fabric_mill": "Loro Piana",
            "colour": "Charcoal",
            "tagged_size": "44R",
            "normalized_size": "44R",
            "gender": "men's",
            "condition_summary": "Very good used condition.",
            "confidence": 0.9,
            "low_confidence_fields": [],
        }
        listing = self._run_write(item)
        assert listing["pricing_sensitive_material"] is True

    def test_fabric_line_preserved_when_set(self):
        item = {
            "brand": "Boggi Milano",
            "item_type": "blazer",
            "materials": ["100% Wool"],
            "fabric_mill": "Loro Piana",
            "fabric_line": "Trofeo",
            "colour": "Charcoal",
            "tagged_size": "44R",
            "normalized_size": "44R",
            "gender": "men's",
            "condition_summary": "Very good used condition.",
            "confidence": 0.9,
            "low_confidence_fields": [],
        }
        listing = self._run_write(item)
        assert listing.get("fabric_line") == "Trofeo"

    def test_pricing_sensitive_not_forced_for_non_premium_mill(self):
        item = {
            "brand": "Boggi Milano",
            "item_type": "blazer",
            "materials": ["100% Wool"],
            "fabric_mill": "Some Unknown Mill",
            "colour": "Charcoal",
            "tagged_size": "44R",
            "normalized_size": "44R",
            "gender": "men's",
            "condition_summary": "Very good used condition.",
            "confidence": 0.9,
            "low_confidence_fields": [],
        }
        listing = self._run_write(item)
        # Should remain whatever the AI returned (False in our fake)
        assert listing["pricing_sensitive_material"] is False


# ── TestNormaliseMill ─────────────────────────────────────────────────────────

class TestNormaliseMill:

    def test_exact_canonical_match(self):
        from app.services.fabric_mill import normalise_mill
        assert normalise_mill("loro piana") == "Loro Piana"

    def test_case_insensitive_canonical(self):
        from app.services.fabric_mill import normalise_mill
        assert normalise_mill("LORO PIANA") == "Loro Piana"

    def test_ocr_alias_loro_plana(self):
        from app.services.fabric_mill import normalise_mill
        assert normalise_mill("Loro Plana") == "Loro Piana"

    def test_ocr_alias_vitale_barberis_variant(self):
        from app.services.fabric_mill import normalise_mill
        assert normalise_mill("Vitale Barberis") == "Vitale Barberis Canonico"

    def test_vbc_abbreviation(self):
        from app.services.fabric_mill import normalise_mill
        assert normalise_mill("VBC") == "Vitale Barberis Canonico"

    def test_holland_and_sherry_variant(self):
        from app.services.fabric_mill import normalise_mill
        assert normalise_mill("Holland and Sherry") == "Holland & Sherry"

    def test_none_returns_none(self):
        from app.services.fabric_mill import normalise_mill
        assert normalise_mill(None) is None

    def test_empty_returns_none(self):
        from app.services.fabric_mill import normalise_mill
        assert normalise_mill("") is None

    def test_garment_brand_returned_unchanged(self):
        from app.services.fabric_mill import normalise_mill
        # Boggi is not a known mill
        result = normalise_mill("Boggi Milano")
        assert result == "Boggi Milano"


# ── TestInferMaterialHint ─────────────────────────────────────────────────────

class TestInferMaterialHint:

    def test_zealander_dream_returns_merino_hint(self):
        from app.services.fabric_mill import infer_material_hint
        hint = infer_material_hint("Loro Piana", "Zealander Dream", [])
        assert hint == "Pure New Zealand Merino Wool"

    def test_trofeo_returns_super_130s_hint(self):
        from app.services.fabric_mill import infer_material_hint
        hint = infer_material_hint("Loro Piana", "Trofeo", [])
        assert "130s" in hint

    def test_case_insensitive_cloth_line(self):
        from app.services.fabric_mill import infer_material_hint
        hint = infer_material_hint("Loro Piana", "ZEALANDER DREAM", [])
        assert hint == "Pure New Zealand Merino Wool"

    def test_no_hint_when_composition_present(self):
        from app.services.fabric_mill import infer_material_hint
        # Already have percentages — don't add a hint
        hint = infer_material_hint("Loro Piana", "Trofeo", ["80% Wool", "20% Polyester"])
        assert hint is None

    def test_mill_fallback_when_no_line(self):
        from app.services.fabric_mill import infer_material_hint
        hint = infer_material_hint("Loro Piana", None, [])
        assert hint is not None
        assert "Italian" in hint or "Wool" in hint

    def test_unknown_mill_returns_none(self):
        from app.services.fabric_mill import infer_material_hint
        hint = infer_material_hint("Boggi Milano", None, [])
        assert hint is None


# ── TestScanForMill ───────────────────────────────────────────────────────────

class TestScanForMill:

    def test_normalises_fabric_mill(self):
        from app.services.fabric_mill import scan_for_mill
        result = {"fabric_mill": "Loro Plana", "materials": [], "tag_keywords": []}
        out = scan_for_mill(result)
        assert out["fabric_mill"] == "Loro Piana"

    def test_infers_material_hint_from_mill_and_line(self):
        from app.services.fabric_mill import scan_for_mill
        result = {
            "fabric_mill": "Loro Piana",
            "fabric_line": "Zealander Dream",
            "materials": [],
            "tag_keywords": [],
        }
        out = scan_for_mill(result)
        assert out.get("material_hint") == "Pure New Zealand Merino Wool"

    def test_moves_mill_from_materials(self):
        from app.services.fabric_mill import scan_for_mill
        result = {
            "fabric_mill": None,
            "materials": ["Vitale Barberis Canonico"],
            "tag_keywords": [],
        }
        out = scan_for_mill(result)
        assert out["fabric_mill"] == "Vitale Barberis Canonico"
        assert "Vitale Barberis Canonico" not in out["materials"]

    def test_does_not_move_fibre_entries_from_materials(self):
        from app.services.fabric_mill import scan_for_mill
        result = {
            "fabric_mill": None,
            "materials": ["80% Wool", "20% Polyester"],
            "tag_keywords": [],
        }
        out = scan_for_mill(result)
        assert out["materials"] == ["80% Wool", "20% Polyester"]

    def test_picks_up_mill_from_tag_keywords(self):
        from app.services.fabric_mill import scan_for_mill
        result = {
            "fabric_mill": None,
            "materials": [],
            "tag_keywords": ["Loro Piana"],
        }
        out = scan_for_mill(result)
        assert out["fabric_mill"] == "Loro Piana"

    def test_does_not_overwrite_existing_mill(self):
        from app.services.fabric_mill import scan_for_mill
        result = {
            "fabric_mill": "Dormeuil",
            "materials": [],
            "tag_keywords": ["Loro Piana"],
        }
        out = scan_for_mill(result)
        # Dormeuil was set — should normalise it but not overwrite with LP
        assert out["fabric_mill"] == "Dormeuil"

    def test_no_hint_when_material_hint_already_set(self):
        from app.services.fabric_mill import scan_for_mill
        result = {
            "fabric_mill": "Loro Piana",
            "fabric_line": "Trofeo",
            "material_hint": "Existing hint",
            "materials": [],
            "tag_keywords": [],
        }
        out = scan_for_mill(result)
        assert out["material_hint"] == "Existing hint"
