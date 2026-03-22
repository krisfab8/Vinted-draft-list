"""
Unit tests for app/services/alias_memory.py.

Pure-function tests — no I/O beyond a tmp-dir alias file.
"""
import json
import pytest
from unittest.mock import patch
from pathlib import Path


# ── Helpers ───────────────────────────────────────────────────────────────────

def _patch_file(tmp_path: Path):
    alias_file = tmp_path / "alias_memory.json"
    return patch("app.services.alias_memory._ALIAS_FILE", alias_file)


# ── TestLookupEmpty ───────────────────────────────────────────────────────────

class TestLookupEmpty:

    def test_brand_returns_none_on_empty_store(self, tmp_path):
        with _patch_file(tmp_path):
            from app.services import alias_memory
            assert alias_memory.lookup_brand("Ralph Lauren") is None

    def test_category_returns_none_on_empty_store(self, tmp_path):
        with _patch_file(tmp_path):
            from app.services import alias_memory
            assert alias_memory.lookup_category("Men > Clothing > Jeans") is None

    def test_item_type_returns_none_on_empty_store(self, tmp_path):
        with _patch_file(tmp_path):
            from app.services import alias_memory
            assert alias_memory.lookup_item_type("running trousers") is None


# ── TestSaveAndLookup ─────────────────────────────────────────────────────────

class TestSaveAndLookup:

    def test_save_and_lookup_brand_exact(self, tmp_path):
        with _patch_file(tmp_path):
            from app.services import alias_memory
            alias_memory.save_brand_alias("ralph laureen", "Ralph Lauren")
            assert alias_memory.lookup_brand("ralph laureen") == "Ralph Lauren"

    def test_save_and_lookup_category(self, tmp_path):
        with _patch_file(tmp_path):
            from app.services import alias_memory
            alias_memory.save_category_alias("Men > Jeans > Slim fit", "Men > Jeans > Slim")
            assert alias_memory.lookup_category("Men > Jeans > Slim fit") == "Men > Jeans > Slim"

    def test_save_and_lookup_item_type(self, tmp_path):
        with _patch_file(tmp_path):
            from app.services import alias_memory
            alias_memory.save_item_type_alias("running trousers", "joggers")
            assert alias_memory.lookup_item_type("running trousers") == "joggers"

    def test_lookup_is_case_insensitive(self, tmp_path):
        with _patch_file(tmp_path):
            from app.services import alias_memory
            alias_memory.save_brand_alias("barbour", "Barbour")
            # Lookup with different casing should still match
            assert alias_memory.lookup_brand("BARBOUR") == "Barbour"
            assert alias_memory.lookup_brand("Barbour") == "Barbour"

    def test_save_normalises_key(self, tmp_path):
        with _patch_file(tmp_path):
            from app.services import alias_memory
            alias_memory.save_brand_alias("  Barbour  ", "Barbour")
            # Normalised key should match stripped+lowercased
            data = json.loads((tmp_path / "alias_memory.json").read_text())
            assert "barbour" in data["brands"]

    def test_multiple_aliases_coexist(self, tmp_path):
        with _patch_file(tmp_path):
            from app.services import alias_memory
            alias_memory.save_brand_alias("barbour", "Barbour")
            alias_memory.save_brand_alias("hacket", "Hackett")
            assert alias_memory.lookup_brand("barbour") == "Barbour"
            assert alias_memory.lookup_brand("hacket") == "Hackett"

    def test_aliases_survive_reload(self, tmp_path):
        with _patch_file(tmp_path):
            from app.services import alias_memory
            alias_memory.save_brand_alias("hacket", "Hackett")

        # Re-patch to the same file path and reload
        with _patch_file(tmp_path):
            from app.services import alias_memory
            assert alias_memory.lookup_brand("hacket") == "Hackett"

    def test_category_and_brand_do_not_collide(self, tmp_path):
        with _patch_file(tmp_path):
            from app.services import alias_memory
            alias_memory.save_brand_alias("barbour", "Barbour")
            alias_memory.save_category_alias("barbour", "Men > Jackets")
            assert alias_memory.lookup_brand("barbour") == "Barbour"
            assert alias_memory.lookup_category("barbour") == "Men > Jackets"
