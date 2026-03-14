"""
Vision extraction: analyse clothing photos and return structured item data.

Supports VISION_PROVIDER:
  - claude-haiku  (default) — Anthropic Claude Haiku 4.5
  - gemini-flash             — Google Gemini Flash (requires GOOGLE_AI_API_KEY)
"""
import base64
import io
import json
import re
from pathlib import Path

import anthropic

from app.config import (
    ANTHROPIC_API_KEY,
    CONFIDENCE_THRESHOLD,
    CORE_PHOTOS,
    GOOGLE_AI_API_KEY,
    HAIKU_MODEL,
    ITEMS_DIR,
    SONNET_MODEL,
    VISION_PROVIDER,
)

_EXTRACT_PROMPT = """
You are extracting structured data from clothing photos for a resale listing.

Analyse the provided photos (front, brand label, model/size tag, material label, back if provided). Photo 2 is specifically the brand label — read the text on the main woven or printed label in that photo with extreme care, letter by letter, to identify the brand.

Photo 1 (front view) determines item type — identify by SHAPE and SILHOUETTE:
- TWO LEG OPENINGS at the bottom = a BOTTOM garment (trousers, track pants, jeans, shorts, joggers). NEVER classify a two-legged garment as a pullover, hoodie, or sweatshirt.
- Arm openings at the sides, hangs from shoulders = a TOP (shirt, jacket, jumper, hoodie, sweatshirt).

Return a JSON object with these fields:

{
  "brand": "string or null — the MANUFACTURER/LABEL name only (e.g. 'Suit Supply', 'Barbour', 'Hugo Boss'). NOT the model or style name.",
  "model_name": "string or null — the style/model/fit name if visible on tag (e.g. 'Brentwood', 'Lennon', 'Slim'). Separate from brand.",
  "item_type": "string (e.g. wax jacket, lambswool jumper, wool trousers)",
  "tagged_size": "string — EXACTLY as printed on tag (e.g. '52', 'W32 L32', 'C42', '12', 'M'). Never convert or interpret.",
  "normalized_size": "string — For trousers/jeans/shorts: look for BOTH waist and leg length on the tag and format as 'W32 L32'. If only one number is visible, record that. For suit/blazer sizes: keep bare EU numbers as-is (e.g. '54'). If already in UK format with R/L/S suffix (e.g. '44R'), keep as-is. For knitwear/shirts with EU numbers, keep as-is. For S/M/L/XL, keep as-is.",
  "trouser_waist": "string or null — for trousers/jeans/shorts only: waist measurement as on tag (e.g. '32', '34'). Null for all other items.",
  "trouser_length": "string or null — for trousers/jeans/shorts only: leg length as on tag (e.g. '32', '30'). Null for all other items.",
  "style": "string or null — the Vinted sub-genre key for this item. For jeans (men's): one of Slim / Straight / Skinny / Ripped. For jeans (women's): one of Straight / Skinny / Boyfriend / Cropped / Flared / High waisted / Ripped. For jackets: one of Denim / Bomber / Biker / Field / Fleece / Harrington / Puffer / Quilted / Shacket / Varsity / Windbreaker. For coats: one of Overcoat / Trench / Parka / Peacoat / Raincoat / Duffle. For men's boots: one of Chelsea / Desert / Wellington / Work. For women's boots: one of Ankle / Knee / Wellington. Infer from tag text, model name, and item shape. Null if item type has no sub-genre or it cannot be determined.",
  "cut": "string or null — the cut or fit style if labeled on the tag (e.g. 'Slim', 'Classic', 'Regular', 'Tailored'). Look for 'CUT:' or 'FIT:' on the size tag. Null if not present.",
  "materials": ["COMPLETE list of ALL fibres/materials with percentages exactly as on the care label. Include EVERY fibre listed. Format each as '50% Cotton' or '100% Merino Wool' or 'Polyester lining' etc. Check BOTH the main brand label AND the material/care label photo. Do NOT omit any fibre. Do NOT list the same fibre twice. Common fibres: wool, merino, lambswool, cashmere, cotton, linen, silk, polyester, viscose, elastane, nylon, acrylic, modal, lyocell."],
  "fabric_mill": "string or null — if a fabric mill/supplier name is visible on the MATERIAL label (e.g. 'Tessuti Sondrio', 'Vitale Barberis Canonico', 'Loro Piana fabric'), record it here. This is NOT the brand.",
  "made_in": "string or null — country of manufacture if visible on any label (e.g. 'Italy', 'England', 'Portugal'). Look for 'Made in X' text.",
  "colour": "string — PRIMARY colour using standardised names (e.g. 'White', 'Navy', 'Charcoal'). If 3+ distinct colours: 'Multicoloured'.",
  "colour_secondary": "string or null — SECOND dominant colour if clearly a major design element (rough 15%+ of garment). Same standardised names. Null if item is effectively one colour. If colour is 'Multicoloured', set this to null.",
  "pattern": "string — the fabric/garment pattern assessed from the FRONT photo. Use one of: 'Plain', 'Pinstripe', 'Chalk stripe', 'Stripe', 'Check', 'Windowpane', 'Houndstooth', 'Herringbone', 'Tartan', 'Tweed', 'Floral', 'Abstract', 'Graphic', 'Paisley'. Use 'Plain' if solid with no visible weave pattern. Default to 'Plain' if unsure.",
  "gender": "men's | women's | unisex",
  "condition_summary": "one sentence, honest assessment. Creasing, minor fading, and small specks do NOT count as flaws and must not downgrade condition. Only visible damage counts: holes, tears, stains, broken zips, missing buttons.",
  "flaws_note": "string or null — any visible damage, stains, repairs",
  "tag_keywords": ["list of additional notable terms found on ANY tag/label that add buyer or search value — e.g. collection names ('Traveller', 'Black Label', 'Blue Harbour'), fabric quality markers ('Super 120s', 'Super 110s', 'VBC 130s'), special treatments or technology ('Water Resistant', 'Performance', 'Stretch'), notable certifications or details ('Hand finished', 'Full canvas', 'Half canvas'). Do NOT duplicate brand, model_name, cut, or basic material. Empty list if nothing notable."],
  "tag_keywords_confidence": "high | low — high if you can clearly read these terms, low if you are inferring or partially reading them",
  "confidence": 0.0-1.0,
  "low_confidence_fields": ["list of field names where you are uncertain"]
}

Rules:
- Use ONLY information visible in the photos. Do not guess.
- BRAND vs MODEL — critical distinction:
  * brand = the MANUFACTURER (the company that made the item). It is usually the largest text on the main woven label, or the name on the outer brand label.
  * model_name = the style, fit, or collection name. These are DIFFERENT things.
  * If a line on the tag is prefixed with "Model:", "Style:", "Fit:", "Collection:", or "Cut:" — that word is the model_name, NOT the brand.
  * Example: a tag showing "SUIT SUPPLY" then "Model: Brentwood" means brand="Suit Supply", model_name="Brentwood". "Brentwood" is NOT the brand.
  * If you cannot clearly identify the brand from the label, set brand to null and add "brand" to low_confidence_fields. Do NOT guess a brand from a model name.
  * If a small secondary tab is attached near the brand label with a single collection/range word (e.g. "TRAVELLER", "URBAN", "LINEN"), include it in model_name. Combine with the size tag model name if both are present (e.g. "Havana Patch — Traveller").
- FABRIC MILLS ARE NEVER THE BRAND — this is the most common mistake. Read carefully:
  * A fabric mill is a company that WOVE THE CLOTH. Their name appears on the care/material composition label to certify the fabric quality. They did NOT make the garment.
  * The brand is the company that MADE THE GARMENT. Their label is sewn inside the collar, chest, or waistband as a woven brand label.
  * WRONG: photos show "Suit Supply" on the main woven label + "Lanificio" on the material label → brand="Lanificio" ← THIS IS WRONG
  * CORRECT: same photos → brand="Suit Supply", fabric_mill="Lanificio"
  * If you see any of these names anywhere in the photos, they are ALWAYS fabric mills — NEVER the brand. Put them in fabric_mill only:
    Lanificio, Tessuti Sondrio, Vitale Barberis Canonico, VBC, Reda, Loro Piana (as fabric supplier), Scabal, Holland & Sherry, Dormeuil, Fratelli Tallia di Delfino, Zignone, Cerruti, Drapers, Loro Piana Fabric
  * If the material label shows a mill name but the brand label is unclear, set brand=null — do NOT fall back to the mill name.
- ITEM TYPE — polo shirts vs knitwear: A polo shirt has a COLLAR + SHORT BUTTON PLACKET at the neck. Even if the fabric is cotton piqué (a knit fabric), it is STILL a "polo shirt" — NOT a jumper, sweater, or knitwear. Ralph Lauren, Lacoste, Fred Perry items with a collar are polo shirts. Only classify as jumper/knitwear if there is NO collar and the item is pulled on over the head.
- MATERIALS: Read ALL fibres from the care/composition label. Include EVERY fibre with its exact percentage (e.g. "68% Wool, 22% Polyester, 10% Elastane"). Do not round or drop minor fibres. If a lining or shell is listed separately (e.g. "Shell: 100% Cotton, Lining: 100% Polyester"), include both. Check BOTH the main brand/tag photo AND the material/care label photo.
- MADE IN: Only set made_in if the exact phrase "Made in [Country]" (or "Fabricado en", "Fabriqué en") appears explicitly on the GARMENT's brand or care label.
  * NEVER use "FABRIC MADE IN X" or "CLOTH MADE IN X" — that is where the cloth was woven, not where the garment was assembled.
  * NEVER infer made_in from Asian characters (Japanese, Chinese, Korean text) — those are translations of material composition, not country of manufacture.
  * If you cannot find an explicit "Made in [Country]" phrase, set made_in to null.
- COLOUR: assess the whole garment including body, panels, and stripes.
  * One dominant colour (roughly 80%+ of the visible garment): colour = that colour, colour_secondary = null.
  * Two clearly distinct major colours (e.g. white body + navy chest panel, navy body + red stripe block): colour = dominant, colour_secondary = secondary. Small logos, accent stitching, and buttons do NOT count as a second colour.
  * Three or more clearly distinct colours: colour = "Multicoloured", colour_secondary = null.
- TAG KEYWORDS: scan ALL labels and tags in every photo for additional notable terms.
  * Collection/range names that appear as standalone words on separate tabs or in prominent positions on the brand label (e.g. "TRAVELLER", "BLACK LABEL", "BLUE LINE") — these are search terms buyers use.
  * Fabric quality designations that appear on the material or brand label (e.g. "Super 120s", "Super 110s", "VBC 130s") — these are valuable for quality buyers.
  * Special fabric treatments or technologies (e.g. "Water Resistant", "Stretch", "Performance", "Machine Washable").
  * If you can clearly read a term: tag_keywords_confidence = "high". If partially visible or inferred: "low".
  * tag_keywords_confidence = "high" means terms may go in the title or description body; "low" means keywords section only.
- PATTERN: assess the fabric/body pattern from the front photo.
  * Look at the main body fabric, not logos or trims.
  * Thin parallel lines on a solid ground = Pinstripe (very fine) or Chalk stripe (slightly bolder).
  * Stripes of any other kind = Stripe.
  * Box or grid of lines = Check (small) or Windowpane (large squares).
  * Diagonal interlocking waves = Houndstooth; diagonal twill = Herringbone.
  * Multicolour plaid with crossing lines = Tartan.
  * Solid with no visible weave pattern = Plain.
  * Default to 'Plain' if unsure.
- If a field is not visible or unreadable, set it to null and add it to low_confidence_fields. Do NOT guess.
- confidence is your overall certainty across all fields (1.0 = fully certain).
- Return valid JSON only — no markdown, no explanation.
""".strip()


def _build_prompt_with_hints(hints: dict) -> str:
    """Prepend user-supplied hints to the extraction prompt so the model anchors on them."""
    if not hints:
        return _EXTRACT_PROMPT
    lines = [
        "USER-PROVIDED HINTS — treat these as confirmed ground truth.",
        "Only correct obvious spelling mistakes; do not override or contradict them:",
    ]
    if hints.get("brand"):
        lines.append(f"- Brand: {hints['brand']}")
    if hints.get("size"):
        lines.append(f"- Size: {hints['size']}")
    if hints.get("gender"):
        lines.append(f"- Gender: {hints['gender']}")
    lines.append("")
    return "\n".join(lines) + "\n" + _EXTRACT_PROMPT


# Known fabric mills — if the model sets brand to one of these it has made an error.
# This is a deterministic safety net; the prompt instructions alone aren't reliable enough.
_KNOWN_MILLS: frozenset[str] = frozenset({
    "lanificio", "lanificio f.lli cerruti", "f.lli cerruti",
    "tessuti sondrio", "vitale barberis canonico", "vbc",
    "reda", "loro piana fabric", "scabal", "holland & sherry",
    "dormeuil", "fratelli tallia di delfino", "zignone",
    "cerruti 1881 fabric", "drapers",
})


def _sanitise_brand(result: dict) -> dict:
    """If the model put a fabric mill in the brand field, move it to fabric_mill and null brand."""
    brand = (result.get("brand") or "").strip()
    if not brand:
        return result
    brand_lower = brand.lower()
    for mill in _KNOWN_MILLS:
        if mill in brand_lower or brand_lower in mill:
            # Move to fabric_mill if not already set
            if not result.get("fabric_mill"):
                result["fabric_mill"] = brand
            result["brand"] = None
            result.setdefault("low_confidence_fields", [])
            if "brand" not in result["low_confidence_fields"]:
                result["low_confidence_fields"].append("brand")
            break
    return result


_MAX_DIMENSION = 1024  # 1568 → 1024 saves ~5000 input tokens per call (40% cost reduction)
_JPEG_QUALITY = 80


def _compress_image(path: Path) -> tuple[str, str]:
    """Resize and compress an image, returning (base64_data, media_type)."""
    try:
        from PIL import Image
        img = Image.open(path)
        img = img.convert("RGB")
        w, h = img.size
        if max(w, h) > _MAX_DIMENSION:
            scale = _MAX_DIMENSION / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
        return base64.standard_b64encode(buf.getvalue()).decode(), "image/jpeg"
    except ImportError:
        # Pillow not installed — fall back to raw bytes
        data = base64.standard_b64encode(path.read_bytes()).decode()
        ext = path.suffix.lower()
        media_type = "image/jpeg" if ext in {".jpg", ".jpeg"} else f"image/{ext.lstrip('.')}"
        return data, media_type


def _load_photos(folder: Path) -> list[dict]:
    """Load core analysis photos (front/tag/material/back) from folder.
    Returns list of Anthropic image content blocks."""
    blocks = []
    extensions = {".jpg", ".jpeg", ".png", ".webp"}

    for name in CORE_PHOTOS:
        for ext in extensions:
            candidate = folder / f"{name}{ext}"
            if candidate.exists():
                data, media_type = _compress_image(candidate)
                blocks.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": data},
                })
                break

    if not blocks:
        raise FileNotFoundError(f"No core photos found in {folder}")
    return blocks


def _extract_claude(photos: list[dict], model: str, prompt: str) -> tuple[dict, dict]:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    content = photos + [{"type": "text", "text": prompt}]
    response = client.messages.create(
        model=model,
        max_tokens=512,
        messages=[{"role": "user", "content": content}],
    )
    raw = response.content[0].text.strip()
    # Strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
    usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens, "model": model}
    return json.loads(raw), usage


def _extract_gemini(photos: list[dict], prompt: str) -> dict:
    """Gemini Flash extraction via REST API."""
    import urllib.request

    parts = []
    for photo in photos:
        src = photo["source"]
        parts.append({
            "inline_data": {
                "mime_type": src["media_type"],
                "data": src["data"],
            }
        })
    parts.append({"text": prompt})

    body = json.dumps({"contents": [{"parts": parts}]}).encode()
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash-lite:generateContent?key={GOOGLE_AI_API_KEY}"
    )
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())

    raw = result["candidates"][0]["content"]["parts"][0]["text"].strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
    return json.loads(raw)


# Known OCR misreads: lowercase misread -> correct brand name
# These explicit entries catch the most common / hardest cases.
# The fuzzy-match fallback below handles everything else.
_BRAND_CORRECTIONS: dict[str, str] = {
    # Suitsupply misreads (stylised logo is consistently misread)
    "suitsupply": "Suitsupply",
    "suit supply": "Suitsupply",
    "buttsupply": "Suitsupply",
    "butts supply": "Suitsupply",
    "butt supply": "Suitsupply",
    "burts supply": "Suitsupply",
    "burt supply": "Suitsupply",
    "suits supply": "Suitsupply",
    # Other common misreads
    "hugo bas": "Hugo Boss",
    "hugo bos": "Hugo Boss",
    "ralphlauren": "Ralph Lauren",
    "polo ralph": "Ralph Lauren",
    "polo ralph lauren": "Ralph Lauren",
    "lacoste sport": "Lacoste",
    "levis": "Levi's",
    "levi strauss": "Levi's",
}

# Lazy-loaded list of canonical brand names from data/brands.txt
_BRAND_LIST: list[str] | None = None


def _load_brand_list() -> list[str]:
    global _BRAND_LIST
    if _BRAND_LIST is None:
        brands_file = Path(__file__).parent.parent / "data" / "brands.txt"
        if brands_file.exists():
            _BRAND_LIST = [
                line.strip() for line in brands_file.read_text().splitlines()
                if line.strip() and not line.startswith("#")
            ]
        else:
            _BRAND_LIST = []
    return _BRAND_LIST


def _apply_brand_corrections(brand: str | None) -> str | None:
    """Fix known OCR misreads — exact dict first, then fuzzy match against brands.txt."""
    if not brand:
        return brand
    brand_stripped = brand.strip()

    # 1. Exact dict lookup (handles hard stylised-logo cases)
    corrected = _BRAND_CORRECTIONS.get(brand_stripped.lower())
    if corrected:
        return corrected

    # 2. Fuzzy match against brands.txt (handles generic OCR typos)
    import difflib
    brand_list = _load_brand_list()
    if brand_list:
        matches = difflib.get_close_matches(brand_stripped, brand_list, n=1, cutoff=0.80)
        if matches:
            return matches[0]

    return brand_stripped


def _reread_material_photo(folder: Path, model: str) -> str | None:
    """
    Single-photo targeted re-read of the material label photo for fabric_mill.
    Called when main extraction did not capture a fabric_mill.
    Returns the mill name string or None.
    """
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        mat_photo = folder / f"material{ext}"
        if mat_photo.exists():
            data, media_type = _compress_image(mat_photo)
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            response = client.messages.create(
                model=model,
                max_tokens=60,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
                        {"type": "text", "text": (
                            "Look at this clothing care/material label photo carefully. "
                            "Is there a fabric mill or cloth supplier name printed on it? "
                            "Known fabric mill names to look for: Cerruti, Lanificio, Tessuti Sondrio, "
                            "Vitale Barberis Canonico, VBC, Reda, Loro Piana, Scabal, Holland & Sherry, "
                            "Dormeuil, Fratelli Tallia di Delfino, Zignone, Drapers. "
                            'Return only JSON: {"fabric_mill": "EXACT NAME"} or {"fabric_mill": null} if none visible.'
                        )},
                    ],
                }],
            )
            raw = response.content[0].text.strip()
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
            try:
                start = raw.index("{")
                result, _ = json.JSONDecoder().raw_decode(raw, start)
                return result.get("fabric_mill")
            except Exception:
                return None
    return None


def _reread_brand_photo(folder: Path, model: str) -> dict | None:
    """
    Single-photo targeted re-read of the brand label photo.
    Returns dict with 'brand' and optionally 'collection_keywords'.
    Always runs when a brand photo exists — cheap (~£0.00002) and more accurate
    than multi-photo extraction for the brand field.
    """
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        brand_photo = folder / f"brand{ext}"
        if brand_photo.exists():
            data, media_type = _compress_image(brand_photo)
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            response = client.messages.create(
                model=model,
                max_tokens=80,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
                        {"type": "text", "text": (
                            'Look at this clothing brand label photo carefully.\n'
                            '1. Read the MAIN brand/manufacturer name letter by letter. '
                            'Common brands you might see (use exact spelling if it matches): '
                            'Suitsupply, Barbour, Hugo Boss, Paul Smith, Hackett, Canali, Corneliani, '
                            'Ralph Lauren, Lacoste, Fred Perry, Ermenegildo Zegna, Belstaff, Grenfell, '
                            'Ted Baker, Reiss, Burberry, Aquascutum, Gieves & Hawkes, Lyle & Scott, '
                            'John Smedley, Pringle of Scotland, Brora, N.Peal, Johnstons of Elgin, '
                            'Cordings, Chester Barrie, Simon Carter, Thomas Pink, Charles Tyrwhitt, '
                            'TM Lewin, Marks & Spencer, Next, Jaeger, Crombie, Magee, Ben Sherman, '
                            'Tommy Hilfiger, Gant, Stone Island, CP Company, Carhartt, Carhartt WIP, '
                            'Patagonia, Arc\'teryx, North Face, Moncler, Canada Goose, Woolrich, '
                            'Levi\'s, Wrangler, Lee, G-Star Raw, Diesel, Nudie Jeans, Edwin, '
                            'Boglioli, Caruso, Pal Zileri, Brioni, Kiton, Isaia, Oliver Spencer, '
                            'Albam, Folk, Norse Projects, Universal Works, Sunspel, Represent, '
                            'Kenzo, Acne Studios, Ami Paris, Maison Margiela. '
                            'If the text closely resembles one of these, use the correct spelling.\n'
                            '2. Look for any SMALL SECONDARY TABS or additional labels attached nearby '
                            '(e.g. "TRAVELLER", "URBAN", "LINEN", "BLACK LABEL") — these are collection names.\n'
                            'Return only JSON: {"brand": "EXACT BRAND NAME", "collection_keywords": ["list", "of", "any", "collection", "tabs"]}.\n'
                            'If brand is unclear return {"brand": null, "collection_keywords": []}.'
                        )},
                    ],
                }],
            )
            raw = response.content[0].text.strip()
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
            try:
                return json.loads(raw)
            except Exception:
                return None
    return None


def extract(item_folder: str | Path, hints: dict | None = None) -> dict:
    """
    Extract structured item data from photos in item_folder.

    Args:
        item_folder: path to folder containing clothing photos
        hints: optional dict with user-supplied overrides, e.g.
               {"brand": "Suit Supply", "size": "W32 L32", "gender": "men's"}

    Returns a dict ready to pass to listing_writer.write().
    Escalates to Sonnet if confidence is below threshold.
    """
    folder = Path(item_folder) if not isinstance(item_folder, Path) else item_folder
    if not folder.is_absolute():
        folder = ITEMS_DIR / folder

    photos = _load_photos(folder)
    prompt = _build_prompt_with_hints(hints or {})

    if VISION_PROVIDER == "gemini-flash":
        if not GOOGLE_AI_API_KEY:
            raise EnvironmentError("GOOGLE_AI_API_KEY required for gemini-flash provider")
        result = _extract_gemini(photos, prompt)
        usage = {"input_tokens": 0, "output_tokens": 0, "model": "gemini-flash"}
    else:
        result, usage = _extract_claude(photos, HAIKU_MODEL, prompt)

    # Escalate to Sonnet only if confidence is low AND it's not just the brand field
    # (brand uncertainty is handled cheaply by _reread_brand_photo instead)
    confidence = result.get("confidence", 1.0)
    non_brand_uncertain = [f for f in result.get("low_confidence_fields", []) if f != "brand"]
    if confidence < CONFIDENCE_THRESHOLD and non_brand_uncertain and VISION_PROVIDER != "gemini-flash":
        print(f"Low confidence ({confidence:.2f}) on {non_brand_uncertain}, escalating to {SONNET_MODEL}")
        result, usage = _extract_claude(photos, SONNET_MODEL, prompt)

    # Deterministic safety net: move any fabric mill that landed in brand → fabric_mill
    result = _sanitise_brand(result)

    # Always re-read brand from brand photo when it exists — more reliable than multi-photo extraction
    if VISION_PROVIDER != "gemini-flash":
        reread = _reread_brand_photo(folder, HAIKU_MODEL)
        if reread and reread.get("brand"):
            old_brand = result.get("brand")
            new_brand = _apply_brand_corrections(reread["brand"])
            if new_brand != old_brand:
                print(f"  Brand re-read: '{old_brand}' -> '{new_brand}'")
            result["brand"] = new_brand
            result["low_confidence_fields"] = [f for f in result.get("low_confidence_fields", []) if f != "brand"]
            # Merge any collection keywords found on the brand label
            extra_kws = reread.get("collection_keywords") or []
            if extra_kws:
                existing = result.get("tag_keywords") or []
                merged = existing + [k for k in extra_kws if k not in existing]
                result["tag_keywords"] = merged
                if result.get("tag_keywords_confidence") != "high":
                    result["tag_keywords_confidence"] = "high"
                print(f"  Collection keywords from brand photo: {extra_kws}")

    # Deterministic brand correction as fallback (catches misreads without brand photo)
    result["brand"] = _apply_brand_corrections(result.get("brand"))

    # If made_in is uncertain, clear it — a wrong country is worse than none
    if "made_in" in result.get("low_confidence_fields", []):
        result["made_in"] = None

    # If fabric_mill was missed by main extraction, do a cheap targeted re-read
    if not result.get("fabric_mill") and VISION_PROVIDER != "gemini-flash":
        reread_mill = _reread_material_photo(folder, HAIKU_MODEL)
        if reread_mill:
            print(f"  Fabric mill re-read: '{reread_mill}'")
            result["fabric_mill"] = reread_mill

    # Ensure fabric_mill is always in tag_keywords so it appears at minimum in keywords line
    mill = result.get("fabric_mill")
    if mill:
        existing_kws = result.get("tag_keywords") or []
        if mill not in existing_kws:
            result["tag_keywords"] = existing_kws + [mill]
        if not result.get("tag_keywords_confidence"):
            result["tag_keywords_confidence"] = "high"

    # Apply confirmed hints directly — override anything the AI got wrong
    if hints:
        if hints.get("brand"):
            result["brand"] = hints["brand"]
            result.setdefault("low_confidence_fields", [])
            if "brand" in result["low_confidence_fields"]:
                result["low_confidence_fields"].remove("brand")
        if hints.get("gender"):
            result["gender"] = hints["gender"]
        if hints.get("size"):
            result["tagged_size"] = hints["size"]
            result["normalized_size"] = hints["size"]

    result["photos_folder"] = str(folder)
    return result, usage
