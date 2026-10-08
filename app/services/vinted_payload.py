"""What the phone app needs to fill Vinted's sell form for one listing.

Same mappings as the desktop robot (app/draft_creator.py) so both fill the form the same
way: category path, Vinted condition label, colour labels, material names, parcel size.
Photos are included as data URLs because the Vinted page can't fetch from our server.
"""
from __future__ import annotations

import base64
import re
from pathlib import Path

from app.services.category_validator import CATEGORY_NAV, resolve_category_key

PHOTO_ORDER = ("front", "back", "brand", "model_size", "material")
VINTED_MAX_BYTES = 8 * 1024 * 1024


def condition_label(summary: str | None) -> str:
    lower = (summary or "").lower()
    if "new with tag" in lower or ("brand new" in lower and "tag" in lower):
        return "New with tags"
    if "new without" in lower:
        return "New without tags"
    if any(k in lower for k in ("very good", "excellent", "barely worn", "hardly worn")):
        return "Very good"
    if any(k in lower for k in ("satisfactory", "fair", "worn")):
        return "Satisfactory"
    return "Very good"


CONDITION_ID = {"New with tags": 6, "New without tags": 1, "Very good": 2, "Good": 3, "Satisfactory": 4}


def package_size(item_type: str | None) -> int:
    """1 = small, 2 = medium, 3 = large (same rules as the desktop robot)."""
    lower = (item_type or "").lower()
    if ("coat" in lower and "raincoat" not in lower) or any(
            k in lower for k in ("parka", "trench", "wax", "overcoat", "anorak", "ski jacket")):
        return 3
    if any(k in lower for k in ("trouser", "jean", "jogger", "sweatpant", "track pant", "short", "chino", "cargo",
                                "jumper", "sweater", "sweatshirt", "hoodie", "knitwear", "cardigan", "shoe", "boot",
                                "trainer", "sneaker", "loafer", "blazer", "jacket", "suit", "waistcoat", "gilet",
                                "raincoat")):
        return 2
    return 1


def colour_label(colour: str | None) -> str | None:
    if not colour:
        return None
    try:
        from app.draft_creator import COLOUR_MAP
    except Exception:
        return None
    lower = colour.lower()
    for keyword in sorted(COLOUR_MAP, key=len, reverse=True):
        if keyword in lower:
            return COLOUR_MAP[keyword]
    return None


def material_names(materials: list[str] | None) -> list[str]:
    names = []
    for item in materials or []:
        name = re.sub(r"^\d+%\s*", "", str(item)).strip().lower()
        if name:
            names.append(name.split()[0])
    return names


def photos(folder: Path) -> list[dict]:
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
             and not p.name.startswith("_")]

    def order(p: Path):
        stem = p.stem
        return (PHOTO_ORDER.index(stem) if stem in PHOTO_ORDER else len(PHOTO_ORDER), p.name)

    out = []
    for path in sorted(files, key=order):
        data = path.read_bytes()
        if len(data) > VINTED_MAX_BYTES:
            continue  # app photos are resized to 2048px, so this is only a safety net
        mime = "image/png" if path.suffix.lower() == ".png" else "image/webp" if path.suffix.lower() == ".webp" else "image/jpeg"
        out.append({"name": path.name, "data_url": f"data:{mime};base64," + base64.b64encode(data).decode()})
    return out


def build(listing: dict, folder: Path) -> dict:
    key = resolve_category_key(listing.get("category") or "", listing.get("style"))
    condition = condition_label(listing.get("condition_summary"))
    return {
        "folder": folder.name,
        "title": listing.get("title") or "",
        "description": listing.get("description") or "",
        "price": str(listing.get("price_gbp") or ""),
        "brand": listing.get("brand") or "",
        "size": listing.get("normalized_size") or listing.get("tagged_size") or "",
        "condition": condition,
        "condition_id": CONDITION_ID[condition],
        "colours": [c for c in (colour_label(listing.get("colour")), colour_label(listing.get("colour_secondary"))) if c],
        "materials": material_names(listing.get("materials")),
        "category_path": list(CATEGORY_NAV.get(key, [])) if key else [],
        "package": package_size(listing.get("item_type")),
        "photos": photos(folder),
    }
