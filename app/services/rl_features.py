"""
Ralph Lauren feature detection.

Pure functions — no I/O, no AI, no side effects.

Detects RL-specific features from existing listing fields and returns a feature
dict used by pricing.py to apply brand-specific price adjustments.
"""
from __future__ import annotations


# Sub-brand phrases that identify RL items (lowercased for matching).
_RL_BRAND_TOKENS = (
    "ralph lauren",
    "polo ralph lauren",
    "polo by ralph lauren",
    "lauren ralph lauren",
    "lauren by ralph lauren",
    "ralph lauren purple label",
    "rlx ralph lauren",
    "rlx",
    "double rl",
    "rrl",
)


def _is_rl_brand(brand: str) -> bool:
    b = brand.lower().strip()
    return any(tok in b for tok in _RL_BRAND_TOKENS)


def _rl_line(brand: str) -> str | None:
    """Identify the RL sub-line from the brand string."""
    b = brand.lower().strip()
    if "purple label" in b:
        return "purple_label"
    if "lauren ralph lauren" in b or "lauren by ralph lauren" in b:
        return "lauren"
    if "polo ralph lauren" in b or "polo by ralph lauren" in b:
        return "polo"
    if "rlx" in b:
        return "rlx"
    if "double rl" in b or b == "rrl":
        return "rrl"
    # plain "ralph lauren" — line unspecified
    return None


def detect_rl_features(listing: dict) -> dict | None:
    """Return a feature dict for Ralph Lauren items, or None for non-RL brands.

    Detection uses only existing listing fields — no AI calls.

    Returned dict fields:
        rl_line         str | None  — "polo"|"lauren"|"purple_label"|"rlx"|"rrl"|None
        rl_logo_size    str | None  — "big"|"small"|None
        rl_embroidery   bool
        rl_fabric_type  str | None  — "terry"|None

    Returns None if brand is not a Ralph Lauren brand.
    """
    brand = (listing.get("brand") or "").strip()
    if not brand or not _is_rl_brand(brand):
        return None

    # Build a searchable haystack from soft-text fields
    kws = " ".join(listing.get("tag_keywords") or [])
    title = listing.get("title") or ""
    desc = listing.get("description") or ""
    haystack = f"{kws} {title} {desc}".lower()

    # Logo size
    rl_logo_size: str | None = None
    if "big pony" in haystack or "large pony" in haystack:
        rl_logo_size = "big"
    elif "small pony" in haystack:
        rl_logo_size = "small"

    # Embroidery
    rl_embroidery: bool = "embroid" in haystack

    # Fabric type — check materials list first, then haystack
    materials_str = " ".join(listing.get("materials") or []).lower()
    rl_fabric_type: str | None = None
    if "terry" in materials_str or "towelling" in materials_str:
        rl_fabric_type = "terry"
    elif "terry" in haystack or "towelling" in haystack:
        rl_fabric_type = "terry"

    return {
        "rl_line": _rl_line(brand),
        "rl_logo_size": rl_logo_size,
        "rl_embroidery": rl_embroidery,
        "rl_fabric_type": rl_fabric_type,
    }
