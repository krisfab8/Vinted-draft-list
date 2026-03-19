"""
Listing writer: takes extractor output and generates a complete Vinted listing.

Uses Claude Haiku 4.5 with prompts from prompts/ directory.
Validates output against listing.schema.json before returning.
"""
import json
import re
from datetime import date
from pathlib import Path

import anthropic

from app.config import ANTHROPIC_API_KEY, ENABLE_CATEGORY_ITEM_TYPE_SLICE, ENABLE_PRICE_MEMORY, HAIKU_MODEL, PROMPTS_DIR
from app.validate_listing import validate_or_raise

# EU/Italian → UK chest size (subtract 10). Used for suits, blazers, tailoring.
_EU_TO_UK: dict[int, int] = {eu: eu - 10 for eu in range(40, 70, 2)}

_TAILORING_KEYWORDS = {"blazer", "suit jacket", "sports jacket", "sport jacket", "jacket suit"}


def _convert_eu_suit_size(listing: dict) -> dict:
    """Convert bare EU tagged_size to UK size (e.g. 54 → 44R) for tailoring items.
    If the size already has a R/L/S suffix it is already in UK format — leave it alone."""
    item_type = (listing.get("item_type") or "").lower()
    if not any(k in item_type for k in _TAILORING_KEYWORDS):
        return listing

    raw_size = str(listing.get("tagged_size") or "").strip()
    # Only convert BARE two-digit numbers (e.g. "54"). If it already has a suffix
    # like "44R" it is a UK chest size — do not subtract 10.
    m = re.match(r"^(\d{2})$", raw_size)
    if not m:
        return listing

    eu_num = int(m.group(1))
    if eu_num not in _EU_TO_UK:
        return listing

    uk_size = f"{_EU_TO_UK[eu_num]}R"
    listing["tagged_size"] = uk_size
    listing["normalized_size"] = uk_size

    title = listing.get("title", "")
    if raw_size in title:
        listing["title"] = title.replace(raw_size, uk_size, 1)

    return listing


# EU → UK shoe size lookup. Source: standard conversion table.
_EU_TO_UK_SHOE: dict[int, int] = {
    35: 2, 36: 3, 37: 4, 38: 5, 39: 6, 40: 6, 41: 7, 42: 8,
    43: 9, 44: 10, 45: 10, 46: 11, 47: 12, 48: 13,
}

_SHOE_KEYWORDS = {
    "boot", "boots", "shoe", "shoes", "trainer", "trainers", "sneaker", "sneakers",
    "loafer", "loafers", "brogue", "brogues", "oxford", "derby", "heel", "heels",
    "sandal", "sandals", "slipper", "slippers", "mule", "mules", "court",
    "plimsoll", "plimsolls", "espadrille", "espadrilles", "flip flop",
}


def _is_shoe_item(item_type: str) -> bool:
    item_lower = item_type.lower()
    return any(k in item_lower for k in _SHOE_KEYWORDS)


def _convert_eu_shoe_size(listing: dict) -> dict:
    """If a shoe item has a bare EU size, convert to UK and store in normalized_size.

    tagged_size is never modified — it stays exactly as extracted.
    Only acts when: item is footwear AND size is a plain integer in EU range (35–48)
    AND the tag didn't already include a UK number (extractor would have picked that up).
    """
    item_type = (listing.get("item_type") or "").lower()
    if not _is_shoe_item(item_type):
        return listing

    raw = str(listing.get("tagged_size") or "").strip()
    m = re.match(r"^(\d{2})$", raw)
    if not m:
        return listing

    eu_num = int(m.group(1))
    uk_num = _EU_TO_UK_SHOE.get(eu_num)
    if uk_num is None:
        return listing

    listing["normalized_size"] = str(uk_num)

    # Update title: replace bare EU number with "UK {uk_num}"
    title = listing.get("title", "")
    if raw in title:
        listing["title"] = title.replace(raw, f"UK {uk_num}", 1)

    return listing

# ---------------------------------------------------------------------------
# Category rules item-type slicing (Step 2: ENABLE_CATEGORY_ITEM_TYPE_SLICE)
# Maps left-hand side of category_rules.md lines (normalised) → group name.
# ---------------------------------------------------------------------------

_CATEGORY_LINE_GROUPS: dict[str, str] = {
    # tailoring
    "blazer": "tailoring", "suit jacket": "tailoring", "sports jacket": "tailoring",
    # outerwear — coats
    "overcoat": "outerwear", "wax jacket": "outerwear", "wool coat": "outerwear",
    "trench coat": "outerwear", "parka": "outerwear", "peacoat": "outerwear",
    "raincoat": "outerwear", "duffle coat": "outerwear",
    # outerwear — jackets
    "chore jacket": "outerwear", "denim jacket": "outerwear", "overshirt": "outerwear",
    "bomber jacket": "outerwear", "fleece jacket": "outerwear",
    "harrington jacket": "outerwear", "puffer jacket": "outerwear",
    "quilted jacket": "outerwear", "gilet": "outerwear",
    # knitwear & sweatshirts
    "lambswool jumper": "knitwear", "merino jumper": "knitwear",
    "crewneck sweatshirt": "knitwear", "hoodie": "knitwear",
    # shirts & tops
    "flannel shirt": "shirts_tops", "oxford shirt": "shirts_tops",
    "polo shirt": "shirts_tops", "t-shirt": "shirts_tops", "shirt / blouse": "shirts_tops",
    # trousers (non-jeans)
    "corduroy trousers": "trousers", "chino trousers": "trousers",
    "track pants": "trousers", "joggers": "trousers", "sweatpants": "trousers",
    "leggings": "trousers",
    # jeans
    "slim fit jeans": "jeans", "skinny jeans": "jeans", "straight fit jeans": "jeans",
    "ripped jeans": "jeans", "jeans": "jeans",
    "straight jeans": "jeans", "boyfriend jeans": "jeans", "cropped jeans": "jeans",
    "flared jeans": "jeans", "high waisted jeans": "jeans",
    # shoes
    "walking boots": "shoes", "chelsea boots": "shoes", "brogue shoes": "shoes",
    "loafers": "shoes", "ankle boots": "shoes", "knee boots": "shoes",
    "trainers": "shoes", "sneakers": "shoes", "oxford shoes": "shoes",
    "derby shoes": "shoes", "court shoes": "shoes", "heels": "shoes",
    "sandals": "shoes", "slippers": "shoes", "mules": "shoes",
    # dresses
    "midi dress": "dresses", "maxi dress": "dresses", "mini dress": "dresses",
    # skirts
    "mini skirt": "skirts", "midi skirt": "skirts", "maxi skirt": "skirts", "skirt": "skirts",
}

# Maps extracted item_type keywords (lowercase) → group.
# Checked longest-match-first so "wax jacket" beats bare "jacket".
_ITEM_TYPE_TO_GROUP: dict[str, str] = {
    # tailoring — most specific first
    "blazer": "tailoring", "suit jacket": "tailoring", "sports jacket": "tailoring",
    "suit": "tailoring",
    # outerwear — specific
    "wax jacket": "outerwear", "wool coat": "outerwear", "trench coat": "outerwear",
    "duffle coat": "outerwear", "chore jacket": "outerwear", "denim jacket": "outerwear",
    "overshirt": "outerwear", "bomber jacket": "outerwear", "fleece jacket": "outerwear",
    "harrington jacket": "outerwear", "puffer jacket": "outerwear",
    "quilted jacket": "outerwear", "overcoat": "outerwear", "parka": "outerwear",
    "peacoat": "outerwear", "raincoat": "outerwear", "duffle": "outerwear",
    "bomber": "outerwear", "harrington": "outerwear", "gilet": "outerwear",
    # outerwear — generic (must come after specific)
    "jacket": "outerwear", "coat": "outerwear",
    # knitwear — specific
    "lambswool jumper": "knitwear", "merino jumper": "knitwear",
    "crewneck sweatshirt": "knitwear",
    # knitwear — generic
    "hoodie": "knitwear", "jumper": "knitwear", "sweater": "knitwear",
    "knitwear": "knitwear", "pullover": "knitwear", "sweatshirt": "knitwear",
    # shirts/tops — specific
    "flannel shirt": "shirts_tops", "oxford shirt": "shirts_tops",
    "polo shirt": "shirts_tops", "t-shirt": "shirts_tops",
    # shirts/tops — generic
    "shirt": "shirts_tops", "blouse": "shirts_tops", "polo": "shirts_tops",
    "tshirt": "shirts_tops", "top": "shirts_tops",
    # trousers — specific
    "corduroy trousers": "trousers", "chino trousers": "trousers",
    "track pants": "trousers", "sweatpants": "trousers", "leggings": "trousers",
    # trousers — generic
    "trousers": "trousers", "trouser": "trousers", "joggers": "trousers",
    "chinos": "trousers",
    # jeans — specific
    "slim fit jeans": "jeans", "skinny jeans": "jeans", "straight jeans": "jeans",
    "ripped jeans": "jeans", "boyfriend jeans": "jeans", "cropped jeans": "jeans",
    "flared jeans": "jeans", "high waisted jeans": "jeans",
    # jeans — generic
    "jeans": "jeans",
    # shoes — specific first
    "walking boots": "shoes", "chelsea boots": "shoes", "brogue shoes": "shoes",
    "ankle boots": "shoes", "knee boots": "shoes", "wellington boots": "shoes",
    "desert boots": "shoes", "work boots": "shoes", "hiking boots": "shoes",
    "leather brogues": "shoes", "oxford shoes": "shoes", "derby shoes": "shoes",
    "court shoes": "shoes", "high heels": "shoes", "stilettos": "shoes",
    "ballet flats": "shoes", "mules": "shoes", "espadrilles": "shoes",
    "trainers": "shoes", "sneakers": "shoes", "running shoes": "shoes",
    "canvas shoes": "shoes", "plimsolls": "shoes",
    "sandals": "shoes", "flip flops": "shoes", "sliders": "shoes",
    "slippers": "shoes",
    # shoes — generic
    "loafers": "shoes", "boots": "shoes", "heels": "shoes", "shoes": "shoes",
    # dresses — specific
    "midi dress": "dresses", "maxi dress": "dresses", "mini dress": "dresses",
    # dresses — generic
    "dress": "dresses",
    # skirts — specific
    "mini skirt": "skirts", "midi skirt": "skirts", "maxi skirt": "skirts",
    # skirts — generic
    "skirt": "skirts",
}


def _resolve_item_type_group(item_type: str) -> str | None:
    """Map an extracted item_type to a category group.

    Uses longest-key substring match so more specific entries win over generic ones.
    Returns None if no match is found (caller falls back to gender-only slice).
    """
    if not item_type:
        return None
    item_lower = item_type.lower()

    # Exact match first
    if item_lower in _ITEM_TYPE_TO_GROUP:
        return _ITEM_TYPE_TO_GROUP[item_lower]

    # Longest substring match (prefer "wax jacket" over "jacket")
    best_key = ""
    best_group: str | None = None
    for key, group in _ITEM_TYPE_TO_GROUP.items():
        if key in item_lower and len(key) > len(best_key):
            best_key = key
            best_group = group

    return best_group


def _filter_category_by_group(rules_text: str, group: str) -> str:
    """Filter category rules lines to only those belonging to the given group.

    Always keeps: section headers (lines starting with #) and the # Notes section.
    Rule lines (containing ->) are kept only when their item type maps to `group`.
    """
    lines = rules_text.splitlines()
    result: list[str] = []
    in_notes = False

    for line in lines:
        stripped = line.strip()

        # Blank lines — keep for readability
        if not stripped:
            result.append(line)
            continue

        # Section headers
        if stripped.startswith("#"):
            if "Notes" in stripped:
                in_notes = True
            result.append(line)
            continue

        # Notes section: keep everything verbatim
        if in_notes:
            result.append(line)
            continue

        # Rule line: keep if item type key belongs to this group
        if "->" in stripped:
            item_key = stripped.split("->")[0].strip().lower()
            if _CATEGORY_LINE_GROUPS.get(item_key) == group:
                result.append(line)

    # Collapse consecutive blank lines to single blank
    final: list[str] = []
    prev_blank = False
    for line in result:
        is_blank = not line.strip()
        if is_blank and prev_blank:
            continue
        final.append(line)
        prev_blank = is_blank

    return "\n".join(final).strip()


_SYSTEM = """
You are writing concise, honest Vinted resale listings for second-hand clothing.
Follow the style guide and category rules exactly.
Return only a valid JSON object — no markdown, no explanation.
""".strip()


def _slice_category_rules(gender: str, item_type: str = "") -> str:
    """Return the gender + item-type relevant section of category_rules.md.

    Step 1 — gender slice: drops the opposite-gender block (~half the file).
    Step 2 — item-type slice: if ENABLE_CATEGORY_ITEM_TYPE_SLICE and item_type is
              known, further filters to only rules for that item's group.
    Unisex items skip the gender step; unknown item types skip the item-type step.
    """
    full = (PROMPTS_DIR / "category_rules.md").read_text()
    g = (gender or "").lower()

    # Step 1: gender slice
    if "men" in g and "women" not in g:
        gender_sliced = re.sub(r"\n# Women's\n.*?(?=\n# |\Z)", "\n", full, flags=re.DOTALL).strip()
    elif "women" in g:
        gender_sliced = re.sub(r"\n# Men's\n.*?(?=\n# |\Z)", "\n", full, flags=re.DOTALL).strip()
    else:
        gender_sliced = full  # unisex — keep everything

    # Step 2: item-type slice (if enabled and item type can be classified)
    if item_type and ENABLE_CATEGORY_ITEM_TYPE_SLICE:
        group = _resolve_item_type_group(item_type)
        if group:
            return _filter_category_by_group(gender_sliced, group)

    return gender_sliced


def _get_category_slice_level(gender: str, item_type: str = "") -> str:
    """Return the slice level that _slice_category_rules would use.

    Returns one of: "full", "gender", "item_type".
    Used for observability logging.
    """
    g = (gender or "").lower()
    if "men" not in g and "women" not in g:
        return "full"  # unisex or unknown → no gender slice
    if item_type and ENABLE_CATEGORY_ITEM_TYPE_SLICE:
        group = _resolve_item_type_group(item_type)
        if group:
            return "item_type"
    return "gender"


# ---------------------------------------------------------------------------
# Price memory (Step 4: ENABLE_PRICE_MEMORY)
# Lightweight local lookup table injected as a hint into the listing prompt.
# Lookup priority: brand+item_type+material_group > brand+item_type > item_type+material_group > item_type
# ---------------------------------------------------------------------------

# Maps extracted material strings (lowercase fragments) → canonical material_group
_MATERIAL_GROUP_MAP: dict[str, str] = {
    "cashmere": "cashmere",
    "merino": "wool",
    "lambswool": "wool",
    "alpaca": "wool",
    "mohair": "wool",
    "angora": "wool",
    "wool": "wool",
    "tweed": "wool",
    "linen": "linen",
    "silk": "silk",
    "cotton": "cotton",
    "leather": "leather",
    "suede": "leather",
    "down": "down",
    "polyester": "synthetic",
    "nylon": "synthetic",
    "acrylic": "synthetic",
    "elastane": "synthetic",
    "spandex": "synthetic",
    "viscose": "synthetic",
    "modal": "synthetic",
    "lyocell": "synthetic",
}

# Lazy-loaded price memory index: maps (brand_lower|None, item_type_lower, material_group|None) → entry
_PRICE_MEMORY: list[dict] | None = None


def _load_price_memory() -> list[dict]:
    global _PRICE_MEMORY
    if _PRICE_MEMORY is None:
        pm_file = Path(__file__).parent.parent / "data" / "price_memory.json"
        if pm_file.exists():
            data = json.loads(pm_file.read_text())
            _PRICE_MEMORY = data.get("entries", [])
        else:
            _PRICE_MEMORY = []
    return _PRICE_MEMORY


def _classify_material_group(materials: list[str]) -> str | None:
    """Return the most premium material_group from the materials list.

    Priority order mirrors the material ranking in the prompt:
    cashmere > silk > wool variants > linen > leather > down > cotton > synthetic.
    """
    if not materials:
        return None
    materials_str = " ".join(materials).lower()
    # Check in priority order
    priority = ["cashmere", "silk", "wool", "linen", "leather", "down", "cotton", "synthetic"]
    for group in priority:
        # Find any fibre that maps to this group
        for fibre, mapped_group in _MATERIAL_GROUP_MAP.items():
            if mapped_group == group and fibre in materials_str:
                return group
    return None


def _lookup_price_memory(brand: str | None, item_type: str, materials: list[str]) -> dict | None:
    """Look up price memory for the given item.

    Priority:
      1. brand + item_type + material_group  (most specific)
      2. brand + item_type                   (material-agnostic)
      3. item_type + material_group          (no brand)
      4. item_type only                      (broadest fallback)

    Returns the matched entry dict with an added 'match_level' key, or None.
    """
    if not ENABLE_PRICE_MEMORY:
        return None

    entries = _load_price_memory()
    brand_lower = brand.strip().lower() if brand else None
    item_lower  = item_type.strip().lower() if item_type else ""
    mat_group   = _classify_material_group(materials)

    def _matches(e: dict, req_brand, req_item, req_mat) -> bool:
        # brand: None in entry means "any brand"
        b_ok = (e.get("brand") is None and req_brand is None) or \
               (e.get("brand") is not None and req_brand is not None and
                e["brand"].lower() == req_brand) or \
               (e.get("brand") is None and req_brand is None)
        b_ok = (e.get("brand") is None) or \
               (e.get("brand") is not None and req_brand is not None and
                e["brand"].lower() == req_brand)
        i_ok = e["item_type"].lower() == req_item
        m_ok = (e.get("material_group") is None) or \
               (e.get("material_group") is not None and req_mat is not None and
                e["material_group"] == req_mat)
        return b_ok and i_ok and m_ok

    # Priority 1: brand + item_type + material_group
    if brand_lower and mat_group:
        for e in entries:
            if (e.get("brand") is not None and e["brand"].lower() == brand_lower
                    and e["item_type"].lower() == item_lower
                    and e.get("material_group") == mat_group):
                return {**e, "match_level": "brand+item_type+material"}

    # Priority 2: brand + item_type (material_group is None in entry = material-agnostic)
    if brand_lower:
        for e in entries:
            if (e.get("brand") is not None and e["brand"].lower() == brand_lower
                    and e["item_type"].lower() == item_lower
                    and e.get("material_group") is None):
                return {**e, "match_level": "brand+item_type"}

    # Also try brand + item_type where material is irrelevant (any material_group entry wins too)
    if brand_lower:
        for e in entries:
            if (e.get("brand") is not None and e["brand"].lower() == brand_lower
                    and e["item_type"].lower() == item_lower):
                return {**e, "match_level": "brand+item_type"}

    # Priority 3: item_type + material_group (no brand)
    if mat_group:
        for e in entries:
            if (e.get("brand") is None
                    and e["item_type"].lower() == item_lower
                    and e.get("material_group") == mat_group):
                return {**e, "match_level": "item_type+material"}

    # Priority 4: item_type only (no brand, material_group is None)
    for e in entries:
        if (e.get("brand") is None
                and e["item_type"].lower() == item_lower
                and e.get("material_group") is None):
            return {**e, "match_level": "item_type"}

    return None


_GRAPHIC_ITEM_TYPES = {"graphic t-shirt", "graphic tee", "band tee", "band t-shirt",
                       "slogan tee", "slogan t-shirt", "printed t-shirt", "print tee"}
_TSHIRT_ITEM_TYPES  = {"t-shirt", "tee", "graphic t-shirt", "graphic tee", "band tee",
                       "band t-shirt", "slogan tee", "slogan t-shirt",
                       "printed t-shirt", "print tee"}

def _apply_top_style(listing: dict, extracted_pattern: str | None,
                     extracted_item_type: str | None) -> dict:
    """Deterministic post-processing: correct style for tops using pattern/item_type.

    Only acts when item_type is a T-shirt variant.  The LLM may still set style
    correctly; this enforces it as a hard rule so tests don't depend on LLM output.
    """
    item_type_lower = (extracted_item_type or "").lower().strip()
    if item_type_lower not in _TSHIRT_ITEM_TYPES:
        return listing

    pattern_lower = (extracted_pattern or "").lower().strip()
    # Graphic signal: pattern is "graphic" OR item_type is a known graphic variant
    if pattern_lower == "graphic" or item_type_lower in _GRAPHIC_ITEM_TYPES:
        listing["style"] = "Graphic"
        # Also strip " > Plain" from category so draft_creator picks up the Graphic nav path
        cat = listing.get("category") or ""
        if cat.lower().endswith(" > plain"):
            listing["category"] = cat[:cat.lower().rfind(" > plain")]
    elif pattern_lower == "plain" and listing.get("style") is None:
        # Only fill Plain if LLM left style unset — don't override an explicit LLM value
        listing["style"] = "Plain"
    return listing


def _escape_json_strings(s: str) -> str:
    """Escape bare control characters (\\n, \\r, \\t) that appear inside JSON string
    values.  Claude occasionally outputs multi-line description text with literal
    newlines rather than \\\\n escapes, which makes the JSON unparseable."""
    result: list[str] = []
    in_string = False
    escape_next = False
    for ch in s:
        if escape_next:
            result.append(ch)
            escape_next = False
        elif ch == "\\":
            result.append(ch)
            escape_next = True
        elif ch == '"':
            result.append(ch)
            in_string = not in_string
        elif in_string and ch == "\n":
            result.append("\\n")
        elif in_string and ch == "\r":
            result.append("\\r")
        elif in_string and ch == "\t":
            result.append("\\t")
        else:
            result.append(ch)
    return "".join(result)


def _build_prompt(item: dict, hints: dict | None = None) -> str:
    style = (PROMPTS_DIR / "listing_style.md").read_text()
    categories = _slice_category_rules(item.get("gender", ""), item.get("item_type", ""))
    pricing = (PROMPTS_DIR / "pricing_rules.md").read_text()

    premium_brands = {
        "barbour", "belstaff", "grenfell", "gloverall",
        "margaret howell", "brora", "john smedley",
        "suit supply", "suitsupply", "ermenegildo zegna", "zegna",
        "canali", "corneliani", "hackett", "paul smith",
    }
    brand_lower = (item.get("brand") or "").lower()
    is_premium = brand_lower in premium_brands

    hint_notes = []
    # model_name — put in description as "- Model: <name>" and append to title if space allows
    _model_name = item.get("model_name") or (hints and hints.get("model_name"))
    if _model_name:
        hint_notes.append(
            f"model_name '{_model_name}' is the confirmed model name — REQUIRED in BOTH title AND description. "
            f"In the description, include it as a bullet point formatted exactly as '- Model: {_model_name}' (not '{_model_name} style'). "
            f"In the title, append it at the END after the colour if the total stays under 70 chars "
            f"(e.g. 'Levi 501 Jeans Mens W32 L32 Blue {_model_name}'). If it would push the title over 70 chars, omit it from the title."
        )

    _cond = (item.get("condition_summary") or "").strip()
    if _cond.lower().startswith("new with tags"):
        hint_notes.append(
            "CONDITION: This item is BRAND NEW WITH TAGS. "
            "condition_summary MUST be 'New with tags — original labels attached.' "
            "The description condition line MUST use this exact phrase — do NOT use 'used condition'."
        )
    elif _cond.lower().startswith("new without tags"):
        hint_notes.append(
            "CONDITION: This item is NEW WITHOUT TAGS (unworn). "
            "condition_summary MUST be 'New without tags — unworn, no original tags.' "
            "Do NOT use 'used condition'."
        )
    elif _cond:
        # Locked used condition — AI must never change the level the user set
        _cond_level = _cond.split(" — ")[0].strip()  # e.g. "Very good used condition"
        hint_notes.append(
            f"CONDITION LOCKED: condition_summary is '{_cond}' — copy it EXACTLY, do not change the level. "
            f"The description must open with '{_cond_level}' — not 'Excellent', 'Good', or any other level."
        )

    item_type_lower = (item.get("item_type") or "").lower()
    is_shoe = _is_shoe_item(item_type_lower)
    _ACTIVEWEAR = ("jogger", "sweatpant", "tracksuit", "legging", "activewear", "gym pant", "track pant", "trackpant", "track suit")
    is_activewear = not is_shoe and any(k in item_type_lower for k in _ACTIVEWEAR)
    is_trouser = not is_shoe and (is_activewear or any(k in item_type_lower for k in ("trouser", "jeans", "shorts", "chino", "cargo")))
    w = item.get("trouser_waist")
    l = item.get("trouser_length")
    if is_activewear:
        # Activewear (joggers, sweatpants, tracksuits, leggings): S/M/L/XL is the primary size.
        # W measurement appears at the end of the title and as a description bullet.
        size_rule = (
            "ACTIVEWEAR SIZING: normalized_size and SIZE in title MUST be the letter size "
            "(S, M, L, XL) — never W/L as the main size. "
        )
        if w and l:
            size_rule += (
                f"ALSO: append 'W{w}' at the very end of the title after the colour "
                f"(e.g. '... Blue W{w}'). Only omit if this pushes the title over 70 chars. "
                f"In the description, add a bullet point: '- Approx W{w} L{l} (waist/length).'"
            )
        elif w:
            size_rule += (
                f"ALSO: append 'W{w}' at the very end of the title if space allows. "
                f"In the description, add a bullet point: '- Approx waist W{w}.'"
            )
        hint_notes.append(size_rule)
    elif is_trouser:
        if w and l:
            hint_notes.append(
                f"REQUIRED: This is a trouser/shorts item. The size MUST be 'W{w} L{l}' in the title, tagged_size, and normalized_size. "
                f"Buyers search by W/L — a bare EU number like '52' is NOT acceptable for trousers. "
                f"Also add a bullet point in the description: '- W{w} L{l} (waist/length).'"
            )
        elif w:
            hint_notes.append(f"This is a trouser item. Waist is W{w}. Use 'W{w}' as the size. Length is unknown — do not fabricate one.")
        else:
            hint_notes.append("This is a trouser/shorts item. The W/L size is not known yet — use 'TBC' as normalized_size and add 'trouser_waist' and 'trouser_length' to low_confidence_fields.")

    if is_shoe:
        # Title format for footwear: Brand + Model (if known) + Colour + Type + UK Size
        # e.g. "Nike Air Force 1 White Trainers UK 9" or "Loake Chelsea Boots Tan Leather UK 9"
        _shoe_size = item.get("normalized_size") or item.get("tagged_size") or ""
        # Check if size looks like EU (bare integer in 35–48 range)
        _shoe_size_note = ""
        try:
            _sz_int = int(_shoe_size)
            if 35 <= _sz_int <= 48:
                _uk = _EU_TO_UK_SHOE.get(_sz_int)
                _shoe_size_note = (
                    f" The extracted size {_shoe_size} looks like an EU size. "
                    f"{'Convert to UK ' + str(_uk) + ' and ' if _uk else ''}"
                    f"show as 'UK {_uk or _shoe_size}' in the title."
                )
        except (ValueError, TypeError):
            if _shoe_size:
                _shoe_size_note = f" Show size as 'UK {_shoe_size}' in the title."
        hint_notes.append(
            f"SHOE ITEM: Title format is Brand + Model (if clearly printed on tag) + Colour + Type + UK Size. "
            f"Example: 'Nike Air Force 1 White Trainers UK 9' or 'Loake Chelsea Boots Tan UK 9'."
            f"{_shoe_size_note} "
            f"Do NOT use W/L format. Do NOT set trouser_waist or trouser_length. "
            f"For condition: note sole wear, creasing on the upper, scuffs, or heel wear if visible in photos. "
            f"If soles look unworn, note that in condition_summary as a positive."
        )

    if hints and hints.get("item_type"):
        hint_notes.append(f"Item type is confirmed as '{hints['item_type']}' — use this exact term as the item_type and include it prominently in the title and description (e.g. instead of 'Track Pants' use '{hints['item_type']}').")
    if hints and hints.get("brand"):
        hint_notes.append(f"Brand is confirmed as '{hints['brand']}' — use exactly this, do not change it.")
    if hints and hints.get("size"):
        if is_activewear:
            _w_suffix_note = (
                f" The letter size is the MAIN size — do NOT use W/L as the size. "
                f"W{w} still goes as a suffix at the END of the title (see ACTIVEWEAR SIZING note above)."
            ) if w else " The letter size is the MAIN size — do NOT use W/L as the size."
            hint_notes.append(f"Size is confirmed as '{hints['size']}' — use EXACTLY this as normalized_size and in the title.{_w_suffix_note}")
        else:
            hint_notes.append(f"Size is confirmed as '{hints['size']}' — use EXACTLY this in the title, tagged_size, and normalized_size. Place it AFTER the item type and gender (Brand + ItemType + Mens/Womens + '{hints['size']}' + Colour). Do NOT drop or reorder it.")
    if hints and hints.get("made_in"):
        hint_notes.append(f"Made in is confirmed as '{hints['made_in']}' — set made_in to this value and include 'Made in {hints['made_in']}' in the description.")
    if hints and hints.get("damages"):
        hint_notes.append(f"User-reported damage: '{hints['damages']}' — include this in flaws_note and condition_summary.")

    # Price memory hint — inject as a soft hint, not a hard override
    _pm_entry = _lookup_price_memory(
        item.get("brand"),
        item.get("item_type", ""),
        item.get("materials") or [],
    )
    if _pm_entry:
        _pm_level = _pm_entry.get("match_level", "?")
        _pm_conf  = _pm_entry.get("confidence", "low")
        _pm_note  = (
            f"PRICE MEMORY HINT (match: {_pm_level}, confidence: {_pm_conf}): "
            f"Typical Vinted resale for this item is £{_pm_entry['typical']} "
            f"(range £{_pm_entry['low']}–£{_pm_entry['high']}). "
            "Use this as a reference band — adjust up/down based on condition, size, and market-first pricing rules. "
            "Do NOT use this price as a hard floor or ceiling; it is a hint only."
        )
        if _pm_entry.get("notes"):
            _pm_note += f" Note: {_pm_entry['notes']}"
        hint_notes.append(_pm_note)

    model_hint = ("\nNotes:\n" + "\n".join(f"- {h}" for h in hint_notes)) if hint_notes else ""

    return f"""
# Style Guide
{style}

# Category Rules
{categories}

# Pricing Rules
{pricing}

# Extracted Item Data
{json.dumps(item, indent=2)}

# Task
Write a complete listing JSON with these fields:
- brand (string or null)
- item_type (string)
- title (string, max 70 chars, REQUIRED order: Brand + ItemType + Mens/Womens + Size + Colour + [Material if premium fibre] — follow style guide exactly, include item synonym, no filler words. NEVER reorder these elements. For trousers/shorts/joggers: Size MUST be W/L format e.g. "W32 L32")
- description (string, follow style guide format)
- tagged_size (string — copy EXACTLY from extracted tagged_size, do not convert)
- normalized_size (string — for trousers/jeans/shorts: MUST be W/L format e.g. 'W32 L32'. For suits/blazers: keep number as-is. For S/M/L/XL: keep as-is.)
- materials (array of strings — copy EXACTLY from extracted materials. Normalize spelling only: capitalize first letter, fix obvious OCR typos e.g. "Labswool" → "Lambswool". NEVER change percentages, NEVER add fibres, NEVER remove fibres, NEVER merge lines. One entry per fibre.)
- colour (string)
- colour_secondary (string or null — copy from extracted colour_secondary)
- style (string or null — the Vinted sub-genre key. For men's t-shirts: one of Plain / Graphic / Long-sleeve. IMPORTANT: if extracted pattern is "Graphic" or item_type contains "graphic", "band tee", "slogan", or "printed", set style to "Graphic". Use "Plain" ONLY if pattern is "Plain" AND item_type has no graphic/print signal. For men's jeans: one of Slim / Straight / Skinny / Ripped (only these 4 exist on Vinted UK). For women's jeans: one of Straight / Skinny / Boyfriend / Cropped / Flared / High waisted / Ripped. For jackets: one of Denim / Bomber / Biker / Field / Fleece / Harrington / Puffer / Quilted / Shacket / Varsity / Windbreaker. For coats: one of Overcoat / Trench / Parka / Peacoat / Raincoat / Duffle. For men's boots: one of Chelsea / Desert / Wellington / Work. For women's boots: one of Ankle / Knee. Copy from extracted style if present; otherwise infer from item_type, model_name, cut, tag_keywords, pattern. Null only if genuinely cannot determine.)
- cut (string or null — copy from extracted cut if present, e.g. "Slim", "Classic")
- pattern (string or null — copy from extracted pattern, e.g. "Pinstripe", "Plain")
- tag_keywords (array — copy from extraction)
- tag_keywords_confidence (string or null — copy from extraction: "high" or "low")
- gender ("men's" | "women's" | "unisex")
- price_gbp (number — use pricing rules, assume buy_price_gbp if provided)
- category (string — use category rules to determine path. Use the BASE category only (e.g. "Men > Jeans", "Men > Coats", "Women > Jackets") — the style field drives the sub-type. Do NOT embed the sub-type in item_type.)
- condition_summary (string — if the input data already has a condition_summary, copy it EXACTLY — never change the condition level. If generating fresh: use one of "Excellent used condition — [note]", "Very good used condition — [note]", "Good used condition — [note]". Default is "Very good used condition". Keep it SHORT.)
- flaws_note (string or null — null unless there is a clearly major visible flaw: hole, tear, large stain, broken zipper. Do NOT list: creasing, minor fading, small specks, normal wear.)
- made_in (string or null — copy from extracted made_in if present)
- fabric_mill (string or null — copy from extracted fabric_mill if present, e.g. "Tessuti Sondrio", "Vitale Barberis Canonico")
- premium (boolean — true only for premium brands listed above)
- buy_price_gbp (number or omit if unknown)
- confidence (number 0–1, carry over from extraction)
- low_confidence_fields (array of strings, carry over from extraction)

STRICT RULE — only use facts from the extracted fields. NEVER invent or assume:
- Description bullet points must come ONLY from: materials, fabric_mill, cut, model_name, tag_keywords (high confidence only), made_in, colour_secondary, pattern.
- Do NOT add any observations about construction, stitching, collar style, lining, canvas, patches, buttons, or any physical detail not explicitly in the extracted fields.
- Do NOT claim "hand finished", "fully lined", "original tags attached", "unworn", "half canvas", "full canvas", "patch collar", "elbow patches" unless these exact terms are in tag_keywords.
- CONDITION IN DESCRIPTION — do NOT restate condition in the description body. Never write "Good used condition", "Excellent condition", "very good condition", "no visible damage", "no holes or stains", or any similar phrase. The condition is a separate structured field. The ONLY exception: if flaws_note is set, add a single plain bullet with the flaw (e.g. "- Small mark on left sleeve.").
- If a field is null or absent, omit it entirely — do not substitute a guess.

Description format rules:
- Use the standardised colour (see Colour Standards in style guide) in both title and description.
- If colour_secondary is set, open the description with both colours (e.g. "White and navy polo shirt in cotton piqué."). Title uses primary colour only.
- If cut is set, include it in the title where space allows (e.g. "Slim Fit" or just "Slim" before or after item type). Mention it briefly in the description ("Slim cut.").
- If pattern is set and not "Plain", include it in the title before the colour (e.g. "Suitsupply Pinstripe Blazer Mens 44R Charcoal Wool"). Always mention the pattern in the description opening.
- If colour is "Multicoloured", use "Multicoloured" in both title and description.
- Write "Mens" or "Womens" (no apostrophe) in the title based on gender.
- Include ONE item type synonym from the synonyms table in the title.
- Include material in title if it is a premium/sellable fibre: cashmere, silk, angora, alpaca, mohair, merino, wool, lambswool, linen, waxed, down, leather, silk, tweed, corduroy.
- MATERIAL RANKING: In title and description, always list the most premium/natural fibre first. Rank order: cashmere > angora > alpaca > silk > mohair > merino wool > wool > lambswool > linen > cotton > down > leather > polyester > nylon > elastane/spandex. In the materials array, reorder so the most premium fibre appears first. In the title, use only the top-ranked premium fibre. In the description opening sentence, list the most premium fibre first (e.g. "Cotton and polyester track pants" not "Polyester and cotton").
- If made_in is set (e.g. "Italy"), include "Made in Italy" in the description — buyers search for this.
- If fabric_mill is set (e.g. "Tessuti Sondrio"), include the mill name in the description — buyers of quality menswear search for these names.
- Include model_name in the description if present.
- TAG KEYWORDS — use items from tag_keywords as follows:
  * If tag_keywords_confidence = "high": include the most buyer-relevant terms (e.g. collection name, fabric grade) in the title if space allows, or prominently in the description body (e.g. "Traveller collection. Super 120s wool.").
  * If tag_keywords_confidence = "low": do NOT include in title or description body — only in the Keywords sentence.
  * Always include all tag_keywords terms in the Keywords sentence regardless of confidence.
- ALWAYS append a keyword sentence at the very end of the description: "Keywords: [brand] [item type] [colour] [size] mens/womens clothing [material if notable] [any tag_keywords terms] casual smart designer"

premium = {str(is_premium).lower()}
{model_hint}
Return valid JSON only.
""".strip()


def write(item: dict, hints: dict | None = None) -> tuple[dict, dict]:
    """
    Generate a complete listing dict from extracted item data.
    Validates against schema before returning.
    Returns (listing, usage) tuple where usage also contains '_write_log'
    with observability data (category_slice_level, price_memory_match_level).

    Args:
        item: extracted item dict from extractor.extract()
        hints: optional user-confirmed values to override AI output,
               e.g. {"brand": "Suit Supply", "size": "W32 L32"}
    """
    import time
    _t_write_start = time.perf_counter()

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = _build_prompt(item, hints=hints)

    response = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=2500,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
    # Fix unescaped control characters inside JSON strings (literal \n, \r, \t).
    raw = _escape_json_strings(raw)
    # Fix trailing commas before } or ] — invalid in JSON, valid in JSON5.
    raw = re.sub(r",\s*([}\]])", r"\1", raw)
    # Decode from first `{` — raw_decode stops at end of first valid JSON object,
    # ignoring any trailing text the model appends after the closing brace
    start = raw.index("{")
    try:
        listing, _ = json.JSONDecoder().raw_decode(raw, start)
    except json.JSONDecodeError as exc:
        # Response was truncated (max_tokens hit).
        # Strategy 1: truncate before the broken field using the error position,
        #   then close the object.  Works for unterminated strings mid-field.
        # Strategy 2: find the last `}` that could close the outer object.
        truncated = raw[start:]
        recovered = False

        # Strategy 1: cut just before the field that's broken
        before_error = truncated[: exc.pos]
        last_comma = max(before_error.rfind(",\n"), before_error.rfind(",\r\n"))
        if last_comma != -1:
            candidate = before_error[: last_comma] + "\n}"
            try:
                listing, _ = json.JSONDecoder().raw_decode(candidate, 0)
                recovered = True
            except json.JSONDecodeError:
                pass

        # Strategy 2: last closing brace
        if not recovered:
            last_brace = truncated.rfind("}")
            if last_brace != -1:
                candidate = truncated[: last_brace + 1]
                try:
                    listing, _ = json.JSONDecoder().raw_decode(candidate, 0)
                    recovered = True
                except json.JSONDecodeError:
                    pass

        if not recovered:
            # Log the raw response so we can diagnose the exact failure
            import sys
            print(f"[listing_writer] JSON parse failed. stop_reason={response.stop_reason!r}. "
                  f"Raw response (first 600 chars):\n{raw[:600]}", file=sys.stderr)
            raise ValueError(
                f"Model response was truncated and could not be recovered. "
                f"stop_reason={response.stop_reason!r}. "
                f"Original error: {exc}"
            ) from exc

    # Carry forward fields from extractor not covered by listing writer
    listing.setdefault("photos_folder", item.get("photos_folder", ""))
    listing.setdefault("listed_date", date.today().isoformat())

    listing = _convert_eu_suit_size(listing)
    listing = _convert_eu_shoe_size(listing)
    listing = _apply_top_style(listing,
                               extracted_pattern=item.get("pattern"),
                               extracted_item_type=item.get("item_type"))

    # Deduplicate materials list (same fibre name appearing twice from misread labels)
    if isinstance(listing.get("materials"), list):
        seen_fibres: set[str] = set()
        deduped: list[str] = []
        for m in listing["materials"]:
            # Normalise to lowercase fibre name for dedup key (strip leading percentage)
            key = re.sub(r"^\d+%\s*", "", str(m)).lower().strip()
            if key and key not in seen_fibres:
                seen_fibres.add(key)
                deduped.append(m)
        listing["materials"] = deduped

    # If made_in is null/absent, strip any "Made in X" phrases the AI hallucinated into description
    if not listing.get("made_in") and not item.get("made_in"):
        listing["made_in"] = None
        desc = listing.get("description", "")
        # Remove lines like "- Made in Italy" or inline "Made in Japan." etc.
        desc = re.sub(r"-\s*Made in [^\n]+\n?", "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"Made in \w+\.?", "", desc, flags=re.IGNORECASE).strip()
        listing["description"] = desc

    # Apply confirmed hints — these take priority over AI output
    if hints:
        if hints.get("brand"):
            listing["brand"] = hints["brand"]
        if hints.get("size"):
            listing["tagged_size"] = hints["size"]
            listing["normalized_size"] = hints["size"]
            # Patch size in title if the AI used a different size string
            title = listing.get("title", "")
            old_size = item.get("tagged_size") or item.get("normalized_size") or ""
            if old_size and old_size in title:
                listing["title"] = title.replace(old_size, hints["size"], 1)
        if hints.get("gender"):
            listing["gender"] = hints["gender"]
        if hints.get("made_in"):
            listing["made_in"] = hints["made_in"]

    # Carry over extraction quality fields for the review UI
    listing.setdefault("brand_confidence", item.get("brand_confidence", "low"))
    listing.setdefault("material_confidence", item.get("material_confidence", "low"))

    # Price memory match level (for review UI + run log)
    _pm = _lookup_price_memory(
        item.get("brand"),
        item.get("item_type", ""),
        item.get("materials") or [],
    )
    listing["price_memory_match"] = _pm.get("match_level") if _pm else None

    # Compute warnings — surfaced in the review UI
    _warnings: list[str] = []
    if listing.get("brand_confidence") in ("low", "medium"):
        _warnings.append("low_brand_confidence")
    if listing.get("material_confidence") in ("low", "medium"):
        _warnings.append("low_material_confidence")
    if not listing["price_memory_match"] and ENABLE_PRICE_MEMORY:
        _warnings.append("no_price_memory")
    if listing.get("low_confidence_fields"):
        _warnings.append("low_confidence_fields")
    if item.get("_extract_log", {}).get("reread_errors"):
        _warnings.append("reread_failed")
    listing["warnings"] = _warnings
    listing.setdefault("error_tags", [])

    validate_or_raise(listing)

    _category_slice_level = _get_category_slice_level(
        item.get("gender", ""), item.get("item_type", "")
    )
    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "model": HAIKU_MODEL,
        "_write_log": {
            "category_slice_level": _category_slice_level,
            "price_memory_match_level": listing["price_memory_match"],
            "write_latency_ms": round((time.perf_counter() - _t_write_start) * 1000),
        },
    }
    return listing, usage
