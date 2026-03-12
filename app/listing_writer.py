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


def _build_prompt(item: dict) -> str:
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

    hints = []
    if item.get("model_name"):
        hints.append(f"model_name '{item['model_name']}' is the style/fit name — include it in the title if space allows.")
    w = item.get("trouser_waist")
    l = item.get("trouser_length")
    if w and l:
        hints.append(f"This is a trouser item. Use 'W{w} L{l}' as the size in the title and in tagged_size/normalized_size.")
    elif w:
        hints.append(f"This is a trouser item. Waist is {w}. Use 'W{w}' as the size.")
    model_hint = ("\nNotes:\n" + "\n".join(f"- {h}" for h in hints)) if hints else ""

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
- title (string, max 80 chars, format: Brand + Type + Key Feature + Colour + Size)
- description (string, follow style guide format)
- tagged_size (string — copy EXACTLY from extracted tagged_size, do not convert)
- normalized_size (string — for numeric EU/Italian sizes on trousers/shirts/knitwear, keep the number as-is. Only use S/M/L/XL for items where that is how they are sized.)
- materials (array of strings)
- colour (string)
- gender ("men's" | "women's" | "unisex")
- price_gbp (number — use pricing rules, assume buy_price_gbp if provided)
- category (string — use category rules to determine path)
- condition_summary (string — MUST start with "Very good" unless clear heavy wear visible. Never write "Good vintage" or "Good used". Example: "Very good used condition — no stains or holes.")
- flaws_note (string or null)
- premium (boolean — true only for premium brands listed above)
- buy_price_gbp (number or omit if unknown)
- confidence (number 0–1, carry over from extraction)
- low_confidence_fields (array of strings, carry over from extraction)

premium = {str(is_premium).lower()}
{model_hint}
Return valid JSON only.
""".strip()


def write(item: dict) -> tuple[dict, dict]:
    """
    Generate a complete listing dict from extracted item data.
    Validates against schema before returning.
    Returns (listing, usage) tuple.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = _build_prompt(item)

    response = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=1024,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
    listing = json.loads(raw)

    # Carry forward fields from extractor not covered by listing writer
    listing.setdefault("photos_folder", item.get("photos_folder", ""))
    listing.setdefault("listed_date", date.today().isoformat())

    listing = _convert_eu_suit_size(listing)
    validate_or_raise(listing)
    usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens, "model": HAIKU_MODEL}
    return listing, usage
