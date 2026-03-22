"""
Tests for listing accuracy improvements:
- _format_trouser_size (deterministic size formatting)
- _clean_materials (material cleanup)
"""
from app.listing_writer import _format_trouser_size, _clean_materials


class TestFormatTrouserSize:

    def test_inches_only_waist_and_length(self):
        assert _format_trouser_size("32", "32", None, None) == "W32 L32"

    def test_inches_and_cm_both(self):
        assert _format_trouser_size("34", "33", "86", "84") == "W34 L33 (86cm / 84cm)"

    def test_cm_with_suffix_stripped(self):
        assert _format_trouser_size("32", "32", "81cm", "81cm") == "W32 L32 (81cm / 81cm)"

    def test_waist_only_no_length(self):
        assert _format_trouser_size("34", None, None, None) == "W34"

    def test_waist_only_with_waist_cm(self):
        assert _format_trouser_size("34", None, "86", None) == "W34 (86cm)"

    def test_no_waist_returns_none(self):
        assert _format_trouser_size(None, "32", None, None) is None

    def test_inches_first_when_both_present(self):
        result = _format_trouser_size("32", "30", "81", "76")
        assert result.startswith("W32 L30")
        assert "(81cm / 76cm)" in result

    def test_length_cm_without_waist_cm_omitted(self):
        # If waist_cm is missing, cm block should not appear
        result = _format_trouser_size("32", "32", None, "81")
        assert result == "W32 L32"


class TestCleanMaterials:

    def test_keeps_known_fibres(self):
        mats = ["80% Wool", "20% Nylon"]
        assert _clean_materials(mats) == mats

    def test_drops_brand_fabric_name(self):
        mats = ["Chester Chum fabric", "100% Cotton"]
        result = _clean_materials(mats)
        assert "Chester Chum fabric" not in result
        assert "100% Cotton" in result

    def test_drops_hallucinated_techweave(self):
        mats = ["TechWeave Pro", "95% Polyester", "5% Elastane"]
        result = _clean_materials(mats)
        assert "TechWeave Pro" not in result
        assert len(result) == 2

    def test_keeps_lining_entries(self):
        mats = ["Shell: 100% Wool", "Lining: 100% Viscose"]
        result = _clean_materials(mats)
        assert len(result) == 2

    def test_empty_list(self):
        assert _clean_materials([]) == []

    def test_all_clean(self):
        mats = ["100% Cashmere"]
        assert _clean_materials(mats) == mats

    def test_all_junk_returns_empty(self):
        mats = ["PerformaDry X2", "AeroShield Plus"]
        assert _clean_materials(mats) == []

    def test_case_insensitive_match(self):
        mats = ["100% MERINO WOOL"]
        assert _clean_materials(mats) == mats

    def test_preserves_multiword_fibres(self):
        mats = ["80% Lambswool", "20% Polyamide"]
        assert _clean_materials(mats) == mats
