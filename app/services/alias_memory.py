"""
Operator alias memory.

Persists corrected brands, categories, and item_types to data/alias_memory.json
so future runs auto-apply them without repeating the same manual correction.

All keys are normalised (strip + lowercase) for case-insensitive matching.

Shape:
{
    "brands":     {"ai brand": "Corrected Brand"},
    "categories": {"ai category": "Correct > Category"},
    "item_types": {"ai item type": "corrected item type"}
}
"""
from __future__ import annotations

import json
from pathlib import Path

from app.config import ROOT

_ALIAS_FILE = ROOT / "data" / "alias_memory.json"

_EMPTY: dict[str, dict[str, str]] = {"brands": {}, "categories": {}, "item_types": {}}


def _norm(s: str) -> str:
    return s.strip().lower()


def _load() -> dict[str, dict[str, str]]:
    if not _ALIAS_FILE.exists():
        return {"brands": {}, "categories": {}, "item_types": {}}
    try:
        data = json.loads(_ALIAS_FILE.read_text(encoding="utf-8"))
        return {
            "brands":     data.get("brands", {}),
            "categories": data.get("categories", {}),
            "item_types": data.get("item_types", {}),
        }
    except Exception:
        return {"brands": {}, "categories": {}, "item_types": {}}


def _save(data: dict[str, dict[str, str]]) -> None:
    _ALIAS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _ALIAS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Public lookups ────────────────────────────────────────────────────────────

def lookup_brand(ai_brand: str) -> str | None:
    """Return corrected brand for ai_brand, or None."""
    data = _load()
    return data["brands"].get(_norm(ai_brand))


def lookup_category(ai_category: str) -> str | None:
    """Return corrected category for ai_category, or None."""
    data = _load()
    return data["categories"].get(_norm(ai_category))


def lookup_item_type(ai_item_type: str) -> str | None:
    """Return corrected item_type for ai_item_type, or None."""
    data = _load()
    return data["item_types"].get(_norm(ai_item_type))


# ── Public saves ──────────────────────────────────────────────────────────────

def save_brand_alias(ai_brand: str, corrected: str) -> None:
    data = _load()
    data["brands"][_norm(ai_brand)] = corrected
    _save(data)


def save_category_alias(ai_category: str, corrected: str) -> None:
    data = _load()
    data["categories"][_norm(ai_category)] = corrected
    _save(data)


def save_item_type_alias(ai_item_type: str, corrected: str) -> None:
    data = _load()
    data["item_types"][_norm(ai_item_type)] = corrected
    _save(data)
