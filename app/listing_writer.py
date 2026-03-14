"""
Listing writer: takes extractor output and generates a complete Vinted listing.

Uses Claude Haiku 4.5 with prompts from prompts/ directory.
Validates output against listing.schema.json before returning.
"""
import json
import re
from datetime import date

import anthropic

from app.config import ANTHROPIC_API_KEY, HAIKU_MODEL, PROMPTS_DIR
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

_SYSTEM = """
You are writing concise, honest Vinted resale listings for second-hand clothing.
Follow the style guide and category rules exactly.
Return only a valid JSON object — no markdown, no explanation.
""".strip()


def _build_prompt(item: dict, hints: dict | None = None) -> str:
    style = (PROMPTS_DIR / "listing_style.md").read_text()
    categories = (PROMPTS_DIR / "category_rules.md").read_text()
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
    _ACTIVEWEAR = ("jogger", "sweatpant", "tracksuit", "legging", "activewear", "gym pant", "track pant", "trackpant", "track suit")
    is_activewear = any(k in item_type_lower for k in _ACTIVEWEAR)
    is_trouser = is_activewear or any(k in item_type_lower for k in ("trouser", "jeans", "shorts", "chino", "cargo"))
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
    if hints and hints.get("damages"):
        hint_notes.append(f"User-reported damage: '{hints['damages']}' — include this in flaws_note and condition_summary.")

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
- materials (array of strings)
- colour (string)
- colour_secondary (string or null — copy from extracted colour_secondary)
- style (string or null — the Vinted sub-genre key. For men's jeans: one of Slim / Straight / Skinny / Ripped (only these 4 exist on Vinted UK). For women's jeans: one of Straight / Skinny / Boyfriend / Cropped / Flared / High waisted / Ripped. For jackets: one of Denim / Bomber / Biker / Field / Fleece / Harrington / Puffer / Quilted / Shacket / Varsity / Windbreaker. For coats: one of Overcoat / Trench / Parka / Peacoat / Raincoat / Duffle. For men's boots: one of Chelsea / Desert / Wellington / Work. For women's boots: one of Ankle / Knee. Copy from extracted style if present; otherwise infer from item_type, model_name, cut, tag_keywords. Null only if genuinely cannot determine.)
- cut (string or null — copy from extracted cut if present, e.g. "Slim", "Classic")
- pattern (string or null — copy from extracted pattern, e.g. "Pinstripe", "Plain")
- tag_keywords (array — copy from extraction)
- tag_keywords_confidence (string or null — copy from extraction: "high" or "low")
- gender ("men's" | "women's" | "unisex")
- price_gbp (number — use pricing rules, assume buy_price_gbp if provided)
- category (string — use category rules to determine path. Use the BASE category only (e.g. "Men > Jeans", "Men > Coats", "Women > Jackets") — the style field drives the sub-type. Do NOT embed the sub-type in item_type.)
- condition_summary (string — if the input data already has a condition_summary, copy it EXACTLY — never change the condition level. If generating fresh: use one of "Excellent used condition — [note]", "Very good used condition — [note]", "Good used condition — [note]". Default is "Very good used condition". Keep it SHORT. The description opening sentence MUST match the condition_summary level exactly.)
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
- Do NOT add condition improvements not in the extracted condition_summary.
- If a field is null or absent, omit it entirely — do not substitute a guess.

Description format rules:
- Use the standardised colour (see Colour Standards in style guide) in both title and description.
- If colour_secondary is set, open the description with both colours (e.g. "White and navy polo shirt in cotton piqué."). Title uses primary colour only.
- If cut is set, include it in the title where space allows (e.g. "Slim Fit" or just "Slim" before or after item type). Mention it briefly in the description ("Slim cut.").
- If pattern is set and not "Plain", include it in the title before the colour (e.g. "Suitsupply Pinstripe Blazer Mens 44R Charcoal Wool"). Always mention the pattern in the description opening.
- If colour is "Multicoloured", use "Multicoloured" in both title and description.
- Write "Mens" or "Womens" (no apostrophe) in the title based on gender.
- Include ONE item type synonym from the synonyms table in the title.
- Include material in title if it is a premium/sellable fibre: wool, merino, cashmere, lambswool, linen, waxed, down, leather, silk, tweed, corduroy.
- MATERIAL RANKING: In title and description, always list the most premium/natural fibre first. Rank order: cashmere > silk > merino wool > wool > lambswool > linen > cotton > down > leather > polyester > nylon > elastane/spandex. In the materials array, reorder so the most premium fibre appears first. In the title, use only the top-ranked premium fibre. In the description opening sentence, list the most premium fibre first (e.g. "Cotton and polyester track pants" not "Polyester and cotton").
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
    Returns (listing, usage) tuple.

    Args:
        item: extracted item dict from extractor.extract()
        hints: optional user-confirmed values to override AI output,
               e.g. {"brand": "Suit Supply", "size": "W32 L32"}
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = _build_prompt(item, hints=hints)

    response = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=1100,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
    # Decode from first `{` — raw_decode stops at end of first valid JSON object,
    # ignoring any trailing text the model appends after the closing brace
    start = raw.index("{")
    listing, _ = json.JSONDecoder().raw_decode(raw, start)

    # Carry forward fields from extractor not covered by listing writer
    listing.setdefault("photos_folder", item.get("photos_folder", ""))
    listing.setdefault("listed_date", date.today().isoformat())

    listing = _convert_eu_suit_size(listing)

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

    validate_or_raise(listing)
    usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens, "model": HAIKU_MODEL}
    return listing, usage
