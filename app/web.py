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
import traceback
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory

from app.config import ITEMS_DIR, ROOT
from app import extractor, listing_writer

try:
    from app import draft_creator
    _DRAFT_ENABLED = True
except Exception:
    draft_creator = None  # type: ignore
    _DRAFT_ENABLED = False

app = Flask(__name__)

# Haiku 4.5 pricing (USD per million tokens)
_INPUT_COST_PER_M = 0.80
_OUTPUT_COST_PER_M = 4.00
_USD_TO_GBP = 0.79

COST_LOG = ROOT / "cost_log.csv"


def _log_cost(folder: str, extract_usage: dict, write_usage: dict, listing: dict):
    total_in = extract_usage["input_tokens"] + write_usage["input_tokens"]
    total_out = extract_usage["output_tokens"] + write_usage["output_tokens"]
    cost_usd = (total_in * _INPUT_COST_PER_M + total_out * _OUTPUT_COST_PER_M) / 1_000_000
    cost_gbp = cost_usd * _USD_TO_GBP

    row = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "folder": folder,
        "brand": listing.get("brand", ""),
        "title": listing.get("title", ""),
        "price_gbp": listing.get("price_gbp", ""),
        "input_tokens": total_in,
        "output_tokens": total_out,
        "cost_usd": round(cost_usd, 5),
        "cost_gbp": round(cost_gbp, 5),
    }

    write_header = not COST_LOG.exists()
    with open(COST_LOG, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        if write_header:
            writer.writeheader()
        writer.writerow(row)

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

    try:
        item, extract_usage = extractor.extract(item_path)
        if "buy_price_gbp" in body:
            item["buy_price_gbp"] = float(body["buy_price_gbp"])
        listing, write_usage = listing_writer.write(item)
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 422
    except Exception:
        return jsonify({"error": traceback.format_exc()}), 500

    # Save listing JSON next to the photos
    out_path = item_path / "listing.json"
    out_path.write_text(json.dumps(listing, indent=2))

    _log_cost(folder, extract_usage, write_usage, listing)

    # Create draft on Vinted (optional — skip if no cookies file or Playwright unavailable)
    draft_url = None
    if _DRAFT_ENABLED and (ROOT / "vinted_cookies.json").exists():
        try:
            draft_url = draft_creator.create_draft(listing, item_path)
            if draft_url:
                listing["draft_url"] = draft_url
        except Exception as e:
            print(f"Draft creation failed: {e}")

    return jsonify(listing), 200


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
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 401
    except Exception:
        return jsonify({"error": traceback.format_exc()}), 500

    return jsonify({"draft_url": draft_url}), 200


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

    # Save photos: first 4 get core names, rest get numbered
    core_names = ["front", "tag", "material", "back"]
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
        saved.append(dest.name)

    if not saved:
        return jsonify({"error": "No valid photos saved"}), 400

    try:
        item, extract_usage = extractor.extract(item_path)
        if buy_price:
            item["buy_price_gbp"] = float(buy_price)
        listing, write_usage = listing_writer.write(item)
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 422
    except Exception:
        return jsonify({"error": traceback.format_exc()}), 500

    out_path = item_path / "listing.json"
    out_path.write_text(json.dumps(listing, indent=2))

    total_in = extract_usage["input_tokens"] + write_usage["input_tokens"]
    total_out = extract_usage["output_tokens"] + write_usage["output_tokens"]
    cost_usd = (total_in * _INPUT_COST_PER_M + total_out * _OUTPUT_COST_PER_M) / 1_000_000
    cost_gbp = cost_usd * _USD_TO_GBP
    listing["cost_gbp"] = round(cost_gbp, 4)
    listing["cost_tokens"] = {"input": total_in, "output": total_out}

    _log_cost(folder_name, extract_usage, write_usage, listing)

    # Create draft on Vinted
    if _DRAFT_ENABLED and (ROOT / "vinted_cookies.json").exists():
        try:
            draft_url = draft_creator.create_draft(listing, item_path)
            if draft_url:
                listing["draft_url"] = draft_url
                # Update saved listing.json with draft URL
                out_path.write_text(json.dumps(listing, indent=2))
        except Exception as e:
            print(f"Draft creation failed: {e}")
            listing["draft_error"] = str(e)

    return jsonify(listing), 200


@app.get("/drafts")
def drafts_page():
    listings = _get_all_listings()
    return render_template("drafts.html", listings=listings, draft_count=len(listings), active_tab="drafts")


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


@app.patch("/listing/<folder>")
def patch_listing(folder):
    """PATCH /listing/<folder>  Body: {field: value, ...}  — update specific fields in listing.json."""
    safe_folder = Path(folder).name
    listing_path = ITEMS_DIR / safe_folder / "listing.json"
    if not listing_path.exists():
        return jsonify({"error": "listing not found"}), 404
    updates = request.get_json(force=True, silent=True) or {}
    listing = json.loads(listing_path.read_text())
    listing.update(updates)
    listing_path.write_text(json.dumps(listing, indent=2))
    return jsonify(listing), 200


@app.get("/health")
def health():
    return jsonify({"status": "ok"})
