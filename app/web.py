"""
Flask web app — single endpoint for creating a Vinted listing from item photos.

Usage:
  flask --app app.web run

POST /create-listing
  Body: {"folder": "item_folder_name", "buy_price_gbp": 15.00}  (buy_price optional)
  Returns: the validated listing JSON
"""
import csv
import json
import re
import threading
import time
import traceback
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory

from app.config import ITEMS_DIR, ROOT
from app import extractor, listing_writer, run_logger

# ── Vinted login session (for cookie refresh flow) ───────────────────────────
_vinted_login: dict = {}   # holds playwright/browser/context while login window is open
COOKIES_FILE = ROOT / "vinted_cookies.json"

try:
    from app import draft_creator
    _DRAFT_ENABLED = True
except Exception:
    draft_creator = None  # type: ignore
    _DRAFT_ENABLED = False

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB max upload


@app.errorhandler(Exception)
def handle_unhandled_exception(e):
    """Catch-all: always return JSON instead of an HTML error page."""
    return jsonify({"error": traceback.format_exc()}), 500

# Pricing (USD per million tokens)
_PRICES = {
    "haiku":  {"in": 0.80, "out": 4.00},
    "sonnet": {"in": 3.00, "out": 15.00},
}
_USD_TO_GBP = 0.79

COST_LOG = ROOT / "cost_log.csv"


def _model_key(model: str) -> str:
    return "sonnet" if "sonnet" in model.lower() else "haiku"


def _calc_cost_usd(usage: dict) -> float:
    key = _model_key(usage.get("model", ""))
    p = _PRICES[key]
    return (usage["input_tokens"] * p["in"] + usage["output_tokens"] * p["out"]) / 1_000_000


def _log_cost(folder: str, extract_usage: dict, write_usage: dict, listing: dict):
    cost_usd = _calc_cost_usd(extract_usage) + _calc_cost_usd(write_usage)
    cost_gbp = cost_usd * _USD_TO_GBP

    row = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "folder": folder,
        "extract_model": extract_usage.get("model", ""),
        "brand": listing.get("brand", ""),
        "title": listing.get("title", ""),
        "price_gbp": listing.get("price_gbp", ""),
        "input_tokens": extract_usage["input_tokens"] + write_usage["input_tokens"],
        "output_tokens": extract_usage["output_tokens"] + write_usage["output_tokens"],
        "cost_usd": round(cost_usd, 5),
        "cost_gbp": round(cost_gbp, 5),
    }

    write_header = not COST_LOG.exists()
    with open(COST_LOG, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        if write_header:
            writer.writeheader()
        writer.writerow(row)

    total_in  = row["input_tokens"]
    total_out = row["output_tokens"]
    print(f"Cost: {total_in} in + {total_out} out tokens = £{cost_gbp:.4f}")


@app.post("/create-listing")
def create_listing():
    body = request.get_json(force=True, silent=True) or {}
    folder = body.get("folder", "").strip()
    if not folder:
        return jsonify({"error": "folder is required"}), 400

    item_path = ITEMS_DIR / folder
    if not item_path.is_dir():
        return jsonify({"error": f"Folder not found: {item_path}"}), 404

    hints = {k: v for k, v in {
        "brand":    body.get("hint_brand",    "").strip(),
        "size":     body.get("hint_size",     "").strip(),
        "gender":   body.get("hint_gender",   "").strip(),
        "made_in":  body.get("hint_made_in",  "").strip(),
        "damages":  body.get("hint_damages",  "").strip(),
    }.items() if v}

    try:
        _t0 = time.perf_counter()
        item, extract_usage = extractor.extract(item_path, hints=hints or None)
        extract_log = item.pop("_extract_log", {})
        if "buy_price_gbp" in body:
            item["buy_price_gbp"] = float(body["buy_price_gbp"])
        listing, write_usage = listing_writer.write(item, hints=hints or None)
        write_log = write_usage.pop("_write_log", {})

        # Save listing JSON next to the photos
        out_path = item_path / "listing.json"
        out_path.write_text(json.dumps(listing, indent=2))

        listing["folder"] = folder
        _log_cost(folder, extract_usage, write_usage, listing)
        _write_run_log(folder, extract_log, write_log, extract_usage, write_usage, listing,
                       round((time.perf_counter() - _t0) * 1000))
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 422
    except Exception:
        return jsonify({"error": traceback.format_exc()}), 500

    return jsonify(listing), 200


@app.get("/auth/status")
def auth_status():
    """GET /auth/status — fast file-based Vinted session indicator (no browser launch)."""
    if not _DRAFT_ENABLED:
        return jsonify({"logged_in": "missing", "method": "none", "expires_at": None})
    return jsonify(draft_creator.check_auth_state())


@app.post("/create-draft")
def create_draft_endpoint():
    """POST /create-draft  Body: {"folder": "blazer_1"}
    Reads the existing listing.json and creates a Vinted draft from it."""
    if not _DRAFT_ENABLED:
        return jsonify({"error": "Playwright not available in this environment"}), 503

    body = request.get_json(force=True, silent=True) or {}
    folder = body.get("folder", "").strip()
    if not folder:
        return jsonify({"error": "folder is required"}), 400

    item_path = ITEMS_DIR / folder
    listing_path = item_path / "listing.json"
    if not listing_path.exists():
        return jsonify({"error": f"listing.json not found in {item_path}"}), 404

    try:
        listing = json.loads(listing_path.read_text())
        draft_url = draft_creator.create_draft(listing, item_path)
    except draft_creator.VintedAuthError as e:
        return jsonify({"error": str(e), "code": "VINTED_AUTH_EXPIRED"}), 401
    except Exception:
        return jsonify({"error": traceback.format_exc()}), 500

    return jsonify({"draft_url": draft_url}), 200


@app.post("/edit-draft")
def edit_draft_endpoint():
    """POST /edit-draft  Body: {"folder": "blazer_1"}
    Edits the existing Vinted draft for this listing (navigates to /items/ID/edit)."""
    if not _DRAFT_ENABLED:
        return jsonify({"error": "Playwright not available in this environment"}), 503

    body = request.get_json(force=True, silent=True) or {}
    folder = body.get("folder", "").strip()
    if not folder:
        return jsonify({"error": "folder is required"}), 400

    item_path = ITEMS_DIR / folder
    listing_path = item_path / "listing.json"
    if not listing_path.exists():
        return jsonify({"error": f"listing.json not found in {item_path}"}), 404

    try:
        listing = json.loads(listing_path.read_text())
        draft_url = listing.get("draft_url") or ""
        result_url = draft_creator.edit_draft(listing, item_path, draft_url)
    except draft_creator.VintedAuthError as e:
        return jsonify({"error": str(e), "code": "VINTED_AUTH_EXPIRED"}), 401
    except Exception:
        return jsonify({"error": traceback.format_exc()}), 500

    return jsonify({"draft_url": result_url}), 200


_UPLOAD_MAX_DIM = 2048   # px — phone photos are typically 4000+ px wide
_UPLOAD_MAX_BYTES = 8 * 1024 * 1024   # 8 MB — Vinted rejects anything ≥ 9 MB


def _resize_photo(path: Path) -> Path:
    """Resize a photo to ≤ _UPLOAD_MAX_DIM px and ≤ _UPLOAD_MAX_BYTES in-place.

    Always normalises to JPEG with progressive encoding and EXIF stripping.
    Returns the (possibly renamed) path.
    """
    try:
        from PIL import Image
        orig_bytes = path.stat().st_size
        img = Image.open(path).convert("RGB")
        w, h = img.size
        needs_resize = max(w, h) > _UPLOAD_MAX_DIM or orig_bytes > _UPLOAD_MAX_BYTES
        if needs_resize:
            scale = min(1.0, _UPLOAD_MAX_DIM / max(w, h))
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        jpg_path = path.with_suffix(".jpg")
        img.save(jpg_path, "JPEG", quality=85, optimize=True, progressive=True, exif=b"")
        new_w, new_h = img.size
        print(
            f"[photo_resize] original={orig_bytes // 1024 // 1024}MB "
            f"resized={jpg_path.stat().st_size // 1024 // 1024}MB "
            f"width={new_w} height={new_h}"
        )
        if jpg_path != path:
            path.unlink(missing_ok=True)
        return jpg_path
    except Exception:
        return path  # Pillow unavailable or corrupt file — keep original


@app.get("/")
def index():
    return render_template("index.html", active_tab="upload", draft_count=_draft_count())


@app.post("/upload")
def upload_listing():
    """Mobile upload endpoint. Accepts multipart form with photos + buy_price.
    Photos should be uploaded in order: front, tag, material, back, then extras.
    Auto-creates an item folder and runs the full pipeline."""
    files = request.files.getlist("photos")
    if not files or all(f.filename == "" for f in files):
        return jsonify({"error": "No photos uploaded"}), 400

    buy_price = request.form.get("buy_price", "").strip()
    folder_name = f"upload_{uuid.uuid4().hex[:8]}"
    item_path = ITEMS_DIR / folder_name
    item_path.mkdir(parents=True, exist_ok=True)

    # Save photos: first 5 get core names (back is optional slot 5), rest get numbered
    core_names = ["front", "brand", "model_size", "material", "back"]
    saved = []
    for i, f in enumerate(files):
        if f.filename == "":
            continue
        ext = Path(f.filename).suffix.lower() or ".jpg"
        if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
            continue
        name = core_names[i] if i < len(core_names) else f"extra_{i - len(core_names) + 1:02d}"
        dest = item_path / f"{name}{ext}"
        f.save(dest)
        dest = _resize_photo(dest)   # shrink large phone photos before storing
        saved.append(dest.name)

    if not saved:
        return jsonify({"error": "No valid photos saved"}), 400

    hints = {k: v for k, v in {
        "brand":   request.form.get("hint_brand",   "").strip(),
        "size":    request.form.get("hint_size",    "").strip(),
        "gender":  request.form.get("hint_gender",  "").strip(),
        "made_in": request.form.get("hint_made_in", "").strip(),
        "damages": request.form.get("hint_damages", "").strip(),
    }.items() if v}

    try:
        _t0 = time.perf_counter()
        item, extract_usage = extractor.extract(item_path, hints=hints or None)
        extract_log = item.pop("_extract_log", {})
        if buy_price:
            item["buy_price_gbp"] = float(buy_price)
        listing, write_usage = listing_writer.write(item, hints=hints or None)
        write_log = write_usage.pop("_write_log", {})

        out_path = item_path / "listing.json"
        out_path.write_text(json.dumps(listing, indent=2))

        cost_usd = _calc_cost_usd(extract_usage) + _calc_cost_usd(write_usage)
        cost_gbp = cost_usd * _USD_TO_GBP
        listing["cost_gbp"] = round(cost_gbp, 4)
        listing["cost_tokens"] = {
            "input":  extract_usage["input_tokens"] + write_usage["input_tokens"],
            "output": extract_usage["output_tokens"] + write_usage["output_tokens"],
        }

        listing["folder"] = folder_name
        _log_cost(folder_name, extract_usage, write_usage, listing)
        _write_run_log(folder_name, extract_log, write_log, extract_usage, write_usage, listing,
                       round((time.perf_counter() - _t0) * 1000))
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 422
    except Exception:
        return jsonify({"error": traceback.format_exc()}), 500

    return jsonify(listing), 200


@app.get("/drafts")
def drafts_page():
    listings = _get_all_listings()
    return render_template("drafts.html", listings=listings, draft_count=len(listings), active_tab="drafts")


@app.get("/connect")
def connect_page():
    return render_template("connect.html", active_tab="connect")


@app.get("/stats")
def stats_page():
    listings = _get_all_listings()
    cost_history = _get_cost_history()
    stats = _compute_stats(listings, cost_history)
    return render_template("stats.html", stats=stats, cost_history=cost_history,
                           draft_count=len(listings), active_tab="stats")


@app.get("/api/listings")
def api_listings():
    return jsonify(_get_all_listings())


@app.get("/api/categories")
def api_categories():
    """Return all Vinted category paths from the scraped category tree."""
    from app.config import ROOT
    cat_file = ROOT / "vinted_categories.json"
    if cat_file.exists():
        import json as _json
        paths = _json.loads(cat_file.read_text())
        # Convert [[seg, seg, ...], ...] to ["seg > seg > ...", ...]
        return jsonify([" > ".join(p) for p in paths])
    # Fallback: CATEGORY_NAV shorthand keys
    if _DRAFT_ENABLED:
        from app.draft_creator import CATEGORY_NAV
        return jsonify(sorted(CATEGORY_NAV.keys()))
    return jsonify([])


@app.get("/api/stats")
def api_stats():
    listings = _get_all_listings()
    cost_history = _get_cost_history()
    return jsonify(_compute_stats(listings, cost_history))


@app.get("/items/<folder>/<filename>")
def serve_item_photo(folder, filename):
    """Serve item photos for the draft bank thumbnails."""
    safe_folder = Path(folder).name  # prevent directory traversal
    return send_from_directory(ITEMS_DIR / safe_folder, filename)


# ── Helpers ────────────────────────────────────────────────────────────────

def _draft_count() -> int:
    if not ITEMS_DIR.exists():
        return 0
    return sum(
        1 for d in ITEMS_DIR.iterdir()
        if d.is_dir() and not d.name.startswith("_") and (d / "listing.json").exists()
    )


def _get_all_listings() -> list[dict]:
    listings = []
    if not ITEMS_DIR.exists():
        return listings
    dirs = sorted(ITEMS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    for item_dir in dirs:
        if not item_dir.is_dir() or item_dir.name.startswith("_"):
            continue
        listing_path = item_dir / "listing.json"
        if not listing_path.exists():
            continue
        try:
            listing = json.loads(listing_path.read_text())
            listing["folder"] = item_dir.name
            for ext in [".jpg", ".jpeg", ".png", ".webp"]:
                if (item_dir / f"front{ext}").exists():
                    listing["thumbnail_url"] = f"/items/{item_dir.name}/front{ext}"
                    break
            listings.append(listing)
        except Exception:
            continue
    return listings


def _get_cost_history() -> list[dict]:
    if not COST_LOG.exists():
        return []
    rows = []
    with open(COST_LOG, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return list(reversed(rows))  # most recent first


def _compute_stats(listings: list[dict], cost_history: list[dict]) -> dict:
    total_items = len(listings)

    # De-duplicate: keep latest cost entry per folder
    seen: set[str] = set()
    unique_costs = []
    for row in cost_history:
        if row["folder"] not in seen:
            seen.add(row["folder"])
            unique_costs.append(row)

    total_spend_gbp = sum(float(r.get("cost_gbp", 0)) for r in unique_costs)
    avg_cost = total_spend_gbp / len(unique_costs) if unique_costs else 0
    total_value = sum(float(l.get("price_gbp", 0)) for l in listings)

    # ROI: items where we know the buy price
    profit_items = [
        l for l in listings
        if l.get("buy_price_gbp") is not None and l.get("price_gbp")
    ]
    potential_profit = sum(
        float(l["price_gbp"]) - float(l["buy_price_gbp"]) - (float(l["price_gbp"]) * 0.05 + 0.70)
        for l in profit_items
    )

    brands = Counter(l.get("brand") or "Unknown" for l in listings)

    return {
        "total_items": total_items,
        "total_spend_gbp": round(total_spend_gbp, 4),
        "avg_cost_gbp": round(avg_cost, 4),
        "total_value_gbp": round(total_value, 2),
        "potential_profit_gbp": round(potential_profit, 2),
        "profit_item_count": len(profit_items),
        "brands": [{"brand": b, "count": c} for b, c in brands.most_common(10)],
    }


def _write_run_log(listing_id, extract_log, write_log, extract_usage, write_usage, listing, latency_ms):
    """Assemble and persist a structured run log entry."""
    cost_extract = _calc_cost_usd(extract_usage) * _USD_TO_GBP
    cost_write   = _calc_cost_usd(write_usage)   * _USD_TO_GBP
    entry = {
        "listing_id":            listing_id,
        "timestamp":             datetime.now().isoformat(timespec="seconds"),
        "latency_ms":            latency_ms,
        # Extraction stage
        "photos_found":          extract_log.get("photos_found", []),
        "crop_applied":          extract_log.get("crop_applied", {}),
        "escalated":             extract_log.get("escalated", False),
        "extract_latency_ms":    extract_log.get("extract_latency_ms"),
        "extract_input_tokens":  extract_log.get("extract_input_tokens", 0),
        "extract_output_tokens": extract_log.get("extract_output_tokens", 0),
        "extract_model":         extract_log.get("extract_model", ""),
        "rereads_triggered":     extract_log.get("rereads_triggered", {}),
        "reread_reasons":        extract_log.get("reread_reasons", {}),
        "parallel_used":         extract_log.get("parallel_used", False),
        "reread_errors":         extract_log.get("reread_errors", {}),
        "rereads_count":         extract_log.get("rereads_count", 0),
        # Listing write stage
        "write_input_tokens":    write_usage.get("input_tokens", 0),
        "write_output_tokens":   write_usage.get("output_tokens", 0),
        "write_model":           write_usage.get("model", ""),
        "write_latency_ms":      write_log.get("write_latency_ms"),
        "category_slice_level":  write_log.get("category_slice_level"),
        # Quality signals (from listing)
        "price_memory_match_level": listing.get("price_memory_match"),
        "brand_confidence":         listing.get("brand_confidence"),
        "material_confidence":      listing.get("material_confidence"),
        "confidence":               listing.get("confidence"),
        "low_confidence_fields":    listing.get("low_confidence_fields", []),
        "warnings":                 listing.get("warnings", []),
        # Cost
        "cost_gbp_extract": round(cost_extract, 5),
        "cost_gbp_write":   round(cost_write, 5),
        "cost_gbp_total":   round(cost_extract + cost_write, 5),
    }
    try:
        run_logger.write_run_log(entry)
    except Exception:
        pass  # never let logging crash the main pipeline


@app.get("/listing/<folder>")
def get_listing(folder):
    """GET /listing/<folder> — return listing.json as JSON."""
    safe_folder = Path(folder).name
    listing_path = ITEMS_DIR / safe_folder / "listing.json"
    if not listing_path.exists():
        return jsonify({"error": "listing not found"}), 404
    listing = json.loads(listing_path.read_text())
    listing["folder"] = safe_folder
    return jsonify(listing), 200


@app.patch("/listing/<folder>")
def patch_listing(folder):
    """PATCH /listing/<folder>  Body: {field: value, ...}  — update specific fields in listing.json.
    Changed fields are logged as correction events in data/corrections.jsonl."""
    safe_folder = Path(folder).name
    listing_path = ITEMS_DIR / safe_folder / "listing.json"
    if not listing_path.exists():
        return jsonify({"error": "listing not found"}), 404
    try:
        updates = request.get_json(force=True, silent=True) or {}
        listing = json.loads(listing_path.read_text())
        # Log each changed field as a correction event
        for field, new_val in updates.items():
            if field.startswith("_"):
                continue
            old_val = listing.get(field)
            if old_val != new_val:
                try:
                    run_logger.write_correction({
                        "timestamp":  datetime.now().isoformat(timespec="seconds"),
                        "listing_id": safe_folder,
                        "field":      field,
                        "old_value":  old_val,
                        "new_value":  new_val,
                        "source":     "manual_review",
                    })
                except Exception:
                    pass
        # Capture old size before applying updates (needed for title patch below)
        old_size = listing.get("normalized_size") or listing.get("tagged_size") or ""
        listing.update(updates)
        # If normalized_size was corrected, replace the old size token in the title too
        if "normalized_size" in updates:
            new_size = updates["normalized_size"]
            title = listing.get("title", "")
            if old_size and old_size in title:
                listing["title"] = title.replace(old_size, new_size, 1)
        listing_path.write_text(json.dumps(listing, indent=2))
        listing["folder"] = safe_folder  # always include so frontend can re-render
    except Exception:
        return jsonify({"error": traceback.format_exc()}), 500
    return jsonify(listing), 200


@app.post("/reprice/<folder>")
def reprice_listing(folder):
    """POST /reprice/<folder> — re-run listing_writer on the saved listing.json to recalculate price.
    Used when the user corrects the brand and wants pricing updated."""
    safe_folder = Path(folder).name
    item_path = ITEMS_DIR / safe_folder
    listing_path = item_path / "listing.json"
    if not listing_path.exists():
        return jsonify({"error": "listing not found"}), 404

    existing = json.loads(listing_path.read_text())
    try:
        new_listing, write_usage = listing_writer.write(existing)
    except Exception:
        return jsonify({"error": traceback.format_exc()}), 500

    # Preserve fields that listing_writer doesn't re-generate
    for field in ("draft_url", "draft_error", "cost_gbp", "cost_tokens", "listed_date", "photos_folder"):
        if field in existing:
            new_listing.setdefault(field, existing[field])

    new_listing["folder"] = safe_folder
    listing_path.write_text(json.dumps(new_listing, indent=2))
    return jsonify(new_listing), 200


@app.post("/regen/<folder>")
def regen_listing(folder):
    """POST /regen/<folder>  Body: {"updates": {field: value, ...}}
    Applies field updates to listing.json then re-runs listing_writer so the
    title, description and price are regenerated with the corrected data."""
    safe_folder = Path(folder).name
    item_path = ITEMS_DIR / safe_folder
    listing_path = item_path / "listing.json"
    if not listing_path.exists():
        return jsonify({"error": "listing not found"}), 404

    body = request.get_json(force=True, silent=True) or {}
    updates = body.get("updates", {})

    existing = json.loads(listing_path.read_text())
    existing.update(updates)

    # Build hints — updates take priority, then fall back to existing confirmed values.
    # This ensures previously confirmed fields are never discarded on partial edits.
    hints = {}

    hints["brand"] = updates.get("brand") or existing.get("brand") or ""
    if not hints["brand"]:
        del hints["brand"]

    gender_val = updates.get("gender") or existing.get("gender")
    if gender_val:
        hints["gender"] = gender_val

    made_in_val = updates.get("made_in") or existing.get("made_in")
    if made_in_val:
        hints["made_in"] = made_in_val

    if updates.get("item_type"):
        hints["item_type"] = updates["item_type"]

    # Size: explicit update > preserve existing W/L > build W/L from waist+length (non-activewear only)
    _wl_pat = re.compile(r"^W\d+\s*L\d+$", re.IGNORECASE)
    _letter_pat = re.compile(r"^(XS|S|M|L|XL|XXL|XXXL)$", re.IGNORECASE)
    existing_size = str(existing.get("normalized_size") or "")
    if updates.get("normalized_size"):
        hints["size"] = updates["normalized_size"]
    elif _wl_pat.match(existing_size):
        hints["size"] = existing_size  # already confirmed W/L — preserve it
    elif _letter_pat.match(existing_size.strip()):
        hints["size"] = existing_size  # activewear letter size — never replace with W/L
    else:
        w = updates.get("trouser_waist") or existing.get("trouser_waist")
        l = updates.get("trouser_length") or existing.get("trouser_length")
        if w and l:
            hints["size"] = f"W{w} L{l}"

    try:
        new_listing, _ = listing_writer.write(existing, hints=hints or None)
    except Exception:
        return jsonify({"error": traceback.format_exc()}), 500

    # Preserve meta fields that listing_writer doesn't touch
    for field in ("draft_url", "draft_error", "cost_gbp", "cost_tokens", "listed_date", "photos_folder"):
        if field in existing:
            new_listing.setdefault(field, existing[field])

    # Preserve user-confirmed condition — regen must never reset what the user chose in the dropdown
    # (condition is changed via PATCH directly, so existing always holds the latest user choice)
    if existing.get("condition_summary") and not updates.get("condition_summary"):
        new_listing["condition_summary"] = existing["condition_summary"]

    # Preserve style if the user explicitly set it (AI might omit nullable fields)
    if existing.get("style") and not new_listing.get("style"):
        new_listing["style"] = existing["style"]

    # Restore locked fields — user edits take priority over AI
    if existing.get("category_locked") and existing.get("category"):
        new_listing["category"] = existing["category"]
        new_listing["category_locked"] = True

    new_listing["folder"] = safe_folder
    listing_path.write_text(json.dumps(new_listing, indent=2))
    return jsonify(new_listing), 200


@app.delete("/listing/<folder>")
def delete_listing(folder):
    """DELETE /listing/<folder> — remove the item folder and all its contents from disk."""
    import shutil
    safe_folder = Path(folder).name
    item_path = ITEMS_DIR / safe_folder
    if not item_path.is_dir():
        return jsonify({"error": "folder not found"}), 404
    try:
        shutil.rmtree(item_path)
    except Exception:
        return jsonify({"error": traceback.format_exc()}), 500
    return jsonify({"deleted": safe_folder}), 200


@app.post("/login/start")
def login_start():
    """Open a Playwright browser so the user can log into Vinted, then call /login/save."""
    if not _DRAFT_ENABLED:
        return jsonify({"error": "Playwright not available"}), 503
    if _vinted_login.get("active"):
        return jsonify({"status": "already_open"})

    ready = threading.Event()
    error_holder: list[str] = []

    def _run():
        try:
            from playwright.sync_api import sync_playwright
            pw = sync_playwright().start()
            _stealth = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
window.chrome = {runtime: {}};
"""
            browser = pw.chromium.launch(
                headless=False,
                channel="chrome",
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
            )
            context.add_init_script(_stealth)
            page = context.new_page()
            page.goto("https://www.vinted.co.uk")
            _vinted_login["pw"] = pw
            _vinted_login["browser"] = browser
            _vinted_login["context"] = context
            _vinted_login["active"] = True
            _vinted_login["done"]   = threading.Event()
            _vinted_login["saved"]  = threading.Event()
            ready.set()
            _vinted_login["done"].wait()   # block until /login/save signals us

            # storage_state() MUST be called from this thread (Playwright greenlet rule)
            save_path = _vinted_login.get("save_path")
            if save_path:
                try:
                    context.storage_state(path=save_path)
                    _vinted_login["save_error"] = None
                except Exception as exc:
                    _vinted_login["save_error"] = str(exc)
                _vinted_login["saved"].set()
        except Exception as exc:
            error_holder.append(str(exc))
            ready.set()
        finally:
            try:
                if "browser" in _vinted_login:
                    _vinted_login["browser"].close()
                if "pw" in _vinted_login:
                    _vinted_login["pw"].stop()
            except Exception:
                pass
            _vinted_login.clear()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    ready.wait(timeout=20)

    if error_holder:
        return jsonify({"error": error_holder[0]}), 500
    return jsonify({"status": "browser_open"})


@app.post("/login/save")
def login_save():
    """Save full Playwright storage state from the open Vinted browser session.

    storage_state() must be called from the Playwright background thread (greenlet rule),
    so we set save_path + signal done, then wait for the background thread to do the write.
    """
    done = _vinted_login.get("done")
    saved = _vinted_login.get("saved")
    if not done:
        return jsonify({"error": "No browser session open — call /login/start first."}), 400
    try:
        _vinted_login["save_path"] = str(ROOT / "auth_state.json")
        done.set()          # tell background thread to call storage_state() + close browser
        saved.wait(timeout=15)   # wait for background thread to finish writing
        err = _vinted_login.get("save_error")
        if err:
            return jsonify({"error": err}), 500
        return jsonify({"status": "saved", "method": "storage_state"})
    except Exception:
        return jsonify({"error": traceback.format_exc()}), 500


@app.get("/review/<folder>")
def review_listing_page(folder):
    """GET /review/<folder> — full review UI for a single listing."""
    safe_folder = Path(folder).name
    item_path = ITEMS_DIR / safe_folder
    listing_path = item_path / "listing.json"
    if not listing_path.exists():
        return jsonify({"error": "listing not found"}), 404
    listing = json.loads(listing_path.read_text())
    listing["folder"] = safe_folder

    # Collect photo filenames
    extensions = {".jpg", ".jpeg", ".png", ".webp"}
    photos = sorted(
        f.name for f in item_path.iterdir()
        if f.is_file() and f.suffix.lower() in extensions
    )

    return render_template(
        "review.html",
        listing=listing,
        photos=photos,
        folder=safe_folder,
        error_categories=run_logger.ERROR_CATEGORIES,
        draft_count=_draft_count(),
        active_tab="drafts",
    )


@app.post("/listing/<folder>/error-tags")
def set_error_tags(folder):
    """POST /listing/<folder>/error-tags  Body: {"tags": ["brand", "pricing"]}
    Saves error taxonomy tags to listing.json and logs to corrections.jsonl."""
    safe_folder = Path(folder).name
    listing_path = ITEMS_DIR / safe_folder / "listing.json"
    if not listing_path.exists():
        return jsonify({"error": "listing not found"}), 404
    try:
        body = request.get_json(force=True, silent=True) or {}
        tags = [t for t in body.get("tags", []) if t in run_logger.ERROR_CATEGORIES]
        listing = json.loads(listing_path.read_text())
        old_tags = listing.get("error_tags", [])
        listing["error_tags"] = tags
        listing_path.write_text(json.dumps(listing, indent=2))
        if old_tags != tags:
            try:
                run_logger.write_correction({
                    "timestamp":  datetime.now().isoformat(timespec="seconds"),
                    "listing_id": safe_folder,
                    "field":      "_error_tags",
                    "old_value":  old_tags,
                    "new_value":  tags,
                    "source":     "error_taxonomy",
                })
            except Exception:
                pass
    except Exception:
        return jsonify({"error": traceback.format_exc()}), 500
    return jsonify({"folder": safe_folder, "error_tags": tags}), 200


@app.get("/api/run-logs/summary")
def api_run_logs_summary():
    """GET /api/run-logs/summary — aggregate stats over all run logs."""
    return jsonify(run_logger.summarize_logs())


@app.get("/api/run-logs")
def api_run_logs():
    """GET /api/run-logs — all run log entries (most recent first, max 200)."""
    logs = run_logger.read_run_logs()
    return jsonify(list(reversed(logs))[:200])


@app.get("/health")
def health():
    return jsonify({"status": "ok"})
