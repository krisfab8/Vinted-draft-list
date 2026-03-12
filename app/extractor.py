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

Analyse the provided photos (front, tag/size label, material label, back) and return a JSON object with these fields:

{
  "brand": "string or null — the MANUFACTURER/LABEL name only (e.g. 'Suit Supply', 'Barbour', 'Hugo Boss'). NOT the model or style name.",
  "model_name": "string or null — the style/model/fit name if visible on tag (e.g. 'Brentwood', 'Lennon', 'Slim'). Separate from brand.",
  "item_type": "string (e.g. wax jacket, lambswool jumper, wool trousers)",
  "tagged_size": "string — EXACTLY as printed on tag (e.g. '52', 'W32 L32', 'C42', '12', 'M'). Never convert or interpret.",
  "normalized_size": "string — For trousers/jeans/shorts: look for BOTH waist and leg length on the tag and format as 'W32 L32'. If only one number is visible, record that. For suit/blazer sizes: keep bare EU numbers as-is (e.g. '54'). If already in UK format with R/L/S suffix (e.g. '44R'), keep as-is. For knitwear/shirts with EU numbers, keep as-is. For S/M/L/XL, keep as-is.",
  "trouser_waist": "string or null — for trousers/jeans/shorts only: waist measurement as on tag (e.g. '32', '34'). Null for all other items.",
  "trouser_length": "string or null — for trousers/jeans/shorts only: leg length as on tag (e.g. '32', '30'). Null for all other items.",
  "materials": ["list of materials, e.g. waxed cotton, polyester lining"],
  "colour": "string",
  "gender": "men's | women's | unisex",
  "condition_summary": "one sentence, honest assessment",
  "flaws_note": "string or null — any visible damage, stains, repairs",
  "confidence": 0.0–1.0,
  "low_confidence_fields": ["list of field names where you are uncertain"]
}

Rules:
- Use ONLY information visible in the photos. Do not guess.
- IMPORTANT: brand = the company/label that made the item. On multi-line tags, look for the main brand name, not model names, style names, or collection names printed beneath it.
- MATERIALS: check BOTH the main label/tag photo AND any separate material composition photo — different brands put this information on different labels. Some only have it on a small inner label. Combine what you see across all photos. Common fibre names to look for: wool, linen, cotton, cashmere, silk, polyester, viscose, elastane, nylon, lambswool, merino.
- If a field is not visible or unreadable, set it to null and add it to low_confidence_fields. Do NOT guess.
- confidence is your overall certainty across all fields (1.0 = fully certain).
- Return valid JSON only — no markdown, no explanation.
""".strip()


_MAX_DIMENSION = 1568  # Anthropic recommended max for vision
_JPEG_QUALITY = 85


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


def _extract_claude(photos: list[dict], model: str) -> tuple[dict, dict]:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    content = photos + [{"type": "text", "text": _EXTRACT_PROMPT}]
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": content}],
    )
    raw = response.content[0].text.strip()
    # Strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
    usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens, "model": model}
    return json.loads(raw), usage


def _extract_gemini(photos: list[dict]) -> dict:
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
    parts.append({"text": _EXTRACT_PROMPT})

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


def extract(item_folder: str | Path) -> dict:
    """
    Extract structured item data from photos in item_folder.

    Returns a dict ready to pass to listing_writer.write().
    Escalates to Sonnet if confidence is below threshold.
    """
    folder = Path(item_folder) if not isinstance(item_folder, Path) else item_folder
    if not folder.is_absolute():
        folder = ITEMS_DIR / folder

    photos = _load_photos(folder)

    if VISION_PROVIDER == "gemini-flash":
        if not GOOGLE_AI_API_KEY:
            raise EnvironmentError("GOOGLE_AI_API_KEY required for gemini-flash provider")
        result = _extract_gemini(photos)
        usage = {"input_tokens": 0, "output_tokens": 0, "model": "gemini-flash"}
    else:
        result, usage = _extract_claude(photos, HAIKU_MODEL)

    # Escalate to Sonnet if confidence is low (Claude providers only)
    confidence = result.get("confidence", 1.0)
    if confidence < CONFIDENCE_THRESHOLD and VISION_PROVIDER != "gemini-flash":
        print(f"Low confidence ({confidence:.2f}), escalating to {SONNET_MODEL}")
        result, usage = _extract_claude(photos, SONNET_MODEL)

    result["photos_folder"] = str(folder)
    return result, usage
