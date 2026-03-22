"""
Premium fabric mill recognition and cloth-label parsing.

Handles:
- Fuzzy OCR normalisation of fabric_mill names (token-based, no external libs)
- Known cloth line → material hint mapping (e.g. Zealander Dream → New Zealand Merino Wool)
- Scanning all result fields for missed mill signals

Garment brand is NEVER modified here.
"""
from __future__ import annotations

# ── Canonical mill names ──────────────────────────────────────────────────────
# Keys must be lowercase
_CANONICAL_MILLS: dict[str, str] = {
    "loro piana":                    "Loro Piana",
    "vitale barberis canonico":      "Vitale Barberis Canonico",
    "vbc":                           "Vitale Barberis Canonico",
    "dormeuil":                      "Dormeuil",
    "holland & sherry":              "Holland & Sherry",
    "holland and sherry":            "Holland & Sherry",
    "h&s":                           "Holland & Sherry",
    "scabal":                        "Scabal",
    "drago":                         "Drago",
    "reda":                          "Reda",
    "lanificio":                     "Lanificio",
    "tessuti sondrio":               "Tessuti Sondrio",
    "cerruti":                       "Cerruti 1881",
    "lanificio f.lli cerruti":       "Cerruti 1881",
    "f.lli cerruti":                 "Cerruti 1881",
    "fratelli tallia di delfino":    "Fratelli Tallia di Delfino",
    "tallia di delfino":             "Fratelli Tallia di Delfino",
    "zignone":                       "Zignone",
    "thomas mason":                  "Thomas Mason",
    "albini":                        "Albini",
    "canclini":                      "Canclini",
    "drapers":                       "Drapers",
    "ermenegildo zegna fabric":      "Ermenegildo Zegna Fabric",
    "zegna fabric":                  "Ermenegildo Zegna Fabric",
}

# OCR-noise aliases — common misreads → canonical lowercase key
_OCR_ALIASES: dict[str, str] = {
    # Loro Piana variants
    "loro plana":            "loro piana",
    "loro plana fabric":     "loro piana",
    "lore piana":            "loro piana",
    "loro piana fabric":     "loro piana",
    "loropiana":             "loro piana",
    # VBC variants
    "vitale barberl5 canonico": "vitale barberis canonico",
    "vitale barberis":          "vitale barberis canonico",
    "vitale barbarls canonico": "vitale barberis canonico",
    "vltale barberis canonico": "vitale barberis canonico",
    "v.b.c":                    "vbc",
    # Holland & Sherry variants
    "holland & sheny":       "holland & sherry",
    "holland sherry":        "holland & sherry",
    # Cerruti variants
    "cerrutil 1881":         "cerruti",
    "cerrut1":               "cerruti",
    # Lanificio variants
    "laniflcio":             "lanificio",
    "laniflcio":             "lanificio",
}

# ── Cloth line → material hint ────────────────────────────────────────────────
# Maps lowercase cloth line name → human-readable material hint
_CLOTH_LINE_HINTS: dict[str, str] = {
    # Loro Piana
    "zealander dream":   "Pure New Zealand Merino Wool",
    "guanashina":        "Vicuña-cashmere blend",
    "trofeo":            "Super 130s Merino Wool",
    "wish":              "Cashmere and Silk blend",
    "storm system":      "Merino Wool with weatherproof treatment",
    "tasmanian":         "Super Fine Tasmanian Merino Wool",  # Dormeuil line too
    "gift of kings":     "100% Cashmere",
    "seta royale":       "Silk and Cashmere blend",
    # VBC
    "vbc platinum":      "Super 150s Merino Wool",
    "vbc gold":          "Super 130s Merino Wool",
    # Dormeuil
    "amadeus":           "Super 150s Merino Wool",
    "escorial":          "Escorial Wool",
    # Scabal
    "gold label":        "Super 150s Merino Wool",
    "genesis":           "Super 120s Merino Wool",
}

# ── Mill → fallback material hint when no cloth line is known ─────────────────
_MILL_FALLBACK_HINTS: dict[str, str] = {
    "loro piana":                 "Premium Italian Wool",
    "vitale barberis canonico":   "Super 100s–130s Italian Wool",
    "dormeuil":                   "British Luxury Wool",
    "holland & sherry":           "British Luxury Tweed or Wool",
    "scabal":                     "Super 120s–150s Merino Wool",
    "drago":                      "Italian Merino Wool",
    "reda":                       "Italian Merino Wool",
    "cerruti 1881":               "Italian Merino Wool",
    "fratelli tallia di delfino": "Italian Super 100s Wool",
    "zignone":                    "Italian Luxury Wool",
}


# ── Public API ────────────────────────────────────────────────────────────────

def normalise_mill(raw: str | None) -> str | None:
    """Fuzzy-normalise an OCR-noisy fabric_mill string to a canonical name.

    Tries in order:
    1. Exact alias match (after strip+lower)
    2. Canonical key match
    3. Token-based partial match (both strings share ≥1 distinctive token)

    Returns canonical mill name or None if raw is empty / unrecognised.
    Garment brand is never touched.
    """
    if not raw:
        return None
    low = raw.strip().lower()

    # 1. OCR alias exact match
    if low in _OCR_ALIASES:
        canonical_key = _OCR_ALIASES[low]
        return _CANONICAL_MILLS.get(canonical_key, raw)

    # 2. Canonical key exact match
    if low in _CANONICAL_MILLS:
        return _CANONICAL_MILLS[low]

    # 3. Token-based match — check if all tokens of any canonical key appear in raw
    raw_tokens = set(low.split())
    for key, canonical in _CANONICAL_MILLS.items():
        key_tokens = set(key.split())
        # Short keys (1-2 tokens) need exact inclusion; longer keys need ≥2 token match
        min_match = 1 if len(key_tokens) <= 2 else 2
        if len(key_tokens & raw_tokens) >= min_match and len(key_tokens) >= 2:
            return canonical

    # 4. Substring match for multi-word mills
    for key, canonical in _CANONICAL_MILLS.items():
        if key in low or low in key:
            return canonical

    # Not recognised — return the raw value cleaned of trailing generic words
    return raw.strip()


def infer_material_hint(
    fabric_mill: str | None,
    fabric_line: str | None,
    existing_materials: list[str],
) -> str | None:
    """Return a descriptive material hint for cloth labels.

    Uses cloth line first, then mill fallback.
    Returns None if materials list already has enough useful info (≥1 entry
    that looks like a composition line with percentages).
    """
    # Don't add a hint if composition is already well-described
    has_composition = any(
        "%" in m for m in (existing_materials or [])
    )
    if has_composition:
        return None

    if fabric_line:
        hint = _CLOTH_LINE_HINTS.get(fabric_line.strip().lower())
        if hint:
            return hint

    if fabric_mill:
        mill_key = normalise_mill(fabric_mill)
        if mill_key:
            hint = _MILL_FALLBACK_HINTS.get(mill_key.lower())
            if hint:
                return hint

    return None


def scan_for_mill(result: dict) -> dict:
    """Scan all result fields for overlooked mill signals and patch result in-place.

    Checks:
    - Normalises existing fabric_mill if set
    - Scans materials list for entries that are actually mill names (moves them)
    - Scans tag_keywords for mill names missed by the main extraction
    - Infers material_hint if not already set

    Returns the modified result dict.
    """
    # Normalise existing fabric_mill
    raw_mill = result.get("fabric_mill")
    if raw_mill:
        normalised = normalise_mill(raw_mill)
        if normalised:
            result["fabric_mill"] = normalised

    # Scan materials list — if any entry is a known mill name, move it to fabric_mill
    _canonical_lower = {v.lower() for v in _CANONICAL_MILLS.values()}
    mats = list(result.get("materials") or [])
    kept_mats = []
    for m in mats:
        candidate = normalise_mill(m)
        # Move if it resolves to a canonical mill AND has no fibre-like content
        is_known_mill = (candidate is not None
                         and candidate.lower() in _canonical_lower)
        has_fibre = any(fibre in m.lower() for fibre in _FIBRE_WORDS)
        if is_known_mill and not has_fibre:
            if not result.get("fabric_mill"):
                result["fabric_mill"] = candidate
        else:
            kept_mats.append(m)
    result["materials"] = kept_mats

    # Scan tag_keywords for mill signals
    if not result.get("fabric_mill"):
        for kw in (result.get("tag_keywords") or []):
            candidate = normalise_mill(kw)
            if candidate and candidate.lower() in {k.lower() for k in _CANONICAL_MILLS.values()}:
                result["fabric_mill"] = candidate
                break

    # Infer material_hint from mill + cloth line
    if not result.get("material_hint"):
        hint = infer_material_hint(
            result.get("fabric_mill"),
            result.get("fabric_line"),
            result.get("materials") or [],
        )
        if hint:
            result["material_hint"] = hint

    return result


# ── Internal helpers ──────────────────────────────────────────────────────────

_FIBRE_WORDS = frozenset({
    "wool", "merino", "cashmere", "cotton", "linen", "silk", "polyester",
    "viscose", "elastane", "nylon", "acrylic", "modal", "lyocell", "alpaca",
    "mohair", "angora", "leather", "suede", "polyamide", "lambswool",
})
