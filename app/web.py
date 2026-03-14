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
import traceback
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory

from app.config import ITEMS_DIR, ROOT
from app import extractor, listing_writer

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
        "brand":   body.get("hint_brand",   "").strip(),
        "size":    body.get("hint_size",    "").strip(),
        "gender":  body.get("hint_gender",  "").strip(),
        "damages": body.get("hint_damages", "").strip(),
    }.items() if v}

    try:
        item, extract_usage = extractor.extract(item_path, hints=hints or None)
        if "buy_price_gbp" in body:
            item["buy_price_gbp"] = float(body["buy_price_gbp"])
        listing, write_usage = listing_writer.write(item, hints=hints or None)

        # Save listing JSON next to the photos
        out_path = item_path / "listing.json"
        out_path.write_text(json.dumps(listing, indent=2))

        listing["folder"] = folder
        _log_cost(folder, extract_usage, write_usage, listing)
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 422
    except Exception:
        return jsonify({"error": traceback.format_exc()}), 500

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
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 401
    except Exception:
        return jsonify({"error": traceback.format_exc()}), 500

    return jsonify({"draft_url": result_url}), 200


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
        saved.append(dest.name)

    if not saved:
        return jsonify({"error": "No valid photos saved"}), 400

    hints = {k: v for k, v in {
        "brand":   request.form.get("hint_brand",   "").strip(),
        "size":    request.form.get("hint_size",    "").strip(),
        "gender":  request.form.get("hint_gender",  "").strip(),
        "damages": request.form.get("hint_damages", "").strip(),
    }.items() if v}

    try:
        item, extract_usage = extractor.extract(item_path, hints=hints or None)
        if buy_price:
            item["buy_price_gbp"] = float(buy_price)
        listing, write_usage = listing_writer.write(item, hints=hints or None)

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
    """PATCH /listing/<folder>  Body: {field: value, ...}  — update specific fields in listing.json."""
    safe_folder = Path(folder).name
    listing_path = ITEMS_DIR / safe_folder / "listing.json"
    if not listing_path.exists():
        return jsonify({"error": "listing not found"}), 404
    try:
        updates = request.get_json(force=True, silent=True) or {}
        listing = json.loads(listing_path.read_text())
        listing.update(updates)
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
            _vinted_login["done"] = threading.Event()
            ready.set()
            _vinted_login["done"].wait()   # block until /login/save is called
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
    """Capture cookies from the open Vinted browser and save to vinted_cookies.json."""
    ctx = _vinted_login.get("context")
    if not ctx:
        return jsonify({"error": "No browser session open — call /login/start first."}), 400
    try:
        cookies = ctx.cookies()
        COOKIES_FILE.write_text(json.dumps(cookies, indent=2))
        done = _vinted_login.get("done")
        if done:
            done.set()   # signal background thread to close browser
        return jsonify({"status": "saved", "count": len(cookies)})
    except Exception:
        return jsonify({"error": traceback.format_exc()}), 500


@app.get("/health")
def health():
    return jsonify({"status": "ok"})
