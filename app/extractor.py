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
    ENABLE_LABEL_AUTOCROP,
    ENABLE_PARALLEL_REREADS,
    GOOGLE_AI_API_KEY,
    HAIKU_MODEL,
    ITEMS_DIR,
    SONNET_MODEL,
    VISION_PROVIDER,
)

def _escape_json_strings(s: str) -> str:
    """Escape bare control characters inside JSON string values."""
    result: list[str] = []
    in_string = False
    escape_next = False
    for ch in s:
        if escape_next:
            result.append(ch); escape_next = False
        elif ch == "\\":
            result.append(ch); escape_next = True
        elif ch == '"':
            result.append(ch); in_string = not in_string
        elif in_string and ch == "\n": result.append("\\n")
        elif in_string and ch == "\r": result.append("\\r")
        elif in_string and ch == "\t": result.append("\\t")
        else: result.append(ch)
    return "".join(result)


def _safe_json_loads(raw: str) -> dict:
    """Parse JSON with escaping, trailing-comma fixes, and truncation recovery."""
    raw = _escape_json_strings(raw)
    raw = re.sub(r",\s*([}\]])", r"\1", raw)
    try:
        start = raw.index("{")
        result, _ = json.JSONDecoder().raw_decode(raw, start)
        return result
    except (json.JSONDecodeError, ValueError) as exc:
        # Truncation recovery: cut before broken field, close object
        try:
            start = raw.index("{")
        except ValueError:
            raise exc
        truncated = raw[start:]
        # Strategy 1: cut before the broken field
        before_error = truncated[: getattr(exc, "pos", len(truncated))]
        last_comma = max(before_error.rfind(",\n"), before_error.rfind(",\r\n"))
        if last_comma != -1:
            candidate = before_error[:last_comma] + "\n}"
            try:
                result, _ = json.JSONDecoder().raw_decode(candidate, 0)
                return result
            except json.JSONDecodeError:
                pass
        # Strategy 2: last closing brace
        last_brace = truncated.rfind("}")
        if last_brace != -1:
            candidate = truncated[:last_brace + 1]
            try:
                result, _ = json.JSONDecoder().raw_decode(candidate, 0)
                return result
            except json.JSONDecodeError:
                pass
        raise exc


_EXTRACT_PROMPT = """
You are extracting structured data from clothing photos for a resale listing.

Analyse the provided photos (front, brand label, model/size tag, material label, back if provided). Photo 2 is specifically the brand label — read the text on the main woven or printed label in that photo with extreme care, letter by letter, to identify the brand.

Photo 1 (front view) determines item type — identify by SHAPE and SILHOUETTE:
- TWO LEG OPENINGS at the bottom = a BOTTOM garment (trousers, track pants, jeans, shorts, joggers). NEVER classify a two-legged garment as a pullover, hoodie, or sweatshirt.
- Arm openings at the sides, hangs from shoulders = a TOP (shirt, jacket, jumper, hoodie, sweatshirt).

Return a JSON object with these fields:

{
  "brand": "string or null — the MANUFACTURER/LABEL name only (e.g. 'Suit Supply', 'Barbour', 'Hugo Boss'). NOT the model or style name.",
  "brand_confidence": "\"high\" | \"medium\" | \"low\" — how clearly you could read the brand label. See BRAND CONFIDENCE rules below.",
  "brand_reason": "string — one sentence: what text you saw on the label and why you are confident or uncertain (e.g. 'Clearly reads BARBOUR in large woven text.' or 'Logo is partially covered; text looks like HACKETT but missing one character.').",
  "brand_candidates": ["only populate if brand_confidence is medium or low — 2-3 plausible alternative readings, e.g. [\"Hackett\", \"Hackitt\"]"],
  "sub_brand": "string or null — a secondary brand or product line printed separately on the same label or on an inner tab (e.g. 'Polo' for Polo Ralph Lauren, 'Sport' for Hugo Boss Sport, 'Black Label'). Null if no secondary name present.",
  "model_name": "string or null — the style/model/fit name if visible on tag (e.g. 'Brentwood', 'Lennon', 'Slim'). Separate from brand.",
  "item_type": "string (e.g. wax jacket, lambswool jumper, wool trousers)",
  "tagged_size": "string — EXACTLY as printed on tag (e.g. '52', 'W32 L32', 'C42', '12', 'M'). Never convert or interpret.",
  "normalized_size": "string — For trousers/jeans/shorts: look for BOTH waist and leg length on the tag and format as 'W32 L32'. If only one number is visible, record that. For suit/blazer sizes: keep bare EU numbers as-is (e.g. '54'). If already in UK format with R/L/S suffix (e.g. '44R'), keep as-is. For knitwear/shirts with EU numbers, keep as-is. For S/M/L/XL, keep as-is. For shoes: keep the size EXACTLY as printed — if the tag shows both EU and UK (e.g. 'EU 43 / UK 9'), record the UK number only (e.g. '9'). If only EU is shown, record it as-is (e.g. '43') — conversion happens downstream.",
  "trouser_waist": "string or null — for trousers/jeans/shorts only: waist measurement as on tag (e.g. '32', '34'). Null for all other items including shoes.",
  "trouser_length": "string or null — for trousers/jeans/shorts only: leg length as on tag (e.g. '32', '30'). Null for all other items including shoes.",
  "style": "string or null — the Vinted sub-genre key for this item. For jeans (men's): one of Slim / Straight / Skinny / Ripped. For jeans (women's): one of Straight / Skinny / Boyfriend / Cropped / Flared / High waisted / Ripped. For jackets: one of Denim / Bomber / Biker / Field / Fleece / Harrington / Puffer / Quilted / Shacket / Varsity / Windbreaker. For coats: one of Overcoat / Trench / Parka / Peacoat / Raincoat / Duffle. For men's boots: one of Chelsea / Desert / Wellington / Work. For women's boots: one of Ankle / Knee / Wellington. For trainers/sneakers (any gender): use 'Trainers'. For loafers: use 'Loafers'. For formal/dress shoes (oxford, derby, brogue): use 'Formal'. For court shoes / heels / pumps: use 'Court'. For sandals: use 'Sandals'. For slippers: use 'Slippers'. For mules: use 'Mules'. Infer from tag text, model name, and item shape. Null if item type has no sub-genre or it cannot be determined.",
  "cut": "string or null — the cut or fit style if labeled on the tag (e.g. 'Slim', 'Classic', 'Regular', 'Tailored'). Look for 'CUT:' or 'FIT:' on the size tag. Null if not present.",
  "materials": ["COMPLETE list of ALL fibres/materials with percentages exactly as on the care label. Include EVERY fibre listed. Format each as '50% Cotton' or '100% Merino Wool' or 'Polyester lining' etc. Check BOTH the main brand label AND the material/care label photo. Do NOT omit any fibre. Do NOT list the same fibre twice. Common fibres: wool, merino, lambswool, cashmere, cotton, linen, silk, polyester, viscose, elastane, nylon, acrylic, modal, lyocell."],
  "material_confidence": "\"high\" | \"medium\" | \"low\" — how clearly you could read the composition label. See MATERIAL CONFIDENCE rules below.",
  "material_reason": "string — one sentence: what you read on the care/composition label and why you are confident or uncertain.",
  "material_candidates": ["only if material_confidence is medium or low — 2-3 alternative possible readings, e.g. [\"80% Wool 20% Polyester\", \"80% Wool 20% Nylon\"]"],
  "pricing_sensitive_material": "boolean — true if ANY fibre in the extracted list is a premium or natural fibre where misidentification significantly affects resale value: cashmere, merino, wool, lambswool, alpaca, mohair, angora, linen, silk, leather, suede, down, velvet, tweed.",
  "fabric_mill": "string or null — if a fabric mill/supplier name is visible on the MATERIAL label (e.g. 'Tessuti Sondrio', 'Vitale Barberis Canonico', 'Loro Piana fabric'), record it here. This is NOT the brand.",
  "made_in": "string or null — country of manufacture if visible on any label (e.g. 'Italy', 'England', 'Portugal'). Look for 'Made in X' text.",
  "colour": "string — PRIMARY colour using standardised names (e.g. 'White', 'Navy', 'Charcoal'). If 3+ distinct colours: 'Multicoloured'.",
  "colour_secondary": "string or null — SECOND dominant colour if clearly a major design element (rough 15%+ of garment). Same standardised names. Null if item is effectively one colour. If colour is 'Multicoloured', set this to null.",
  "pattern": "string — the fabric/garment pattern assessed from the FRONT photo. Use one of: 'Plain', 'Pinstripe', 'Chalk stripe', 'Stripe', 'Check', 'Windowpane', 'Houndstooth', 'Herringbone', 'Tartan', 'Tweed', 'Floral', 'Abstract', 'Graphic', 'Paisley'. Use 'Plain' if solid with no visible weave pattern. Default to 'Plain' if unsure.",
  "gender": "men's | women's | unisex — infer from: (1) visible size tag (EU 34-44 = women's, EU 46-56 = men's; UK 6-16 = women's); (2) silhouette — women's blazers/jackets are shorter, fitted at waist, often curved hem; men's have broader shoulders, longer/boxier hem; (3) brand knowledge. If ambiguous (e.g. flat-lay, no size tag, unisex brand), add 'gender' to low_confidence_fields. NEVER default to men's when unsure — default to women's or unisex instead.",
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
  * TWO-LINE COMPOUND BRANDS: Some brands print across two lines. If the label shows two lines where the second line contains "&", "und", "and", "et", or an additional surname (a capitalised word that is not a model/style name), merge both lines into a single brand name. Example: label shows "HENSEL" on line 1 and "UND MORTENSEN" on line 2 → brand="Hensel und Mortensen". Example: "GIEVES" line 1 + "& HAWKES" line 2 → brand="Gieves & Hawkes". Do NOT merge if the second line is clearly a model/style name or a tagline.
- FABRIC MILLS ARE NEVER THE BRAND — this is the most common mistake. Read carefully:
  * A fabric mill is a company that WOVE THE CLOTH. Their name appears on the care/material composition label to certify the fabric quality. They did NOT make the garment.
  * The brand is the company that MADE THE GARMENT. Their label is sewn inside the collar, chest, or waistband as a woven brand label.
  * WRONG: photos show "Suit Supply" on the main woven label + "Lanificio" on the material label → brand="Lanificio" ← THIS IS WRONG
  * CORRECT: same photos → brand="Suit Supply", fabric_mill="Lanificio"
  * If you see any of these names anywhere in the photos, they are ALWAYS fabric mills — NEVER the brand. Put them in fabric_mill only:
    Lanificio, Tessuti Sondrio, Vitale Barberis Canonico, VBC, Reda, Loro Piana (as fabric supplier), Scabal, Holland & Sherry, Dormeuil, Fratelli Tallia di Delfino, Zignone, Cerruti, Drapers, Loro Piana Fabric
  * If the material label shows a mill name but the brand label is unclear, set brand=null — do NOT fall back to the mill name.
- ITEM TYPE — polo shirts vs knitwear: A polo shirt has a COLLAR + SHORT BUTTON PLACKET at the neck. Even if the fabric is cotton piqué (a knit fabric), it is STILL a "polo shirt" — NOT a jumper, sweater, or knitwear. Ralph Lauren, Lacoste, Fred Perry items with a collar are polo shirts. Only classify as jumper/knitwear if there is NO collar and the item is pulled on over the head.
- MATERIALS: Read ALL fibres from the care/composition label. OCR TAKES PRIORITY — copy the exact text you can read; do NOT infer, estimate, or substitute percentages you cannot see. Include EVERY fibre with its exact percentage as printed (e.g. "68% Wool, 22% Polyester, 10% Elastane"). Do not round or drop minor fibres. If a lining or shell is listed separately (e.g. "Shell: 100% Cotton, Lining: 100% Polyester"), include both. Check BOTH the main brand/tag photo AND the material/care label photo. If the label is partially obscured and you can only read some fibres, report exactly what is legible and set material_confidence="medium" or "low" accordingly — do not fill in the rest by inference.
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
- MATERIAL CONFIDENCE — always populate material_confidence, material_reason, and material_candidates:
  * "high": composition label clearly legible — percentages and fibre names fully visible with no ambiguity.
  * "medium": label partially obscured or small/faded print, but you can read most of it; some uncertainty about one fibre or percentage.
  * "low": label unreadable, not visible in photos, or you are guessing from context. Also use "low" if materials is empty.
  * pricing_sensitive_material: true if ANY extracted fibre is premium/natural (cashmere, merino, wool, lambswool, alpaca, mohair, angora, linen, silk, leather, suede, down, velvet, tweed). False for basic synthetics (polyester, nylon, acrylic, elastane) or cotton-only items.
  * OCR EVERY LINE separately — the composition label often has 3–5 fibres on separate lines (e.g. line 1: "46% Lambswool", line 2: "30% Silk", line 3: "15% Angora", line 4: "9% Polyamide"). Each line = one separate entry in the materials array. NEVER merge two lines into one. NEVER omit a line because the percentages already sum to 100 with fewer lines.
  * MULTILINGUAL LABELS — European labels often list each fibre in 2–4 languages on the SAME line, separated by "/" or "•": e.g. "46%LAMBSWOOL/LAMBSWOOL" or "30% SOIE / SILK / SEIDE". This is ONE fibre in multiple languages, NOT separate materials. Take the ENGLISH name (or most readable) and produce a SINGLE entry. Do NOT create separate entries for each language version of the same fibre.
  * FIBRE TRANSLATIONS (French/Italian/German → English): SOIE/SOOJA/SEIDE = Silk | LAINE/LANA/WOLLE = Wool | CACHEMIRE/KASCHMIR = Cashmere | ANGORA = Angora | MOHAIR = Mohair | COTON/COTONE/BAUMWOLLE = Cotton | LIN/LINO/LEINEN = Linen | POLYAMIDE/NYLON = Polyamide | POLYESTER = Polyester | VISCOSE/VISCOSA = Viscose | ELASTHANNE/ELASTAN = Elastane | ACRYLIQUE/ACRILICO = Acrylic | ALPAGA/ALPACA = Alpaca | LAMBSWOOL/LAINE D'AGNEAU = Lambswool
  * Do NOT include care instructions (wash symbols, temperature marks, "Machine Wash", "Dry Clean Only") in the materials list — those are care labels, not composition.
  * Populate material_candidates with 2-3 alternative fibre readings when confidence is medium or low.
- BRAND CONFIDENCE — always populate brand_confidence, brand_reason, and brand_candidates:
  * "high": brand name clearly legible on the label (e.g. large woven text "BARBOUR"), closely matches a known brand with no ambiguity.
  * "medium": text partially obscured, stylised logo font, or you can read most characters but are not fully certain (e.g. logo-heavy label, faded text).
  * "low": text illegible or heavily obscured, inferring brand only from context/style, or 2+ plausible reads exist. Also use "low" if brand is null.
  * Always populate brand_candidates with 2-3 alternative readings when confidence is medium or low.
  * sub_brand: check for a secondary line name printed below or on a separate inner tab attached to the main brand label.
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


_JPEG_QUALITY = 80

# ---------------------------------------------------------------------------
# Label auto-crop (Step 1: ENABLE_LABEL_AUTOCROP)
# Removes background/surrounding fabric from close-up label photos before
# sending to the model, reducing token cost and improving OCR accuracy.
# ---------------------------------------------------------------------------

_AUTOCROP_TOLERANCE     = 35    # pixel diff from background to count as foreground
_AUTOCROP_CONFIDENCE_MIN = 0.25  # min fraction of bbox that must be foreground
_AUTOCROP_AREA_MAX      = 0.85  # only crop if result is ≤ this fraction of original area
_AUTOCROP_PAD_FRACTION  = 0.05  # padding around detected region as fraction of each dim

# Roles that receive autocrop treatment (label/OCR photos only)
_OCR_ROLES: frozenset[str] = frozenset({"brand", "model_size", "material"})


def _autocrop_label(img: "Image.Image") -> tuple["Image.Image", dict]:
    """Detect and crop to the label/text region in a close-up label photo.

    Algorithm:
      1. Sample corner patches → estimate background brightness (median).
      2. Binary mask: pixels where |value − background| > _AUTOCROP_TOLERANCE.
      3. Dilate mask (MaxFilter 5) to connect nearby text chars into solid blobs.
      4. Find bounding box of foreground pixels.
      5. confidence = undilated_fg_count / bbox_area.
      6. If confidence ≥ threshold AND crop saves ≥ 15% area → apply with padding.
      7. Otherwise fall back to original.

    Returns (result_image, crop_meta) where crop_meta has:
      original_size   : (w, h)
      cropped_size    : (cw, ch) — same as original_size when fallback
      crop_applied    : bool
      crop_confidence : float 0–1
      fallback_used   : bool
    """
    from PIL import Image, ImageFilter

    w, h = img.size

    def _no_crop(conf: float) -> tuple:
        return img, {
            "original_size": (w, h), "cropped_size": (w, h),
            "crop_applied": False, "crop_confidence": round(conf, 3), "fallback_used": True,
        }

    if w < 32 or h < 32:
        return _no_crop(1.0)

    grey = img.convert("L")

    # Background estimate: median of corner patch pixels (~5% of shortest dim, min 4px)
    patch = max(4, min(w, h) // 20)
    corner_vals: list[int] = []
    for cy, cx in [(0, 0), (0, w - patch), (h - patch, 0), (h - patch, w - patch)]:
        region = grey.crop((cx, cy, min(cx + patch, w), min(cy + patch, h)))
        corner_vals.extend(region.tobytes())  # bytes() works for "L" mode; each byte = pixel 0–255
    corner_vals.sort()
    bg_val = corner_vals[len(corner_vals) // 2]  # median

    # Binary mask — vectorised via PIL point() (lookup table, only 256 evaluations)
    table = [255 if abs(v - bg_val) > _AUTOCROP_TOLERANCE else 0 for v in range(256)]
    mask = grey.point(table, "L")

    # Dilate (5×5 max filter = 2px radius) to merge nearby characters
    mask_dilated = mask.filter(ImageFilter.MaxFilter(5))
    bbox = mask_dilated.getbbox()
    if not bbox:
        return _no_crop(0.0)

    x1, y1, x2, y2 = bbox
    bbox_area = (x2 - x1) * (y2 - y1)
    if bbox_area == 0:
        return _no_crop(0.0)

    # Confidence = fraction of (undilated) bbox that is genuinely foreground
    fg_count = sum(1 for v in mask.crop((x1, y1, x2, y2)).tobytes() if v > 0)
    confidence = fg_count / bbox_area

    if confidence < _AUTOCROP_CONFIDENCE_MIN:
        return _no_crop(round(confidence, 3))

    # Add padding so we don't clip the label edge
    pad_x = max(4, int(w * _AUTOCROP_PAD_FRACTION))
    pad_y = max(4, int(h * _AUTOCROP_PAD_FRACTION))
    x1 = max(0, x1 - pad_x)
    y1 = max(0, y1 - pad_y)
    x2 = min(w, x2 + pad_x)
    y2 = min(h, y2 + pad_y)

    crop_w, crop_h = x2 - x1, y2 - y1
    area_ratio = (crop_w * crop_h) / (w * h)

    if area_ratio > _AUTOCROP_AREA_MAX:
        # Crop doesn't remove enough background — not worth it
        return img, {
            "original_size": (w, h), "cropped_size": (w, h),
            "crop_applied": False, "crop_confidence": round(confidence, 3), "fallback_used": True,
        }

    cropped = img.crop((x1, y1, x2, y2))
    return cropped, {
        "original_size": (w, h),
        "cropped_size": (crop_w, crop_h),
        "crop_applied": True,
        "crop_confidence": round(confidence, 3),
        "fallback_used": False,
    }


def _compress_with_autocrop(path: Path, max_dim: int) -> tuple[str, str, dict]:
    """Autocrop to label region (if ENABLE_LABEL_AUTOCROP) then compress.

    Used for OCR-critical photos (brand, model_size, material).
    Returns (b64_data, media_type, crop_meta).
    """
    try:
        from PIL import Image
        img = Image.open(path).convert("RGB")

        if ENABLE_LABEL_AUTOCROP:
            img, crop_meta = _autocrop_label(img)
        else:
            w, h = img.size
            crop_meta = {
                "original_size": (w, h), "cropped_size": (w, h),
                "crop_applied": False, "crop_confidence": 1.0, "fallback_used": False,
            }

        w, h = img.size
        if max(w, h) > max_dim:
            scale = max_dim / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
        data = base64.standard_b64encode(buf.getvalue()).decode()
        return data, "image/jpeg", crop_meta
    except ImportError:
        data, media_type = _compress_image(path, max_dim)
        return data, media_type, {
            "original_size": (0, 0), "cropped_size": (0, 0),
            "crop_applied": False, "crop_confidence": 0.0, "fallback_used": True,
        }


# Per-role max resolution policy:
#   overview photos (garment shots) → 768px  — saves tokens, resolution not needed
#   label/OCR photos (tags, care labels) → 1024px — must read small printed text
_PHOTO_MAX_DIM: dict[str, int] = {
    "front":      768,   # overview
    "back":       768,   # overview (kept here in case re-added)
    "brand":      1024,  # OCR — brand label text
    "model_size": 1024,  # OCR — size/model tag text
    "material":   1024,  # OCR — care/composition label text
}
_DEFAULT_MAX_DIM = 768  # any extra/unknown photo treated as overview


def _compress_image(path: Path, max_dim: int | None = None) -> tuple[str, str]:
    """Resize and compress an image, returning (base64_data, media_type).

    max_dim defaults to _DEFAULT_MAX_DIM unless the caller supplies a role-specific value.
    """
    effective_max = max_dim if max_dim is not None else _DEFAULT_MAX_DIM
    try:
        from PIL import Image
        img = Image.open(path)
        img = img.convert("RGB")
        w, h = img.size
        if max(w, h) > effective_max:
            scale = effective_max / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
        return base64.standard_b64encode(buf.getvalue()).decode(), "image/jpeg"
    except ImportError:
        # Pillow not installed — fall back to raw bytes (no resize)
        data = base64.standard_b64encode(path.read_bytes()).decode()
        ext = path.suffix.lower()
        media_type = "image/jpeg" if ext in {".jpg", ".jpeg"} else f"image/{ext.lstrip('.')}"
        return data, media_type


def _load_photos(folder: Path) -> tuple[list[dict], dict[str, dict]]:
    """Load core analysis photos (front/brand/model_size/material) from folder.

    OCR-critical photos (brand, model_size, material) are auto-cropped to the
    label region before compression when ENABLE_LABEL_AUTOCROP is set.

    Returns:
        (image_blocks, crop_report) where crop_report maps role → crop metadata.
    """
    blocks: list[dict] = []
    crop_report: dict[str, dict] = {}
    extensions = {".jpg", ".jpeg", ".png", ".webp"}

    for name in CORE_PHOTOS:
        for ext in extensions:
            candidate = folder / f"{name}{ext}"
            if candidate.exists():
                max_dim = _PHOTO_MAX_DIM.get(name, _DEFAULT_MAX_DIM)
                if name in _OCR_ROLES:
                    data, media_type, crop_meta = _compress_with_autocrop(candidate, max_dim)
                    crop_report[name] = crop_meta
                else:
                    data, media_type = _compress_image(candidate, max_dim)
                blocks.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": data},
                })
                break

    if not blocks:
        raise FileNotFoundError(f"No core photos found in {folder}")
    return blocks, crop_report


def _extract_claude(photos: list[dict], model: str, prompt: str) -> tuple[dict, dict]:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    content = photos + [{"type": "text", "text": prompt}]
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": content}],
    )
    raw = response.content[0].text.strip()
    # Strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
    usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens, "model": model}
    return _safe_json_loads(raw), usage


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
    return _safe_json_loads(raw)


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


# Premium brands where a medium-confidence OCR read still warrants a re-read,
# because getting the brand wrong has a significant impact on resale price.
_REREAD_PREMIUM_BRANDS: frozenset[str] = frozenset({
    # Luxury tailoring — wrong brand = £100s price difference
    "brioni", "kiton", "cesare attolini", "isaia", "canali", "corneliani",
    "ermenegildo zegna", "boglioli", "caruso",
    # Premium outerwear
    "moncler", "canada goose", "stone island", "cp company",
    "arc'teryx", "arcteryx", "belstaff",
    # Premium casualwear
    "represent", "acne studios", "ami paris", "maison margiela", "kenzo",
    # Heritage British — brand name drives price
    "barbour", "hackett",
})


def _should_reread_brand(result: dict) -> bool:
    """Return True if brand should be confirmed via a dedicated label re-read.

    Gate logic (in priority order):
      always:  brand is None                           → reread
      always:  brand_confidence == "low"               → reread
      maybe:   brand_confidence == "medium"            → reread only for premium brands
      never:   brand_confidence == "high"              → skip reread
    """
    if result.get("brand") is None:
        return True
    # Default to "low" if the field is missing (e.g. old cached result)
    confidence = result.get("brand_confidence", "low")
    if confidence == "low":
        return True
    if confidence == "medium":
        brand_lower = (result.get("brand") or "").lower()
        return brand_lower in _REREAD_PREMIUM_BRANDS
    return False  # "high" → trust the main extraction


# Fibres where misidentification significantly affects resale price.
# "wool" includes standard wool where acrylic masquerading as wool is a real OCR risk.
_PRICING_SENSITIVE_FIBRES: frozenset[str] = frozenset({
    "cashmere", "merino", "lambswool", "alpaca", "mohair", "angora",
    "wool",    # standard wool still matters vs acrylic/synthetic
    "linen",   # natural fibre — buyers care, blends matter
    "silk",    # premium — easily confused with satin/viscose
    "leather", "suede",   # real vs faux is a huge price difference
    "down",    # fill vs synthetic insulation
    "velvet",  # fabric type matters
    "tweed",   # heritage fabric — buyers search for it
})

# Item types where material composition affects resale price enough to warrant
# a reread even at medium material confidence.
_PRICING_SENSITIVE_ITEM_TYPES: frozenset[str] = frozenset({
    "blazer", "suit", "jacket", "coat",           # tailoring / outerwear
    "jumper", "sweater", "knitwear", "pullover",  # knitwear — cashmere vs acrylic
    "trouser", "trousers",                         # tailored trousers — wool vs poly
    "dress", "skirt",                              # occasion wear — silk vs poly
})


def _should_reread_material(result: dict) -> bool:
    """Return True if material composition should be re-read from the label photo.

    Gate logic:
      always:  materials empty / None              → reread (label not read at all)
      always:  material_confidence == "low"        → reread
      maybe:   material_confidence == "medium"     → reread if pricing-sensitive material or item type
      never:   material_confidence == "high"       → skip
    """
    if not result.get("materials"):
        return True
    # Default to "low" if field is missing (backward compat)
    confidence = result.get("material_confidence", "low")
    if confidence == "low":
        return True
    if confidence == "high":
        return False
    # "medium" — reread if premium/natural fibre or pricing-sensitive item type
    # 1. Model's own flag
    if result.get("pricing_sensitive_material"):
        return True
    # 2. Deterministic check: scan extracted materials for premium fibres
    materials_str = " ".join(result.get("materials") or []).lower()
    if any(f in materials_str for f in _PRICING_SENSITIVE_FIBRES):
        return True
    # 3. Item type gate: even basic fabric compositions matter for tailoring/knitwear
    item_type_lower = (result.get("item_type") or "").lower()
    if any(kw in item_type_lower for kw in _PRICING_SENSITIVE_ITEM_TYPES):
        return True
    return False  # medium confidence, non-premium material, basic item → skip


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


def _reread_material_photo(folder: Path, model: str, full_reread: bool = False) -> dict | None:
    """Single-photo targeted re-read of the material label photo.

    full_reread=False (default): targeted fabric_mill-only read.
        Returns {"fabric_mill": str_or_null}

    full_reread=True: full composition + fabric_mill read, used when
        material_confidence is low/medium on a pricing-sensitive item.
        Returns {"materials": [...], "fabric_mill": str_or_null}
    """
    for base in ("material", "model_size"):
        for ext_suffix in (".jpg", ".jpeg", ".png", ".webp"):
            mat_photo = folder / f"{base}{ext_suffix}"
            if mat_photo.exists():
                data, media_type, _ = _compress_with_autocrop(mat_photo, max_dim=1024)
                client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

                if full_reread:
                    prompt_text = (
                        "Look at this clothing care/material label photo carefully.\n"
                        "1. Read ALL fibre/material composition percentages EXACTLY as printed. "
                        "Format each entry as '68% Wool' or '100% Cotton' etc. "
                        "Include EVERY fibre listed, including lining if shown separately. "
                        "Do NOT include care instructions (wash symbols, 'Machine Wash', 'Dry Clean Only', "
                        "temperature numbers, tumble-dry icons) — only fibre composition.\n"
                        "IMPORTANT — MULTILINGUAL LABELS: European labels often print each fibre in 2-4 languages "
                        "on the SAME LINE separated by '/': e.g. '30% SOIE / SILK / SEIDE' or '15% ANGORA / ANGORA'. "
                        "This is ONE fibre in multiple languages. Take the English name and make ONE entry. "
                        "Do NOT create separate entries for each language version. "
                        "Each physical LINE on the label = one material entry.\n"
                        "FIBRE TRANSLATIONS: SOIE/SEIDE=Silk | LAINE/LANA/WOLLE=Wool | CACHEMIRE/KASCHMIR=Cashmere | "
                        "ANGORA=Angora | COTON/COTONE/BAUMWOLLE=Cotton | LIN/LINO/LEINEN=Linen | "
                        "POLYAMIDE/NYLON=Polyamide | VISCOSE=Viscose | ELASTHANNE/ELASTAN=Elastane | "
                        "ALPAGA/ALPACA=Alpaca | LAMBSWOOL/LAINE D'AGNEAU=Lambswool\n"
                        "2. Look for a fabric mill or cloth supplier name "
                        "(e.g. Tessuti Sondrio, Vitale Barberis Canonico, VBC, Reda, Loro Piana, "
                        "Cerruti, Lanificio, Scabal, Holland & Sherry, Dormeuil, Zignone, Drapers).\n"
                        'Return only JSON: {"materials": ["list of fibres exactly as on label"], '
                        '"fabric_mill": "NAME or null"}'
                    )
                    max_tokens = 150
                else:
                    prompt_text = (
                        "Look at this clothing care/material label photo carefully. "
                        "Is there a fabric mill or cloth supplier name printed on it? "
                        "Known fabric mill names to look for: Cerruti, Lanificio, Tessuti Sondrio, "
                        "Vitale Barberis Canonico, VBC, Reda, Loro Piana, Scabal, Holland & Sherry, "
                        "Dormeuil, Fratelli Tallia di Delfino, Zignone, Drapers. "
                        'Return only JSON: {"fabric_mill": "EXACT NAME"} or {"fabric_mill": null} if none visible.'
                    )
                    max_tokens = 60

                response = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
                            {"type": "text", "text": prompt_text},
                        ],
                    }],
                )
                raw = response.content[0].text.strip()
                raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
                try:
                    start = raw.index("{")
                    raw = _escape_json_strings(raw)
                    raw = re.sub(r",\s*([}\]])", r"\1", raw)
                    result, _ = json.JSONDecoder().raw_decode(raw, start)
                    return result
                except Exception:
                    pass  # try next candidate photo
                break  # photo found for this base; don't try other extensions
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
            data, media_type, _ = _compress_with_autocrop(brand_photo, max_dim=1024)
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
                            '2. TWO-LINE COMPOUND BRANDS: If the label shows two lines and the second '
                            'line contains "&", "und", "and", "et", or an additional surname, merge them '
                            'into one brand name. Example: "HENSEL" + "UND MORTENSEN" → "Hensel und Mortensen". '
                            'Example: "GIEVES" + "& HAWKES" → "Gieves & Hawkes".\n'
                            '3. Look for any SMALL SECONDARY TABS or additional labels attached nearby '
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
                return _safe_json_loads(raw)
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
    Result includes '_extract_log' key with observability data — callers should
    pop it (item.pop('_extract_log', {})) before saving listing.json.
    """
    import time
    _t_start = time.perf_counter()

    folder = Path(item_folder) if not isinstance(item_folder, Path) else item_folder
    if not folder.is_absolute():
        folder = ITEMS_DIR / folder

    # Track which core photos are present (for run log)
    _photos_found: list[str] = []
    for _name in CORE_PHOTOS:
        for _ext in (".jpg", ".jpeg", ".png", ".webp"):
            if (folder / f"{_name}{_ext}").exists():
                _photos_found.append(_name)
                break

    photos, crop_report = _load_photos(folder)
    # Log auto-crop results for OCR photos
    for role, meta in crop_report.items():
        if meta.get("crop_applied"):
            ow, oh = meta["original_size"]
            cw, ch = meta["cropped_size"]
            pct = 100 * (1 - (cw * ch) / (ow * oh)) if ow * oh > 0 else 0
            print(f"  Auto-crop {role}: {ow}×{oh} → {cw}×{ch} (-{pct:.0f}%, conf={meta['crop_confidence']:.2f})")

    prompt = _build_prompt_with_hints(hints or {})

    _escalated = False
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
        _escalated = True

    # Deterministic safety net: move any fabric mill that landed in brand → fabric_mill
    result = _sanitise_brand(result)

    # -----------------------------------------------------------------------
    # Parallel rereads (Step 3: ENABLE_PARALLEL_REREADS)
    # If both brand and material rereads are needed, run them concurrently.
    # Each reread is isolated — failure of one never fails the other.
    # -----------------------------------------------------------------------
    _do_brand_reread    = VISION_PROVIDER != "gemini-flash" and _should_reread_brand(result)
    _do_material_full   = VISION_PROVIDER != "gemini-flash" and _should_reread_material(result)
    _do_material_mill   = (
        VISION_PROVIDER != "gemini-flash"
        and not _do_material_full
        and not result.get("fabric_mill")
    )

    # Capture reread reasons for run log
    _reread_brand_reason: str | None = None
    _reread_mat_reason: str | None = None

    # Log what will be triggered
    if _do_brand_reread:
        reason = result.get("brand_confidence", "low")
        _reread_brand_reason = f"brand_confidence={reason}"
        print(f"  Brand re-read triggered (confidence={reason}, brand={result.get('brand')!r})")
    else:
        if result.get("brand_confidence") == "high":
            print(f"  Brand re-read skipped (confidence=high, brand={result.get('brand')!r})")
    if _do_material_full:
        conf = result.get("material_confidence", "low")
        _reread_mat_reason = f"material_confidence={conf} (full reread)"
        print(f"  Material re-read triggered (confidence={conf}, materials={result.get('materials')})")
    elif _do_material_mill:
        _reread_mat_reason = "mill-only (no fabric_mill set)"
        print(f"  Material re-read skipped (confidence=high); checking for fabric_mill only")
    else:
        if not _do_material_full:
            print(f"  Material re-read skipped (confidence=high, fabric_mill already set)")

    # Decide whether to use parallel execution path
    _use_parallel = (
        ENABLE_PARALLEL_REREADS
        and _do_brand_reread
        and (_do_material_full or _do_material_mill)
    )

    _t_start = time.perf_counter()
    _reread_brand_result   = None
    _reread_mat_result     = None
    _reread_brand_error    = None
    _reread_mat_error      = None

    if _use_parallel:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _brand_task():
            return _reread_brand_photo(folder, HAIKU_MODEL)

        def _mat_task():
            full = _do_material_full
            return _reread_material_photo(folder, HAIKU_MODEL, full_reread=full)

        with ThreadPoolExecutor(max_workers=2) as _pool:
            _fut_brand = _pool.submit(_brand_task)
            _fut_mat   = _pool.submit(_mat_task)
            for _fut in as_completed((_fut_brand, _fut_mat)):
                try:
                    if _fut is _fut_brand:
                        _reread_brand_result = _fut.result()
                    else:
                        _reread_mat_result = _fut.result()
                except Exception as _e:
                    if _fut is _fut_brand:
                        _reread_brand_error = _e
                        print(f"  Brand re-read FAILED: {_e}")
                    else:
                        _reread_mat_error = _e
                        print(f"  Material re-read FAILED: {_e}")
        print(f"  Parallel re-reads completed in {time.perf_counter() - _t_start:.2f}s")
    else:
        # Sequential path: brand first, then material
        if _do_brand_reread:
            try:
                _reread_brand_result = _reread_brand_photo(folder, HAIKU_MODEL)
            except Exception as _e:
                _reread_brand_error = _e
                print(f"  Brand re-read FAILED: {_e}")
        if _do_material_full or _do_material_mill:
            try:
                _reread_mat_result = _reread_material_photo(
                    folder, HAIKU_MODEL, full_reread=_do_material_full
                )
            except Exception as _e:
                _reread_mat_error = _e
                print(f"  Material re-read FAILED: {_e}")

    # Apply brand reread result
    if _do_brand_reread and _reread_brand_result and _reread_brand_result.get("brand"):
        old_brand = result.get("brand")
        new_brand = _apply_brand_corrections(_reread_brand_result["brand"])
        if new_brand != old_brand:
            print(f"  Brand re-read: '{old_brand}' -> '{new_brand}'")
        result["brand"] = new_brand
        result["brand_confidence"] = "high"
        result["low_confidence_fields"] = [
            f for f in result.get("low_confidence_fields", []) if f != "brand"
        ]
        extra_kws = _reread_brand_result.get("collection_keywords") or []
        if extra_kws:
            existing = result.get("tag_keywords") or []
            merged = existing + [k for k in extra_kws if k not in existing]
            result["tag_keywords"] = merged
            if result.get("tag_keywords_confidence") != "high":
                result["tag_keywords_confidence"] = "high"
            print(f"  Collection keywords from brand photo: {extra_kws}")

    # Apply material reread result
    if (_do_material_full or _do_material_mill) and _reread_mat_result:
        if _do_material_full and _reread_mat_result.get("materials"):
            old_mats = result.get("materials")
            result["materials"] = _reread_mat_result["materials"]
            result["material_confidence"] = "high"
            result["low_confidence_fields"] = [
                f for f in result.get("low_confidence_fields", []) if f != "materials"
            ]
            if _reread_mat_result["materials"] != old_mats:
                print(f"  Materials updated: {_reread_mat_result['materials']}")
        if _reread_mat_result.get("fabric_mill") and not result.get("fabric_mill"):
            print(f"  Fabric mill re-read: '{_reread_mat_result['fabric_mill']}'")
            result["fabric_mill"] = _reread_mat_result["fabric_mill"]

    # Deterministic brand correction as fallback (catches misreads without brand photo)
    result["brand"] = _apply_brand_corrections(result.get("brand"))

    # If made_in is uncertain, clear it — a wrong country is worse than none
    if "made_in" in result.get("low_confidence_fields", []):
        result["made_in"] = None

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

    # Build observability log — popped by web.py before saving listing.json
    result["_extract_log"] = {
        "photos_found": _photos_found,
        "crop_applied": {k: v.get("crop_applied", False) for k, v in crop_report.items()},
        "escalated": _escalated,
        "extract_latency_ms": round((time.perf_counter() - _t_start) * 1000),
        "extract_input_tokens": usage.get("input_tokens", 0),
        "extract_output_tokens": usage.get("output_tokens", 0),
        "extract_model": usage.get("model", ""),
        "rereads_triggered": {
            "brand": _do_brand_reread,
            "material_full": _do_material_full,
            "material_mill": _do_material_mill,
        },
        "reread_reasons": {k: v for k, v in {
            "brand": _reread_brand_reason,
            "material": _reread_mat_reason,
        }.items() if v},
        "parallel_used": _use_parallel,
        "reread_errors": {k: str(v) for k, v in {
            "brand": _reread_brand_error,
            "material": _reread_mat_error,
        }.items() if v},
        "rereads_count": int(_do_brand_reread) + int(_do_material_full or _do_material_mill),
    }

    return result, usage
