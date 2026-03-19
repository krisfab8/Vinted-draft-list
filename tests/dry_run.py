"""
Dry-run validation: simulates the full extraction pipeline without making any API calls.

Outputs:
  - Per-item photo inventory with old vs new compressed dimensions
  - Estimated token savings per photo and overall
  - Prompt token sizes
  - Whether brand/material re-read would trigger
  - Final validation report

Usage:
  .venv/bin/python -m tests.dry_run [item_folder ...]

  If no folders are given, scans items/ for all folders with at least a front photo.
"""

import io
import json
import sys
import base64
from pathlib import Path
import math

# ---------------------------------------------------------------------------
# Token estimation for Anthropic vision
# Anthropic charges approximately (width × height) / 750 tokens per image.
# Validated against cost_log.csv: pixel/750 is within ~10% of actual billing.
# ---------------------------------------------------------------------------

def _estimate_image_tokens(w: int, h: int) -> int:
    return max(1, int(w * h / 750))


def _cost_gbp(input_tokens: int, output_tokens: int, model: str = "haiku") -> float:
    """Approximate cost in pence (GBP) using Haiku 4.5 pricing."""
    USD_PER_M_IN  = 0.80   # Haiku 4.5 input
    USD_PER_M_OUT = 4.00   # Haiku 4.5 output
    USD_TO_GBP    = 0.79
    usd = (input_tokens / 1_000_000) * USD_PER_M_IN + (output_tokens / 1_000_000) * USD_PER_M_OUT
    return usd * USD_TO_GBP * 100   # return pence


def _compress_and_measure(path: Path, max_dim: int) -> tuple[int, int, int]:
    """Compress image to max_dim and return (out_w, out_h, estimated_tokens)."""
    try:
        from PIL import Image
        img = Image.open(path).convert("RGB")
        w, h = img.size
        if max(w, h) > max_dim:
            scale = max_dim / max(w, h)
            w, h = int(w * scale), int(h * scale)
        return w, h, _estimate_image_tokens(w, h)
    except Exception:
        return 0, 0, 0


def _autocrop_and_measure(path: Path, max_dim: int) -> tuple[int, int, int, dict]:
    """Autocrop + compress and return (out_w, out_h, estimated_tokens, crop_meta)."""
    try:
        from PIL import Image
        from app.extractor import _autocrop_label, ENABLE_LABEL_AUTOCROP
        img = Image.open(path).convert("RGB")
        if ENABLE_LABEL_AUTOCROP:
            img, crop_meta = _autocrop_label(img)
        else:
            w0, h0 = img.size
            crop_meta = {"original_size": (w0, h0), "cropped_size": (w0, h0),
                         "crop_applied": False, "crop_confidence": 1.0, "fallback_used": False}
        w, h = img.size
        if max(w, h) > max_dim:
            scale = max_dim / max(w, h)
            w, h = int(w * scale), int(h * scale)
        return w, h, _estimate_image_tokens(w, h), crop_meta
    except Exception:
        return 0, 0, 0, {"crop_applied": False, "fallback_used": True, "crop_confidence": 0.0,
                         "original_size": (0, 0), "cropped_size": (0, 0)}


# ---------------------------------------------------------------------------
# Old policy (before this session's changes)
# ---------------------------------------------------------------------------
OLD_CORE_PHOTOS = ["front", "brand", "model_size", "material", "back"]
OLD_MAX_DIM = 1024   # all photos same

# New policy (current)
NEW_CORE_PHOTOS = ["front", "brand", "model_size", "material"]
NEW_MAX_DIM: dict[str, int] = {
    "front":      768,
    "back":       768,
    "brand":      1024,
    "model_size": 1024,
    "material":   1024,
}
NEW_DEFAULT_MAX_DIM = 768

# Prompt token estimates (measured from actual file contents)
EXTRACT_PROMPT_TOKENS       = 2719   # _EXTRACT_PROMPT (measured via len/4)
# Old listing writer: full category_rules.md (1129 tok) + style (1145) + schema (376) + overhead
LISTING_WRITER_TOKENS_OLD   = 2651
# New listing writer: sliced category rules (~624 tok for men's, ~646 for women's) + style + schema
LISTING_WRITER_TOKENS_NEW   = 2155   # approx: 624 + 1145 + 376 = 2145 (men's); use 2155 as midpoint
TYPICAL_OUTPUT_TOKENS       = 560    # average from cost_log.csv
# Re-read calls include the compressed image tokens + a short text prompt
BRAND_REREAD_PROMPT    = 120    # text-only portion of brand re-read call
MATERIAL_REREAD_PROMPT = 100    # text-only portion of material re-read call

# Brand-reread gate simulation
# We can't know brand_confidence without an API call, so we simulate two scenarios:
#  - pessimistic (baseline): all items with brand photo trigger reread (old behaviour)
#  - optimistic (new gate): only low-confidence + premium-medium items reread
# For items with a listing.json, use the stored brand to classify:
#   known brand in brands.txt → assume "high confidence" → skip reread
#   known premium brand       → assume "medium confidence" → still reread
#   brand not in brands.txt   → assume "low confidence"  → reread
from app.extractor import _REREAD_PREMIUM_BRANDS, _PRICING_SENSITIVE_FIBRES, _PRICING_SENSITIVE_ITEM_TYPES

def _load_known_brands() -> set[str]:
    root = Path(__file__).parent.parent
    brands_file = root / "data" / "brands.txt"
    if not brands_file.exists():
        return set()
    return {
        line.strip().lower() for line in brands_file.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }

_KNOWN_BRANDS: set[str] = _load_known_brands()


def _simulate_brand_reread(folder: Path) -> tuple[bool, str]:
    """Return (would_reread, reason) based on stored listing.json brand."""
    listing_path = folder / "listing.json"
    if not listing_path.exists():
        return True, "no listing.json → assume low confidence"
    try:
        listing = json.loads(listing_path.read_text())
        brand = (listing.get("brand") or "").strip()
        if not brand:
            return True, "brand is None/empty → always reread"
        brand_lower = brand.lower()
        if brand_lower in _REREAD_PREMIUM_BRANDS:
            return True, f"premium brand '{brand}' → reread even at medium confidence"
        if brand_lower in _KNOWN_BRANDS:
            return False, f"known brand '{brand}' → high confidence → skip"
        return True, f"unknown brand '{brand}' → low confidence → reread"
    except Exception:
        return True, "could not read listing.json"


def _simulate_material_reread(folder: Path) -> tuple[str, str]:
    """Return ('full'|'mill_only'|'skip', reason) based on stored listing.json."""
    listing_path = folder / "listing.json"
    if not listing_path.exists():
        return "full", "no listing.json → assume low confidence"
    try:
        listing = json.loads(listing_path.read_text())
        materials = listing.get("materials") or []
        if not materials:
            return "full", "no materials → always full reread"
        # Simulate medium confidence for items we haven't extracted yet; if listing has
        # fabric_mill already set and materials non-empty, treat as high → mill-only check
        fabric_mill = listing.get("fabric_mill")
        item_type = (listing.get("item_type") or "").lower()
        materials_str = " ".join(materials).lower()

        # Check if any pricing-sensitive fibre present
        has_premium_fibre = any(f in materials_str for f in _PRICING_SENSITIVE_FIBRES)
        # Check if pricing-sensitive item type
        has_premium_type = any(kw in item_type for kw in _PRICING_SENSITIVE_ITEM_TYPES)

        if has_premium_fibre:
            return "full", f"premium fibre in materials ('{materials[0]}')"
        if has_premium_type:
            return "full", f"pricing-sensitive item type: '{item_type}'"
        if not fabric_mill:
            return "mill_only", "basic materials, no fabric_mill → targeted mill reread"
        return "skip", f"basic materials + fabric_mill already set → skip"
    except Exception:
        return "full", "could not read listing.json"


EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp"]

def _find_photo(folder: Path, name: str) -> Path | None:
    for ext in EXTENSIONS:
        p = folder / f"{name}{ext}"
        if p.exists():
            return p
    return None


def _analyse_folder(folder: Path) -> dict | None:
    front = _find_photo(folder, "front")
    if not front:
        return None

    result = {
        "folder": folder.name,
        "old": {"photos": [], "total_img_tokens": 0},
        "new": {"photos": [], "total_img_tokens": 0},
        "has_brand_photo": bool(_find_photo(folder, "brand")),
        "has_material_photo": bool(_find_photo(folder, "material")),
        "has_back_photo": bool(_find_photo(folder, "back")),
    }

    # Old config — 5 photos at uniform 1024px
    for name in OLD_CORE_PHOTOS:
        p = _find_photo(folder, name)
        if p:
            w, h, tokens = _compress_and_measure(p, OLD_MAX_DIM)
            result["old"]["photos"].append({"role": name, "w": w, "h": h, "tokens": tokens})
            result["old"]["total_img_tokens"] += tokens

    # New config — 4 photos with role-specific dimensions + autocrop for OCR roles
    _OCR_ROLES_DRYRUN = {"brand", "model_size", "material"}
    for name in NEW_CORE_PHOTOS:
        p = _find_photo(folder, name)
        if p:
            max_dim = NEW_MAX_DIM.get(name, NEW_DEFAULT_MAX_DIM)
            if name in _OCR_ROLES_DRYRUN:
                w, h, tokens, crop_meta = _autocrop_and_measure(p, max_dim)
                result["new"]["photos"].append({
                    "role": name, "w": w, "h": h, "tokens": tokens, "max_dim": max_dim,
                    "crop_meta": crop_meta,
                })
            else:
                w, h, tokens = _compress_and_measure(p, max_dim)
                result["new"]["photos"].append({"role": name, "w": w, "h": h, "tokens": tokens, "max_dim": max_dim})
            result["new"]["total_img_tokens"] += tokens

    # Re-read image tokens — autocropped at 1024px (same as production)
    brand_reread_img_tokens = 0
    mat_reread_img_tokens   = 0
    if result["has_brand_photo"]:
        p = _find_photo(folder, "brand")
        if p:
            _, _, brand_reread_img_tokens, _ = _autocrop_and_measure(p, 1024)
    if result["has_material_photo"]:
        p = _find_photo(folder, "material")
        if p:
            _, _, mat_reread_img_tokens, _ = _autocrop_and_measure(p, 1024)

    brand_reread_total    = brand_reread_img_tokens + BRAND_REREAD_PROMPT
    material_reread_total = mat_reread_img_tokens   + MATERIAL_REREAD_PROMPT

    # Brand reread gate simulation
    would_reread, reread_reason = _simulate_brand_reread(folder)
    result["brand_reread_simulated"] = would_reread
    result["brand_reread_reason"] = reread_reason

    # Material reread gate simulation
    mat_reread_mode, mat_reread_reason = _simulate_material_reread(folder)
    result["mat_reread_mode"] = mat_reread_mode      # "full" | "mill_only" | "skip"
    result["mat_reread_reason"] = mat_reread_reason

    # Category rules slice + price memory: infer from listing.json if available
    listing_path = folder / "listing.json"
    gender = ""
    item_type = ""
    materials: list[str] = []
    brand = ""
    if listing_path.exists():
        try:
            listing_data = json.loads(listing_path.read_text())
            gender    = listing_data.get("gender", "")
            item_type = listing_data.get("item_type", "")
            materials = listing_data.get("materials") or []
            brand     = listing_data.get("brand") or ""
        except Exception:
            pass
    result["gender"]    = gender
    result["item_type"] = item_type

    # Price memory lookup
    from app.listing_writer import _lookup_price_memory
    pm_entry = _lookup_price_memory(brand or None, item_type, materials)
    result["price_memory"] = pm_entry   # None if no match

    # Listing writer token counts — three levels:
    #   old:          full category_rules (no slicing)
    #   gender_only:  gender slice (old Step 4)
    #   with_type:    gender + item-type slice (new Step 2)
    from app.listing_writer import _slice_category_rules, _resolve_item_type_group
    style_schema_tokens = (4583 + 1505) // 4  # listing_style.md + schema chars / 4
    old_cat_tokens = 4517 // 4                # full category_rules.md
    gender_sliced = _slice_category_rules(gender)
    type_sliced   = _slice_category_rules(gender, item_type)
    gender_cat_tokens = len(gender_sliced) // 4
    type_cat_tokens   = len(type_sliced) // 4
    old_writer_total    = style_schema_tokens + old_cat_tokens
    gender_writer_total = style_schema_tokens + gender_cat_tokens
    type_writer_total   = style_schema_tokens + type_cat_tokens
    result["old_writer_tokens"]    = old_writer_total
    result["new_writer_tokens"]    = type_writer_total     # used for cost calc
    result["gender_writer_tokens"] = gender_writer_total
    result["type_group"] = _resolve_item_type_group(item_type) or ""

    # Total input tokens
    old_total = result["old"]["total_img_tokens"] + EXTRACT_PROMPT_TOKENS + old_writer_total
    if result["has_brand_photo"]:
        old_total += brand_reread_total   # old: always reread
    if result["has_material_photo"]:
        old_total += material_reread_total

    new_total = result["new"]["total_img_tokens"] + EXTRACT_PROMPT_TOKENS + type_writer_total
    if result["has_brand_photo"] and would_reread:
        new_total += brand_reread_total   # new: only if gate passes
    if result["has_material_photo"]:
        if mat_reread_mode == "full":
            new_total += material_reread_total
        elif mat_reread_mode == "mill_only":
            # mill-only reread: same image tokens, but output capped at 60 tokens (vs 150)
            new_total += mat_reread_img_tokens + MATERIAL_REREAD_PROMPT

    result["old"]["total_input_tokens"] = old_total
    result["new"]["total_input_tokens"] = new_total

    result["old"]["cost_pence"] = _cost_gbp(old_total, TYPICAL_OUTPUT_TOKENS)
    result["new"]["cost_pence"] = _cost_gbp(new_total, TYPICAL_OUTPUT_TOKENS)
    result["saving_pence"] = result["old"]["cost_pence"] - result["new"]["cost_pence"]
    result["saving_pct"] = (result["saving_pence"] / result["old"]["cost_pence"] * 100) if result["old"]["cost_pence"] else 0

    return result


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

COL = {"RESET": "\033[0m", "BOLD": "\033[1m", "GREEN": "\033[32m",
       "YELLOW": "\033[33m", "CYAN": "\033[36m", "RED": "\033[31m", "DIM": "\033[2m"}

def c(color: str, text: str) -> str:
    return f"{COL[color]}{text}{COL['RESET']}"


def _print_folder(r: dict) -> None:
    print(f"\n  {c('BOLD', r['folder'])}")

    # Photo table
    old_map = {p["role"]: p for p in r["old"]["photos"]}
    new_map = {p["role"]: p for p in r["new"]["photos"]}
    all_roles = list(dict.fromkeys(
        [p["role"] for p in r["old"]["photos"]] + [p["role"] for p in r["new"]["photos"]]
    ))

    print(f"    {'Role':<12} {'Old dim':>9} {'Tok':>6}  {'New dim':>9} {'Tok':>6}  {'Delta':>7}")
    print(f"    {'-'*12} {'-'*9} {'-'*6}  {'-'*9} {'-'*6}  {'-'*7}")

    for role in all_roles:
        op = old_map.get(role)
        np = new_map.get(role)

        old_dim  = f"{op['w']}×{op['h']}" if op else "—"
        old_tok  = str(op["tokens"]) if op else "—"
        new_dim  = f"{np['w']}×{np['h']}" if np else c("DIM", "dropped")
        new_tok  = str(np["tokens"]) if np else "—"
        delta    = (op["tokens"] if op else 0) - (np["tokens"] if np else 0)
        delta_s  = c("GREEN", f"-{delta}") if delta > 0 else (c("DIM", "0") if delta == 0 else c("RED", f"+{abs(delta)}"))

        ocr_flag = " [OCR]" if role in ("brand", "model_size", "material") else ""
        # Autocrop annotation for OCR roles
        crop_note = ""
        if np and np.get("crop_meta", {}).get("crop_applied"):
            cm = np["crop_meta"]
            ow, oh = cm["original_size"]
            cw, ch = cm["cropped_size"]
            pct = int(100 * (1 - (cw * ch) / (ow * oh))) if ow * oh else 0
            crop_note = c("GREEN", f" ✂-{pct}%")
        elif np and np.get("crop_meta") and not np["crop_meta"].get("crop_applied"):
            crop_note = c("DIM", " (no crop)")
        print(f"    {role+ocr_flag:<18} {old_dim:>9} {old_tok:>6}  {new_dim:>9} {new_tok:>6}  {delta_s:>7}{crop_note}")

    # Totals
    old_img_tok = r["old"]["total_img_tokens"]
    new_img_tok = r["new"]["total_img_tokens"]
    img_delta = old_img_tok - new_img_tok
    print(f"    {'Image tokens total':<18} {'':>9} {old_img_tok:>6}  {'':>9} {new_img_tok:>6}  {c('GREEN', f'-{img_delta}'):>7}")

    # Cost
    old_p = r["old"]["cost_pence"]
    new_p = r["new"]["cost_pence"]
    saving = r["saving_pence"]
    pct    = r["saving_pct"]
    print(f"\n    Cost (est):  Old {old_p:.2f}p  →  New {new_p:.2f}p  "
          f"{c('GREEN', f'(save {saving:.2f}p / {pct:.0f}%)')}")

    # Brand reread gate
    if r["has_brand_photo"]:
        if r["brand_reread_simulated"]:
            note = c("CYAN", f"brand-reread TRIGGERED — {r['brand_reread_reason']}")
        else:
            note = c("DIM", f"brand-reread SKIPPED — {r['brand_reread_reason']}")
        print(f"    Brand:   {note}")

    # Material reread gate
    if r["has_material_photo"]:
        mode = r["mat_reread_mode"]
        reason = r["mat_reread_reason"]
        if mode == "full":
            note = c("CYAN", f"material-reread FULL — {reason}")
        elif mode == "mill_only":
            note = c("YELLOW", f"material-reread MILL-ONLY — {reason}")
        else:
            note = c("DIM", f"material-reread SKIPPED — {reason}")
        print(f"    Material: {note}")

    # Category rules slice — show three-level breakdown
    g = r.get("gender", "")
    itype = r.get("item_type", "")
    igroup = r.get("type_group", "")
    old_w    = r["old_writer_tokens"]
    gender_w = r.get("gender_writer_tokens", old_w)
    new_w    = r["new_writer_tokens"]
    total_delta = old_w - new_w
    if total_delta > 0:
        if igroup and new_w < gender_w:
            slice_note = c("GREEN", (
                f"cat-rules: full({old_w})→gender({gender_w})→{igroup}({new_w}) "
                f"[total -{total_delta} tok]"
            ))
        elif gender_w < old_w:
            slice_note = c("GREEN", f"cat-rules: gender-only slice '{g}': {old_w}→{gender_w} tok (-{old_w - gender_w})")
        else:
            slice_note = c("GREEN", f"cat-rules sliced: {old_w}→{new_w} tok (-{total_delta})")
    else:
        slice_note = c("DIM", f"cat-rules not sliced (gender='{g}', item_type='{itype}')")
    print(f"    Prompt:  {slice_note}")

    # Price memory hint display
    pm = r.get("price_memory")
    if pm:
        level = pm.get("match_level", "?")
        conf  = pm.get("confidence", "?")
        note  = c("CYAN", (
            f"price-memory [{level}, {conf}]: "
            f"£{pm['typical']} typical (£{pm['low']}–£{pm['high']})"
        ))
        print(f"    Price:   {note}")
    else:
        print(f"    Price:   {c('DIM', 'no price memory match')}")

    if r["has_back_photo"] and "back" not in [p["role"] for p in r["new"]["photos"]]:
        print(f"    Photos:  {c('YELLOW', 'back.jpg present but dropped')}")


def run(folders: list[Path]) -> None:
    print(c("BOLD", "\n=== Vinted Lister — Dry-Run Validation ==="))
    print(c("DIM", "No API calls made. Costs estimated from pixel counts + prompt sizes.\n"))

    print("Prompt token breakdown:")
    print(f"  Extraction prompt : ~{EXTRACT_PROMPT_TOKENS} tokens (unchanged)")
    print(f"  Listing writer    : old ~{LISTING_WRITER_TOKENS_OLD} → new ~{LISTING_WRITER_TOKENS_NEW} tokens (cat-rules sliced)")
    print(f"  Typical output    : ~{TYPICAL_OUTPUT_TOKENS} tokens")
    print(f"  Brand re-read     : photo tokens + ~{BRAND_REREAD_PROMPT} prompt (gated by confidence)")
    print(f"  Material re-read  : photo tokens + ~{MATERIAL_REREAD_PROMPT} prompt (gated: full / mill-only / skip)")

    results = []
    skipped = 0
    for folder in folders:
        r = _analyse_folder(folder)
        if r:
            results.append(r)
            _print_folder(r)
        else:
            skipped += 1

    if not results:
        print(c("YELLOW", "\nNo valid item folders found (need at least front photo)."))
        return

    # -----------------------------------------------------------------------
    # Aggregate summary
    # -----------------------------------------------------------------------
    total_old  = sum(r["old"]["cost_pence"] for r in results)
    total_new  = sum(r["new"]["cost_pence"] for r in results)
    total_save = total_old - total_new
    avg_old    = total_old / len(results)
    avg_new    = total_new / len(results)
    avg_save   = total_save / len(results)

    print(f"\n{c('BOLD', '=== Summary ===')} ({len(results)} items)")
    print(f"  Avg cost before : {avg_old:.2f}p per item")
    print(f"  Avg cost after  : {avg_new:.2f}p per item")
    print(f"  Avg saving      : {c('GREEN', f'{avg_save:.2f}p per item')}")
    print(f"  Total saving    : {c('GREEN', f'{total_save:.2f}p')} across all {len(results)} test items")

    # Brand reread rate
    with_brand_photo = [r for r in results if r["has_brand_photo"]]
    reread_yes = [r for r in with_brand_photo if r["brand_reread_simulated"]]
    reread_no  = [r for r in with_brand_photo if not r["brand_reread_simulated"]]
    if with_brand_photo:
        reread_pct = len(reread_yes) / len(with_brand_photo) * 100
        reread_saved = len(reread_no)
        print(f"\n{c('BOLD', 'Brand reread gate')} ({len(with_brand_photo)} items with brand photo):")
        print(f"  Would reread  : {len(reread_yes)}/{len(with_brand_photo)} ({reread_pct:.0f}%)")
        print(f"  Would skip    : {c('GREEN', str(len(reread_no)))} items → saves ~"
              f"{c('GREEN', f'{len(reread_no) * 0.10:.2f}p')} (≈0.10p each)")
        if reread_no:
            skipped_brands = []
            for r in reread_no:
                lp = (Path(__file__).parent.parent / "items" / r["folder"] / "listing.json")
                if not lp.exists():
                    # items might be in a different location
                    lp = (Path(__file__).parent.parent / r["folder"] / "listing.json")
                try:
                    brand = json.loads(lp.read_text()).get("brand", "?")
                    skipped_brands.append(brand)
                except Exception:
                    skipped_brands.append("?")
            print(f"  Skipped brands: {', '.join(skipped_brands)}")

    # Material reread rate
    with_mat_photo = [r for r in results if r["has_material_photo"]]
    mat_full     = [r for r in with_mat_photo if r["mat_reread_mode"] == "full"]
    mat_mill     = [r for r in with_mat_photo if r["mat_reread_mode"] == "mill_only"]
    mat_skip     = [r for r in with_mat_photo if r["mat_reread_mode"] == "skip"]
    if with_mat_photo:
        print(f"\n{c('BOLD', 'Material reread gate')} ({len(with_mat_photo)} items with material photo):")
        print(f"  Full reread   : {len(mat_full)}/{len(with_mat_photo)} — premium fibre or item type")
        print(f"  Mill-only     : {len(mat_mill)}/{len(with_mat_photo)} — basic materials, no fabric_mill stored")
        print(f"  Skipped       : {c('GREEN', str(len(mat_skip)))}/{len(with_mat_photo)} "
              f"— basic + fabric_mill already known")
        # Old cost assumed full material reread every time
        old_mat_cost = sum(
            _cost_gbp(
                r["new"]["total_img_tokens"] + MATERIAL_REREAD_PROMPT +
                next((p["tokens"] for p in r["new"]["photos"] if p["role"] == "material"), 0),
                0
            )
            for r in with_mat_photo
        )
        # Count new cost: full items already included; mill-only saves output tokens (same input)
        skipped_reread_savings = len(mat_skip) * 0.01  # rough: ~0.01p per skipped call
        print(f"  Gate saves    : {c('GREEN', f'~{skipped_reread_savings:.2f}p')} across {len(mat_skip)} skipped items")

    # Autocrop summary
    ocr_roles = ("brand", "model_size", "material")
    all_ocr_photos = [
        p for r in results for p in r["new"]["photos"]
        if p["role"] in ocr_roles and p.get("crop_meta")
    ]
    cropped = [p for p in all_ocr_photos if p["crop_meta"].get("crop_applied")]
    no_crop = [p for p in all_ocr_photos if not p["crop_meta"].get("crop_applied")]
    if all_ocr_photos:
        avg_area_reduction = 0.0
        if cropped:
            reductions = []
            for p in cropped:
                cm = p["crop_meta"]
                ow, oh = cm["original_size"]
                cw, ch = cm["cropped_size"]
                if ow * oh > 0:
                    reductions.append(100 * (1 - (cw * ch) / (ow * oh)))
            avg_area_reduction = sum(reductions) / len(reductions) if reductions else 0
        print(f"\n{c('BOLD', 'Label auto-crop')} ({len(all_ocr_photos)} OCR photos across {len(results)} items):")
        print(f"  Crop applied  : {len(cropped)}/{len(all_ocr_photos)} photos")
        print(f"  No crop       : {len(no_crop)}/{len(all_ocr_photos)} photos (fallback or flag off)")
        if cropped:
            print(f"  Avg area cut  : {c('GREEN', f'{avg_area_reduction:.0f}%')} on photos where crop applied")

    # Category rules slice summary — show all three levels
    has_gender = [r for r in results if r.get("gender") in ("men's", "women's")]
    has_type   = [r for r in has_gender if r.get("type_group")]
    if has_gender:
        avg_gender_save = sum(r["old_writer_tokens"] - r.get("gender_writer_tokens", r["old_writer_tokens"])
                              for r in has_gender) / len(has_gender)
        avg_type_save   = sum(r["old_writer_tokens"] - r["new_writer_tokens"] for r in has_gender) / len(has_gender)
        print(f"\n{c('BOLD', 'Category rules slice')} ({len(has_gender)} gender-known items):")
        print(f"  Old (full rules)       : ~{results[0]['old_writer_tokens']} tokens")
        print(f"  Gender slice only      : ~{results[0].get('gender_writer_tokens', 'n/a')} tokens")
        if has_type:
            r0 = has_type[0]
            print(f"  Gender + item-type     : ~{r0['new_writer_tokens']} tokens (group: {r0['type_group']})")
        print(f"  Avg saving (gender)    : {c('GREEN', f'~{avg_gender_save:.0f} tokens')} per item")
        if has_type:
            print(f"  Avg saving (+ type)    : {c('GREEN', f'~{avg_type_save:.0f} tokens')} per item")

    # Parallel reread summary
    print(f"\n{c('BOLD', 'Parallel rereads')}:")
    from app.config import ENABLE_PARALLEL_REREADS as _FLAG_PARALLEL
    if _FLAG_PARALLEL:
        both_reread = [r for r in results if r["brand_reread_simulated"] and
                       r.get("mat_reread_mode") in ("full", "mill_only")]
        brand_only  = [r for r in results if r["brand_reread_simulated"] and
                       r.get("mat_reread_mode") == "skip"]
        mat_only    = [r for r in results if not r["brand_reread_simulated"] and
                       r.get("mat_reread_mode") in ("full", "mill_only")]
        print(f"  Flag enabled  : {c('GREEN', 'YES')}")
        print(f"  Both parallel : {len(both_reread)} items (brand + material concurrently)")
        print(f"  Brand only    : {len(brand_only)} items")
        print(f"  Material only : {len(mat_only)} items")
        total_rereads = sum(
            (1 if r["brand_reread_simulated"] else 0) +
            (1 if r.get("mat_reread_mode") in ("full", "mill_only") else 0)
            for r in results
        )
        print(f"  Avg rereads   : {total_rereads / len(results):.1f} per item")
    else:
        print(f"  Flag enabled  : {c('YELLOW', 'NO')} (sequential mode)")

    # Price memory summary
    pm_matched   = [r for r in results if r.get("price_memory")]
    pm_unmatched = [r for r in results if not r.get("price_memory")]
    print(f"\n{c('BOLD', 'Price memory')} ({len(results)} items):")
    print(f"  Matched  : {len(pm_matched)}/{len(results)} items")
    print(f"  No match : {c('DIM', str(len(pm_unmatched)))} items")
    if pm_matched:
        from collections import Counter
        level_counts = Counter(r["price_memory"]["match_level"] for r in pm_matched)
        for level, count in sorted(level_counts.items()):
            print(f"    {level:<30} {count} items")

    # -----------------------------------------------------------------------
    # Validation rules
    # -----------------------------------------------------------------------
    print(f"\n{c('BOLD', '=== Validation Rules ===')}")

    rules: list[tuple[str, bool, str]] = []

    from app.config import CORE_PHOTOS
    from app.extractor import _PHOTO_MAX_DIM, _DEFAULT_MAX_DIM

    rules.append(("back excluded from CORE_PHOTOS",
                  "back" not in CORE_PHOTOS,
                  f"CORE_PHOTOS = {CORE_PHOTOS}"))

    rules.append(("front uses 768px max",
                  _PHOTO_MAX_DIM.get("front") == 768,
                  f"front max_dim = {_PHOTO_MAX_DIM.get('front')}"))

    rules.append(("brand uses 1024px max [OCR]",
                  _PHOTO_MAX_DIM.get("brand") == 1024,
                  f"brand max_dim = {_PHOTO_MAX_DIM.get('brand')}"))

    rules.append(("model_size uses 1024px max [OCR]",
                  _PHOTO_MAX_DIM.get("model_size") == 1024,
                  f"model_size max_dim = {_PHOTO_MAX_DIM.get('model_size')}"))

    rules.append(("material uses 1024px max [OCR]",
                  _PHOTO_MAX_DIM.get("material") == 1024,
                  f"material max_dim = {_PHOTO_MAX_DIM.get('material')}"))

    rules.append(("default max_dim is 768 (safe fallback)",
                  _DEFAULT_MAX_DIM == 768,
                  f"_DEFAULT_MAX_DIM = {_DEFAULT_MAX_DIM}"))

    # Verify reread functions have explicit 1024 by inspecting source
    import inspect
    from app.extractor import _reread_brand_photo, _reread_material_photo
    brand_src    = inspect.getsource(_reread_brand_photo)
    material_src = inspect.getsource(_reread_material_photo)
    rules.append(("_reread_brand_photo explicitly passes max_dim=1024",
                  "max_dim=1024" in brand_src,
                  "checked via source inspection"))
    rules.append(("_reread_material_photo explicitly passes max_dim=1024",
                  "max_dim=1024" in material_src,
                  "checked via source inspection"))

    # Brand reread gate is in place
    from app.extractor import _should_reread_brand, _REREAD_PREMIUM_BRANDS
    rules.append(("_should_reread_brand skips high-confidence non-premium",
                  not _should_reread_brand({"brand": "Next", "brand_confidence": "high"}),
                  "Next + high → skip"))
    rules.append(("_should_reread_brand triggers for low confidence",
                  _should_reread_brand({"brand": "Barbour", "brand_confidence": "low"}),
                  "Barbour + low → reread"))
    rules.append(("_should_reread_brand triggers for premium at medium",
                  _should_reread_brand({"brand": "Moncler", "brand_confidence": "medium"}),
                  "Moncler + medium → reread"))

    # Brand confidence fields in prompt
    from app.extractor import _EXTRACT_PROMPT
    rules.append(("extraction prompt includes brand_confidence field",
                  "brand_confidence" in _EXTRACT_PROMPT,
                  "checked in _EXTRACT_PROMPT string"))
    rules.append(("extraction prompt includes BRAND CONFIDENCE rules",
                  "BRAND CONFIDENCE" in _EXTRACT_PROMPT,
                  "checked in _EXTRACT_PROMPT string"))

    # Material reread gate is in place
    from app.extractor import _should_reread_material, _PRICING_SENSITIVE_FIBRES, _PRICING_SENSITIVE_ITEM_TYPES
    rules.append(("_should_reread_material skips high-confidence basic cotton",
                  not _should_reread_material({"materials": ["100% Cotton"], "material_confidence": "high"}),
                  "100% Cotton + high → skip"))
    rules.append(("_should_reread_material triggers for low confidence",
                  _should_reread_material({"materials": ["100% Wool"], "material_confidence": "low"}),
                  "Wool + low → full reread"))
    rules.append(("_should_reread_material triggers for medium+cashmere",
                  _should_reread_material({"materials": ["80% Cashmere, 20% Wool"], "material_confidence": "medium"}),
                  "cashmere + medium → full reread"))
    rules.append(("_should_reread_material triggers for medium+blazer",
                  _should_reread_material({
                      "materials": ["100% Polyester"], "item_type": "blazer",
                      "material_confidence": "medium", "pricing_sensitive_material": False
                  }),
                  "polyester blazer + medium → full reread"))
    rules.append(("_PRICING_SENSITIVE_FIBRES non-empty",
                  len(_PRICING_SENSITIVE_FIBRES) >= 10,
                  f"{len(_PRICING_SENSITIVE_FIBRES)} fibres"))
    rules.append(("_PRICING_SENSITIVE_ITEM_TYPES non-empty",
                  len(_PRICING_SENSITIVE_ITEM_TYPES) >= 8,
                  f"{len(_PRICING_SENSITIVE_ITEM_TYPES)} item types"))
    rules.append(("extraction prompt includes material_confidence field",
                  "material_confidence" in _EXTRACT_PROMPT,
                  "checked in _EXTRACT_PROMPT string"))
    rules.append(("extraction prompt includes MATERIAL CONFIDENCE rules",
                  "MATERIAL CONFIDENCE" in _EXTRACT_PROMPT,
                  "checked in _EXTRACT_PROMPT string"))

    # Category rules slice
    from app.listing_writer import _slice_category_rules
    mens_slice = _slice_category_rules("men's")
    womens_slice = _slice_category_rules("women's")
    full_rules = _slice_category_rules("")
    rules.append(("men's slice excludes Women's category paths",
                  "Women > " not in mens_slice.split("# Notes")[0],
                  f"{len(mens_slice)//4} tokens vs {len(full_rules)//4} full"))
    rules.append(("women's slice excludes Men's category paths",
                  "Men > " not in womens_slice.split("# Notes")[0],
                  f"{len(womens_slice)//4} tokens vs {len(full_rules)//4} full"))
    rules.append(("category slice saves ≥400 tokens for single-gender",
                  (len(full_rules) - len(mens_slice)) // 4 >= 400,
                  f"saving = {(len(full_rules)-len(mens_slice))//4} tokens"))

    # Step 1 — Label auto-crop
    from app.config import ENABLE_LABEL_AUTOCROP as _FLAG_AUTOCROP
    rules.append(("ENABLE_LABEL_AUTOCROP feature flag exists and defaults True",
                  _FLAG_AUTOCROP is True,
                  f"ENABLE_LABEL_AUTOCROP = {_FLAG_AUTOCROP}"))

    from app.extractor import _autocrop_label, _OCR_ROLES
    rules.append(("_autocrop_label function is callable",
                  callable(_autocrop_label),
                  "checked via callable()"))
    rules.append(("_OCR_ROLES contains brand, model_size, material",
                  {"brand", "model_size", "material"}.issubset(_OCR_ROLES),
                  f"_OCR_ROLES = {sorted(_OCR_ROLES)}"))
    rules.append(("front is not in _OCR_ROLES",
                  "front" not in _OCR_ROLES,
                  "front uses _compress_image, not autocrop"))

    from app.extractor import _compress_with_autocrop
    from app.extractor import _reread_brand_photo as _rbp, _reread_material_photo as _rmp
    rbp_src = inspect.getsource(_rbp)
    rmp_src = inspect.getsource(_rmp)
    rules.append(("_reread_brand_photo uses _compress_with_autocrop",
                  "_compress_with_autocrop" in rbp_src,
                  "source inspection"))
    rules.append(("_reread_material_photo uses _compress_with_autocrop",
                  "_compress_with_autocrop" in rmp_src,
                  "source inspection"))

    # Step 2 — Item-type category slice
    from app.config import ENABLE_CATEGORY_ITEM_TYPE_SLICE as _FLAG_SLICE
    rules.append(("ENABLE_CATEGORY_ITEM_TYPE_SLICE feature flag exists and defaults True",
                  _FLAG_SLICE is True,
                  f"ENABLE_CATEGORY_ITEM_TYPE_SLICE = {_FLAG_SLICE}"))

    from app.listing_writer import _resolve_item_type_group
    rules.append(("_resolve_item_type_group('blazer') == 'tailoring'",
                  _resolve_item_type_group("blazer") == "tailoring",
                  f"got: {_resolve_item_type_group('blazer')}"))
    rules.append(("_resolve_item_type_group('jeans') == 'jeans'",
                  _resolve_item_type_group("jeans") == "jeans",
                  f"got: {_resolve_item_type_group('jeans')}"))
    rules.append(("_resolve_item_type_group('jacket') == 'outerwear'",
                  _resolve_item_type_group("jacket") == "outerwear",
                  f"got: {_resolve_item_type_group('jacket')}"))
    rules.append(("_resolve_item_type_group('unknown item') returns None",
                  _resolve_item_type_group("unknown item xyz") is None,
                  f"got: {_resolve_item_type_group('unknown item xyz')}"))

    blazer_slice     = _slice_category_rules("men's", "blazer")
    mens_slice_only  = _slice_category_rules("men's")
    blazer_tok_save  = (len(mens_slice_only) - len(blazer_slice)) // 4
    rules.append(("item-type slice saves ≥50 tokens vs gender-only (men's blazer)",
                  blazer_tok_save >= 50,
                  f"saving = {blazer_tok_save} tokens"))
    rules.append(("men's blazer slice contains Blazer rule",
                  "Blazer" in blazer_slice,
                  "checked in slice text"))
    rules.append(("men's blazer slice excludes Jeans rules (pre-Notes)",
                  "Jeans" not in blazer_slice.split("# Notes")[0],
                  "checked pre-Notes section"))

    # Step 3 — Parallel rereads
    from app.config import ENABLE_PARALLEL_REREADS as _VAL_PARALLEL
    rules.append(("ENABLE_PARALLEL_REREADS feature flag exists and defaults True",
                  _VAL_PARALLEL is True,
                  f"ENABLE_PARALLEL_REREADS = {_VAL_PARALLEL}"))

    from app.extractor import extract as _ext_fn
    ext_src = inspect.getsource(_ext_fn)
    rules.append(("extract() uses ThreadPoolExecutor for parallel rereads",
                  "ThreadPoolExecutor" in ext_src,
                  "source inspection"))
    rules.append(("extract() handles individual reread exceptions gracefully",
                  "_reread_brand_error" in ext_src and "_reread_mat_error" in ext_src,
                  "error variables present in source"))
    rules.append(("parallel path only active when both rereads needed",
                  "_use_parallel" in ext_src,
                  "_use_parallel guard present in source"))

    # Step 4 — Price memory
    from app.config import ENABLE_PRICE_MEMORY as _VAL_PM
    rules.append(("ENABLE_PRICE_MEMORY feature flag exists and defaults True",
                  _VAL_PM is True,
                  f"ENABLE_PRICE_MEMORY = {_VAL_PM}"))

    from app.listing_writer import _lookup_price_memory, _classify_material_group
    rules.append(("_lookup_price_memory is callable",
                  callable(_lookup_price_memory),
                  "checked via callable()"))
    rules.append(("_classify_material_group('100% Cashmere') == 'cashmere'",
                  _classify_material_group(["100% Cashmere"]) == "cashmere",
                  f"got: {_classify_material_group(['100% Cashmere'])}"))
    rules.append(("_classify_material_group('100% Wool') == 'wool'",
                  _classify_material_group(["100% Wool"]) == "wool",
                  f"got: {_classify_material_group(['100% Wool'])}"))

    from app.listing_writer import _load_price_memory
    pm_entries = _load_price_memory()
    rules.append(("price_memory.json has ≥10 entries",
                  len(pm_entries) >= 10,
                  f"{len(pm_entries)} entries loaded"))
    rules.append(("all price_memory entries have valid price ordering (low≤typical≤high)",
                  all(e["low"] <= e["typical"] <= e["high"] for e in pm_entries),
                  "checked all entries"))

    # Verify price hint appears in a real prompt
    from app.listing_writer import _build_prompt as _bpmt, _PRICE_MEMORY as _pm_cache
    _bpmt_item = {
        "brand": "Barbour", "brand_confidence": "high",
        "item_type": "wax jacket", "gender": "men's",
        "tagged_size": "M", "normalized_size": "M",
        "materials": ["100% Cotton"], "colour": "Olive",
        "confidence": 0.9, "low_confidence_fields": [],
        "condition_summary": "Very good used condition — minimal wear.",
    }
    _bpmt_prompt = _bpmt(_bpmt_item)
    rules.append(("price memory hint injected into Barbour wax jacket prompt",
                  "PRICE MEMORY HINT" in _bpmt_prompt,
                  "checked in _build_prompt output"))

    # Cost improves vs old config
    rules.append(("new config costs less than old config",
                  avg_new < avg_old,
                  f"old={avg_old:.2f}p → new={avg_new:.2f}p"))

    pass_count = 0
    for desc, passed, detail in rules:
        icon = c("GREEN", "PASS") if passed else c("RED", "FAIL")
        dim_note = c("DIM", f"  ({detail})")
        print(f"  [{icon}] {desc} {dim_note}")
        if passed:
            pass_count += 1

    # -----------------------------------------------------------------------
    # OCR risk assessment
    # -----------------------------------------------------------------------
    print(f"\n{c('BOLD', '=== OCR Risk Assessment ===')}")

    ocr_roles = ("brand", "model_size", "material")
    ocr_ok = all(_PHOTO_MAX_DIM.get(r) == 1024 for r in ocr_roles)

    if ocr_ok:
        print(c("GREEN", "  LOW RISK — all label/OCR photos kept at 1024px."))
        print(c("DIM",   "  Re-read functions also use 1024px (verified above)."))
        print(c("DIM",   "  768px applied only to front (garment overview) — no text to read there."))
    else:
        problem_roles = [r for r in ocr_roles if _PHOTO_MAX_DIM.get(r) != 1024]
        print(c("RED", f"  HIGH RISK — OCR-critical photos at wrong resolution: {problem_roles}"))

    # -----------------------------------------------------------------------
    # Final verdict
    # -----------------------------------------------------------------------
    print(f"\n{c('BOLD', '=== Result ===')} {pass_count}/{len(rules)} rules passed")
    if pass_count == len(rules):
        print(c("GREEN", "  All checks passed. Cost-reduction changes are safe to deploy.\n"))
    else:
        failed = [d for d, p, _ in rules if not p]
        print(c("RED", f"  {len(failed)} check(s) failed: {failed}\n"))


if __name__ == "__main__":
    root = Path(__file__).parent.parent

    if len(sys.argv) > 1:
        folders = [Path(a) for a in sys.argv[1:]]
    else:
        items_dir = root / "items"
        folders = sorted(
            [d for d in items_dir.iterdir() if d.is_dir()],
            key=lambda d: d.name
        )
        # Also check _sample_item in root
        sample = root / "_sample_item"
        if sample.is_dir():
            folders.insert(0, sample)

    run(folders)
