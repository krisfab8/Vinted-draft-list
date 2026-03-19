"""
Tests for price memory V1: _classify_material_group, _lookup_price_memory,
and _build_prompt price hint injection.

Run with:  .venv/bin/python -m pytest tests/test_price_memory.py -v
"""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# 1. Feature flag
# ---------------------------------------------------------------------------

class TestPriceMemoryFlag:
    def test_flag_exists_and_defaults_true(self):
        from app.config import ENABLE_PRICE_MEMORY
        assert ENABLE_PRICE_MEMORY is True

    def test_flag_importable_in_listing_writer(self):
        from app.listing_writer import ENABLE_PRICE_MEMORY  # noqa: F401


# ---------------------------------------------------------------------------
# 2. _classify_material_group
# ---------------------------------------------------------------------------

class TestClassifyMaterialGroup:
    def test_cashmere_identified(self):
        from app.listing_writer import _classify_material_group
        assert _classify_material_group(["90% Cashmere, 10% Wool"]) == "cashmere"

    def test_merino_maps_to_wool(self):
        from app.listing_writer import _classify_material_group
        assert _classify_material_group(["100% Merino Wool"]) == "wool"

    def test_lambswool_maps_to_wool(self):
        from app.listing_writer import _classify_material_group
        assert _classify_material_group(["100% Lambswool"]) == "wool"

    def test_plain_wool_maps_to_wool(self):
        from app.listing_writer import _classify_material_group
        assert _classify_material_group(["80% Wool, 20% Polyester"]) == "wool"

    def test_cashmere_beats_wool(self):
        """When both are present, cashmere takes priority."""
        from app.listing_writer import _classify_material_group
        assert _classify_material_group(["80% Wool", "20% Cashmere"]) == "cashmere"

    def test_silk_identified(self):
        from app.listing_writer import _classify_material_group
        assert _classify_material_group(["100% Silk"]) == "silk"

    def test_linen_identified(self):
        from app.listing_writer import _classify_material_group
        assert _classify_material_group(["55% Linen, 45% Cotton"]) == "linen"

    def test_leather_identified(self):
        from app.listing_writer import _classify_material_group
        assert _classify_material_group(["100% Leather"]) == "leather"

    def test_down_identified(self):
        from app.listing_writer import _classify_material_group
        assert _classify_material_group(["90% Down, 10% Feather"]) == "down"

    def test_cotton_identified(self):
        from app.listing_writer import _classify_material_group
        assert _classify_material_group(["100% Cotton"]) == "cotton"

    def test_polyester_maps_to_synthetic(self):
        from app.listing_writer import _classify_material_group
        assert _classify_material_group(["100% Polyester"]) == "synthetic"

    def test_empty_returns_none(self):
        from app.listing_writer import _classify_material_group
        assert _classify_material_group([]) is None

    def test_none_returns_none(self):
        from app.listing_writer import _classify_material_group
        assert _classify_material_group(None) is None


# ---------------------------------------------------------------------------
# 3. _lookup_price_memory — exact / brand matches
# ---------------------------------------------------------------------------

_SAMPLE_ENTRIES = [
    {
        "brand": "barbour",
        "item_type": "wax jacket",
        "material_group": None,
        "low": 55, "typical": 85, "high": 130,
        "source": "sold_listings", "confidence": "high",
    },
    {
        "brand": "suitsupply",
        "item_type": "blazer",
        "material_group": "wool",
        "low": 55, "typical": 85, "high": 130,
        "source": "sold_listings", "confidence": "high",
    },
    {
        "brand": None,
        "item_type": "blazer",
        "material_group": "wool",
        "low": 20, "typical": 40, "high": 80,
        "source": "manual", "confidence": "low",
    },
    {
        "brand": None,
        "item_type": "blazer",
        "material_group": "cashmere",
        "low": 40, "typical": 75, "high": 140,
        "source": "manual", "confidence": "low",
    },
    {
        "brand": None,
        "item_type": "jeans",
        "material_group": None,
        "low": 8, "typical": 15, "high": 30,
        "source": "manual", "confidence": "low",
    },
    {
        "brand": "levi's",
        "item_type": "jeans",
        "material_group": None,
        "low": 18, "typical": 30, "high": 55,
        "source": "sold_listings", "confidence": "high",
    },
]


@pytest.fixture(autouse=True)
def _reset_price_memory():
    """Reset the lazy-loaded cache between tests."""
    import app.listing_writer as lw
    original = lw._PRICE_MEMORY
    yield
    lw._PRICE_MEMORY = original


def _patch_entries(entries=None):
    """Context manager that patches _load_price_memory to return sample entries."""
    import app.listing_writer as lw
    lw._PRICE_MEMORY = entries if entries is not None else _SAMPLE_ENTRIES
    return lw


class TestLookupPriceMemory:
    def test_exact_brand_item_material_match(self):
        """Priority 1: brand + item_type + material_group match."""
        _patch_entries()
        from app.listing_writer import _lookup_price_memory
        result = _lookup_price_memory("Suitsupply", "blazer", ["80% Wool, 20% Polyester"])
        assert result is not None
        assert result["typical"] == 85
        assert result["match_level"] == "brand+item_type+material"

    def test_brand_item_match_material_agnostic(self):
        """Priority 2: brand + item_type, entry has material_group=None."""
        _patch_entries()
        from app.listing_writer import _lookup_price_memory
        result = _lookup_price_memory("Barbour", "wax jacket", ["100% Cotton"])
        assert result is not None
        assert result["typical"] == 85
        assert result["match_level"] == "brand+item_type"

    def test_fallback_item_type_material(self):
        """Priority 3: no brand match → falls back to item_type + material_group."""
        _patch_entries()
        from app.listing_writer import _lookup_price_memory
        result = _lookup_price_memory("Unknown Brand", "blazer", ["100% Wool"])
        assert result is not None
        assert result["match_level"] == "item_type+material"
        assert result["low"] == 20  # generic wool blazer

    def test_fallback_item_type_only(self):
        """Priority 4: item_type only when no brand or material match."""
        _patch_entries()
        from app.listing_writer import _lookup_price_memory
        result = _lookup_price_memory("Unknown Brand", "jeans", ["98% Cotton, 2% Elastane"])
        assert result is not None
        assert result["match_level"] == "item_type"
        assert result["typical"] == 15

    def test_no_match_returns_none(self):
        """Completely unknown item type returns None."""
        _patch_entries()
        from app.listing_writer import _lookup_price_memory
        result = _lookup_price_memory("Acme", "magic carpet", [])
        assert result is None

    def test_brand_match_beats_generic(self):
        """Brand match should return brand entry, not generic fallback."""
        _patch_entries()
        from app.listing_writer import _lookup_price_memory
        result = _lookup_price_memory("Levi's", "jeans", ["98% Cotton, 2% Elastane"])
        assert result is not None
        assert result["brand"] == "levi's"
        assert result["typical"] == 30
        assert result["low"] == 18

    def test_cashmere_beats_wool_fallback(self):
        """Cashmere blazer should match the cashmere entry, not wool."""
        _patch_entries()
        from app.listing_writer import _lookup_price_memory
        result = _lookup_price_memory(None, "blazer", ["90% Cashmere, 10% Wool"])
        assert result is not None
        assert result.get("material_group") == "cashmere"
        assert result["typical"] == 75

    def test_no_brand_item_type_material_match(self):
        """Explicit no-brand lookup can still match an item_type+material entry."""
        _patch_entries()
        from app.listing_writer import _lookup_price_memory
        result = _lookup_price_memory(None, "blazer", ["100% Wool"])
        assert result is not None
        assert result["match_level"] == "item_type+material"

    def test_case_insensitive_brand(self):
        """Brand lookup is case-insensitive."""
        _patch_entries()
        from app.listing_writer import _lookup_price_memory
        r1 = _lookup_price_memory("BARBOUR", "wax jacket", [])
        r2 = _lookup_price_memory("barbour", "wax jacket", [])
        assert r1 is not None and r2 is not None
        assert r1["typical"] == r2["typical"]

    def test_case_insensitive_item_type(self):
        """Item type lookup is case-insensitive."""
        _patch_entries()
        from app.listing_writer import _lookup_price_memory
        result = _lookup_price_memory("Levi's", "Jeans", [])
        assert result is not None

    def test_result_has_match_level_key(self):
        """Returned entry always includes match_level."""
        _patch_entries()
        from app.listing_writer import _lookup_price_memory
        result = _lookup_price_memory("Barbour", "wax jacket", [])
        assert "match_level" in result

    def test_result_has_price_fields(self):
        """Returned entry always has low, typical, high."""
        _patch_entries()
        from app.listing_writer import _lookup_price_memory
        result = _lookup_price_memory("Barbour", "wax jacket", [])
        assert isinstance(result["low"], (int, float))
        assert isinstance(result["typical"], (int, float))
        assert isinstance(result["high"], (int, float))
        assert result["low"] <= result["typical"] <= result["high"]


# ---------------------------------------------------------------------------
# 4. Flag disabled — no lookup performed
# ---------------------------------------------------------------------------

class TestFlagDisabledNoLookup:
    def test_lookup_returns_none_when_disabled(self, monkeypatch):
        import app.listing_writer as lw
        monkeypatch.setattr(lw, "ENABLE_PRICE_MEMORY", False)
        _patch_entries()
        result = lw._lookup_price_memory("Barbour", "wax jacket", [])
        assert result is None

    def test_prompt_has_no_price_memory_hint_when_disabled(self, monkeypatch):
        import app.listing_writer as lw
        monkeypatch.setattr(lw, "ENABLE_PRICE_MEMORY", False)
        _patch_entries()
        item = {
            "brand": "Barbour", "brand_confidence": "high",
            "item_type": "wax jacket", "gender": "men's",
            "tagged_size": "M", "normalized_size": "M",
            "materials": ["100% Cotton"], "colour": "Olive",
            "confidence": 0.9, "low_confidence_fields": [],
            "condition_summary": "Very good used condition — minimal wear.",
        }
        prompt = lw._build_prompt(item)
        assert "PRICE MEMORY HINT" not in prompt


# ---------------------------------------------------------------------------
# 5. _build_prompt includes price memory hint
# ---------------------------------------------------------------------------

class TestBuildPromptPriceMemoryHint:
    def _base_item(self, **overrides):
        base = {
            "brand": "Suitsupply", "brand_confidence": "high",
            "item_type": "blazer", "gender": "men's",
            "tagged_size": "44R", "normalized_size": "44R",
            "materials": ["80% Wool, 20% Polyester"], "colour": "Charcoal",
            "confidence": 0.9, "low_confidence_fields": [],
            "condition_summary": "Very good used condition — minimal wear.",
        }
        base.update(overrides)
        return base

    def test_price_hint_injected_for_known_brand(self):
        _patch_entries()
        from app.listing_writer import _build_prompt
        item = self._base_item()
        prompt = _build_prompt(item)
        assert "PRICE MEMORY HINT" in prompt
        assert "£85" in prompt  # Suitsupply blazer typical

    def test_price_hint_shows_range(self):
        _patch_entries()
        from app.listing_writer import _build_prompt
        item = self._base_item()
        prompt = _build_prompt(item)
        assert "£55" in prompt  # low
        assert "£130" in prompt  # high

    def test_price_hint_shows_match_level(self):
        _patch_entries()
        from app.listing_writer import _build_prompt
        item = self._base_item()
        prompt = _build_prompt(item)
        assert "brand+item_type" in prompt

    def test_price_hint_marks_as_hint_not_override(self):
        """Prompt must tell the model the price is a hint, not a hard constraint."""
        _patch_entries()
        from app.listing_writer import _build_prompt
        item = self._base_item()
        prompt = _build_prompt(item)
        assert "hint" in prompt.lower()

    def test_no_price_hint_for_unknown_item(self):
        """Unknown item_type with no memory entry produces no hint."""
        _patch_entries()
        from app.listing_writer import _build_prompt
        item = self._base_item(brand="Unknown Co", item_type="magic carpet")
        prompt = _build_prompt(item)
        assert "PRICE MEMORY HINT" not in prompt

    def test_fallback_entry_hint_shows_low_confidence(self):
        """Generic fallback entry hint should show confidence=low."""
        _patch_entries()
        from app.listing_writer import _build_prompt
        item = self._base_item(brand="SomeBrand", item_type="jeans",
                               materials=["98% Cotton, 2% Elastane"],
                               tagged_size="W32 L32", normalized_size="W32 L32",
                               trouser_waist="32", trouser_length="32")
        prompt = _build_prompt(item)
        assert "PRICE MEMORY HINT" in prompt
        assert "low" in prompt  # confidence level

    def test_price_hint_placed_in_notes_section(self):
        """Price memory hint must appear in the Notes section, not raw prompt body."""
        _patch_entries()
        from app.listing_writer import _build_prompt
        item = self._base_item()
        prompt = _build_prompt(item)
        notes_section = prompt.split("Notes:")[-1] if "Notes:" in prompt else ""
        assert "PRICE MEMORY HINT" in notes_section


# ---------------------------------------------------------------------------
# 6. Price memory data file is valid
# ---------------------------------------------------------------------------

class TestPriceMemoryDataFile:
    def test_file_exists(self):
        from pathlib import Path
        pm_file = Path(__file__).parent.parent / "data" / "price_memory.json"
        assert pm_file.exists(), "data/price_memory.json must exist"

    def test_file_is_valid_json(self):
        from pathlib import Path
        pm_file = Path(__file__).parent.parent / "data" / "price_memory.json"
        data = json.loads(pm_file.read_text())
        assert "entries" in data

    def test_entries_have_required_fields(self):
        from pathlib import Path
        pm_file = Path(__file__).parent.parent / "data" / "price_memory.json"
        data = json.loads(pm_file.read_text())
        for e in data["entries"]:
            for field in ("item_type", "low", "typical", "high", "confidence"):
                assert field in e, f"Entry missing '{field}': {e}"
            assert e["low"] <= e["typical"] <= e["high"], \
                f"Price ordering broken: {e}"

    def test_entries_non_empty(self):
        from pathlib import Path
        pm_file = Path(__file__).parent.parent / "data" / "price_memory.json"
        data = json.loads(pm_file.read_text())
        assert len(data["entries"]) >= 10, "Expected ≥10 price memory entries"

    def test_load_price_memory_returns_list(self):
        import app.listing_writer as lw
        lw._PRICE_MEMORY = None  # force reload
        result = lw._load_price_memory()
        assert isinstance(result, list)
        assert len(result) >= 10
