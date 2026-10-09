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
import shutil
import threading
import time
import traceback
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path

from flask import Flask, g, jsonify, redirect, render_template, request, send_from_directory, url_for

from app.config import ITEMS_DIR, ROOT
from app import extractor, listing_writer, run_logger
from app.services import pipeline as pipeline_svc
from app.services import item_store, listing_state, listing_edits
from app.services import listing_tracker
from app.services.category_validator import resolve_category_key as _resolve_category_key
from app.services import alias_memory as _alias_memory
from app.services import user_profile as profile_svc

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
from app.sales_api import sales as sales_blueprint
app.register_blueprint(sales_blueprint)

@app.before_request
def serialize_item_requests():
    folder = (request.view_args or {}).get('folder')
    if folder is None and request.path in {'/create-listing', '/create-draft', '/edit-draft'}:
        body = request.get_json(silent=True)
        folder = body.get('folder') if isinstance(body, dict) else None
    if folder is None or (request.method in {'GET', 'HEAD'} and not request.path.startswith(('/listing/', '/review/'))):
        return
    try:
        lock = listing_state.locked(ITEMS_DIR, folder)
        path = lock.__enter__()
    except ValueError:
        return jsonify(error='Invalid item folder.'), 400
    g.item_lock, g.item_path = lock, path
    expected = request.headers.get('If-Match')
    if request.method not in {'GET', 'HEAD', 'OPTIONS'} and expected and expected.strip('"') != listing_state.revision(path):
        return jsonify(error='This item changed in another tab. Reload it before saving; your changes have not been applied.', code='EDIT_CONFLICT'), 409


@app.after_request
def item_revision_headers(response):
    path = getattr(g, 'item_path', None)
    if path is None and response.is_json and response.status_code < 400 and request.path == '/upload':
        body = response.get_json(silent=True)
        if isinstance(body, dict) and body.get('folder'):
            path = listing_state.item_path(ITEMS_DIR, body['folder'])
    if path is not None and response.status_code < 400:
        revision = listing_state.revision(path)
        if revision:
            response.headers['X-Item-Revision'] = revision
        response.headers['Cache-Control'] = 'no-store'
    elif request.path in {'/drafts', '/sold', '/insights', '/api/listings', '/api/sales'}:
        response.headers['Cache-Control'] = 'no-store'
    return response


def cache_policy(path: str, versioned: bool) -> str | None:
    """Cache-Control for static files and item photos; None = leave the route's own policy."""
    if path.startswith("/static/"):
        return "public, max-age=31536000, immutable" if versioned else "public, max-age=86400"
    if path.startswith("/items/"):
        return "private, no-cache"        # revalidate: an unchanged photo costs a tiny 304, not a re-download
    return None


@app.after_request
def compress_text(response):
    """Gzip pages and JSON (Drafts carries the whole item list); files are left alone."""
    import gzip
    policy = cache_policy(request.path, bool(request.args.get("v"))) if response.status_code in (200, 304) else None
    if policy:
        response.headers["Cache-Control"] = policy
    if (response.direct_passthrough or not 200 <= response.status_code < 300 or response.headers.get("Content-Encoding")
            or "gzip" not in request.headers.get("Accept-Encoding", "")):
        return response
    kind = response.mimetype or ""
    if not (kind.startswith("text/") or kind in ("application/json", "application/javascript")):
        return response
    data = response.get_data()
    if len(data) < 1400:
        return response
    response.set_data(gzip.compress(data, 6))
    response.headers["Content-Encoding"] = "gzip"
    response.headers["Content-Length"] = str(len(response.get_data()))
    response.vary.add("Accept-Encoding")
    return response


@app.teardown_request
def release_item_request(error):
    lock = g.pop('item_lock', None)
    if lock is not None:
        lock.__exit__(None, None, None)


try:
    item_store.init_db()
except Exception:
    pass  # non-fatal — app runs without the metadata index


@app.get("/manifest.json")
def serve_manifest():
    return send_from_directory(ROOT / "app" / "static", "manifest.json",
                               mimetype="application/manifest+json")


@app.errorhandler(Exception)
def handle_unhandled_exception(e):
    """Catch-all: always return JSON instead of an HTML error page."""
    return jsonify({"error": traceback.format_exc()}), 500

# Pricing (USD per million tokens)
_PRICES = {
    "haiku":  {"in": 1.00, "out": 5.00},
    "sonnet": {"in": 3.00, "out": 15.00},
    "gpt-6-luna": {"in": 0.10, "out": 0.50},
    "gpt-6.1-sol": {"in": 2.00, "out": 10.00},
}
_USD_TO_GBP = 0.79

COST_LOG = ROOT / "cost_log.csv"


def _model_key(model: str) -> str:
    if model in {"gpt-6-luna", "gpt-6.1-sol"}:
        return model
    return "sonnet" if "sonnet" in model.lower() else "haiku"


def _calc_cost_usd(usage: dict) -> float:
    if "calls" in usage:
        return sum(c.get("cost_usd") or 0 for c in usage["calls"])
    key = _model_key(usage.get("model", ""))
    p = _PRICES[key]
    return (usage["input_tokens"] * p["in"] + usage["output_tokens"] * p["out"]) / 1_000_000


def _log_cost(folder: str, extract_usage: dict, write_usage: dict, listing: dict):
    cost_usd = _calc_cost_usd(extract_usage) + _calc_cost_usd(write_usage)
    cost_gbp = cost_usd * _USD_TO_GBP

    calls = extract_usage.get("calls", []) + write_usage.get("calls", [])
    row = {
        "run_id": calls[0]["run_id"] if calls else "",
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

    # Upgrade old CSV headers without misaligning newly added run IDs.
    if COST_LOG.exists():
        with COST_LOG.open(newline="") as f:
            reader = csv.DictReader(f)
            old_header = reader.fieldnames
            old_rows = list(reader)
        if old_header != list(row):
            import tempfile, os
            with tempfile.NamedTemporaryFile(mode="w", newline="", dir=COST_LOG.parent, delete=False) as f:
                temporary = Path(f.name)
                writer = csv.DictWriter(f, fieldnames=row.keys(), extrasaction="ignore")
                writer.writeheader()
                writer.writerows(old_rows)
            try:
                os.replace(temporary, COST_LOG)
            finally:
                temporary.unlink(missing_ok=True)

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
        buy_price = float(body["buy_price_gbp"]) if "buy_price_gbp" in body else None
        pricing_mode = profile_svc.load().get("pricing_mode", "balanced")
        price_check = _price_check_perk()
        listing, extract_usage, write_usage, extract_log, write_log = pipeline_svc.run_pipeline(
            item_path, hints, buy_price_gbp=buy_price, pricing_mode=pricing_mode, price_check=price_check
        )
        if price_check and listing.get("web_price_perk"):
            _spend_perk("price_check")

        # Save listing JSON next to the photos
        from app.services import review_evidence
        review_evidence.capture(item_path, listing, extract_log=extract_log, write_log=write_log,
                                pipeline_latency_ms=round((time.perf_counter() - _t0) * 1000))
        out_path = item_path / "listing.json"
        listing_state.write(out_path, listing)

        listing["folder"] = folder
        _log_cost(folder, extract_usage, write_usage, listing)
        _write_run_log(folder, extract_log, write_log, extract_usage, write_usage, listing,
                       round((time.perf_counter() - _t0) * 1000))
        _sync_item_status(folder, listing)
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

        # ── Pre-flight: low brand confidence gate ─────────────────────────────
        if listing.get("brand_confidence") == "low" and not listing.get("brand_confirmed"):
            brand = listing.get("brand") or ""
            return jsonify({
                "code": "LOW_BRAND_CONFIDENCE",
                "error": f"Brand '{brand}' is low-confidence — confirm before drafting",
            }), 409

        # ── Pre-flight: unresolved category gate ──────────────────────────────
        category = listing.get("category") or ""
        if category and not _resolve_category_key(category) and not listing.get("category_locked"):
            return jsonify({
                "code": "CATEGORY_UNRESOLVED",
                "error": f"Category '{category}' has no Vinted mapping — correct before drafting",
                "category": category,
            }), 409

        draft_url = draft_creator.create_draft(listing, item_path)
        # Clear any previous draft error and persist draft_url
        listing.pop("draft_error", None)
        listing["draft_url"] = draft_url
        listing_state.write(listing_path, listing)
        item_store.set_status(folder, "drafted")
        listing_tracker.record_draft_snapshot(folder, listing)
    except draft_creator.VintedAuthError as e:
        return jsonify({"error": str(e), "code": "VINTED_AUTH_EXPIRED"}), 401
    except Exception as exc:
        # Persist a short operator-friendly error; full traceback stays in logs only
        err_msg = _draft_error_summary(exc)
        try:
            listing = json.loads(listing_path.read_text())
            listing["draft_error"] = err_msg
            listing_state.write(listing_path, listing)
        except Exception:
            pass
        item_store.set_status(folder, "error", last_error=err_msg)
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


def _resize_photo(path: Path, *, prepared: bool = False) -> Path:
    """Resize a photo to ≤ _UPLOAD_MAX_DIM px and ≤ _UPLOAD_MAX_BYTES in-place.

    Normalises to JPEG and strips EXIF; verified prepared JPEGs pass through.
    Returns the (possibly renamed) path.
    """
    try:
        from PIL import Image, ImageOps
        orig_bytes = path.stat().st_size
        with Image.open(path) as source:
            safe_info = {"jfif", "jfif_version", "jfif_unit", "jfif_density", "progressive", "progression"}
            if (prepared and source.format == "JPEG" and source.mode == "RGB"
                    and max(source.size) <= _UPLOAD_MAX_DIM and orig_bytes <= _UPLOAD_MAX_BYTES
                    and not source.getexif() and set(source.info) <= safe_info):
                source.verify()
                return path  # Already prepared; avoid a second encode and CPU/quality cost.
            img = ImageOps.exif_transpose(source).convert("RGB")
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


@app.post("/prepare-photo")
def prepare_photo():
    """Fallback conversion only; no saved listing or billable AI work."""
    from flask import Response
    from app.services.photo_prepare import normalize, MAX_BYTES, PhotoPreparationError
    photo = request.files.get("photo")
    if photo is None:
        return jsonify(error="Select a photo first."), 400
    try:
        image = normalize(photo.stream.read(MAX_BYTES + 1))
    except PhotoPreparationError as error:
        return jsonify(error=str(error)), 422
    return Response(image, mimetype="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/")
def index():
    profile = profile_svc.load()
    return render_template(
        "index.html",
        active_tab="upload",
        draft_count=_draft_count(),
        profile=profile,
        is_reseller=profile_svc.is_reseller(profile),
        onboarded=bool(profile.get("onboarded_at")),
        daily_goal=profile_svc.daily_goal(profile),
        progress=_progress(),
    )


@app.get("/welcome")
def welcome_page():
    """First-run onboarding: a few taps, then name and email."""
    return render_template("onboarding.html", profile=profile_svc.load())


@app.get("/tour")
def tour_page():
    """How it works: a short story-style walkthrough after the welcome (rewatch from Settings)."""
    return render_template("tour.html")


@app.post("/api/onboarding")
def save_onboarding():
    try:
        profile = profile_svc.onboard(request.get_json(silent=True))
    except ValueError as error:
        return jsonify(error=str(error)), 422
    return jsonify(name=profile["name"], photo_mode=profile["photo_mode"],
                   daily_goal=profile_svc.daily_goal(profile))


@app.after_request
def upload_timing(response):
    timings = getattr(g, "upload_timings", None)
    if timings is not None:
        timings["total"] = (time.perf_counter() - g.upload_started) * 1000
        if "prepare" in timings:
            timings["pipeline"] = max(0, timings["total"] - timings["receive"] - timings["prepare"])
        response.headers["Server-Timing"] = ", ".join(
            f"{name};dur={elapsed:.1f}" for name, elapsed in timings.items())
        print("[upload_timing] " + json.dumps({"status": response.status_code,
              "bytes": request.content_length, "milliseconds": timings}), flush=True)
    return response


@app.post("/upload")
def upload_listing():
    """Mobile upload endpoint. Accepts multipart form with photos + buy_price.
    Photos should be uploaded in order: front, tag, material, back, then extras.
    Auto-creates an item folder and runs the full pipeline."""
    g.upload_started = time.perf_counter()
    g.upload_timings = {}
    files = request.files.getlist("photos")
    g.upload_timings["receive"] = (time.perf_counter() - g.upload_started) * 1000
    if not files or all(f.filename == "" for f in files):
        return jsonify({"error": "No photos uploaded"}), 400

    from app.services import measurements
    try:
        explicit_roles = measurements.parse_roles(request.form.get("photo_roles"), len(files))
    except (ValueError, TypeError):
        return jsonify(error="Choose valid, unique photo roles; use Extra for other photos."), 422

    if len(files) > 20:
        return jsonify(error="Upload at most 20 photos."), 422

    buy_price = request.form.get("buy_price", "").strip()
    folder_name = f"upload_{uuid.uuid4().hex[:8]}"
    item_path = ITEMS_DIR / folder_name
    item_path.mkdir(parents=True, exist_ok=True)

    # Save photos as temp files, then score and rename to role names
    from app.services import photo_roles as _photo_roles
    temp_paths: list[Path] = []
    for i, f in enumerate(files):
        if f.filename == "":
            continue
        ext = Path(f.filename).suffix.lower() or ".jpg"
        if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
            continue
        temp_dest = item_path / f"_temp_{i:02d}{ext}"
        f.save(temp_dest)
        temp_dest = _resize_photo(temp_dest, prepared=request.form.get("prepared_photos") == "1")
        temp_paths.append(temp_dest)

    if not temp_paths:
        return jsonify({"error": "No valid photos saved"}), 400

    # Explicit mobile roles override the legacy heuristic. Never shift missing slots.
    if explicit_roles is not None and len(temp_paths) != len(explicit_roles):
        return jsonify(error="A selected photo format is unsupported."), 422
    try:
        if explicit_roles is not None:
            role_map = measurements.role_map(temp_paths, explicit_roles)
            role_confidence = {role: 1.0 for role in role_map}
        else:
            role_map, role_confidence = _photo_roles.assign_roles(temp_paths)
    except Exception:
        return jsonify(error="Could not assign photo roles."), 422

    # Rename temp files to role names
    saved = []
    saved_roles = {}
    for role, src in role_map.items():
        if src is None:
            continue
        ext = src.suffix
        dest = item_path / f"{role}{ext}"
        src.rename(dest)
        saved.append(dest.name)
        saved_roles[role] = dest.name

    # Persist role assignments + confidence for review/observability
    try:
        import json as _json
        (item_path / "photo_roles.json").write_text(
            _json.dumps({
                "roles": saved_roles,
                "confidence": role_confidence,
                "low_confidence": _photo_roles.low_confidence_roles(role_confidence),
            }, indent=2)
        )
    except Exception:
        pass

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
        g.upload_timings["prepare"] = (time.perf_counter() - g.upload_started) * 1000 - g.upload_timings["receive"]
        _t0 = time.perf_counter()
        buy_price_gbp = float(buy_price) if buy_price else None
        pricing_mode = profile_svc.load().get("pricing_mode", "balanced")
        price_check = _price_check_perk()
        listing, extract_usage, write_usage, extract_log, write_log = pipeline_svc.run_pipeline(
            item_path, hints, buy_price_gbp=buy_price_gbp, pricing_mode=pricing_mode, price_check=price_check
        )
        if price_check and listing.get("web_price_perk"):
            _spend_perk("price_check")

        # upload adds cost fields to the listing (not present in create-listing response)
        cost_usd = _calc_cost_usd(extract_usage) + _calc_cost_usd(write_usage)
        cost_gbp = cost_usd * _USD_TO_GBP
        listing["cost_gbp"] = (listing.get("run_stats") or {}).get("total_cost_gbp") or round(cost_gbp, 5)
        listing["model_calls"] = extract_usage.get("calls", []) + write_usage.get("calls", [])
        listing["cost_complete"] = extract_usage.get("cost_complete", True) and write_usage.get("cost_complete", True)
        listing["cost_status"] = "estimated" if listing["cost_complete"] else "incomplete"
        listing["cost_tokens"] = {
            "input":  extract_usage["input_tokens"] + write_usage["input_tokens"],
            "output": extract_usage["output_tokens"] + write_usage["output_tokens"],
        }

        from app.services import review_evidence
        review_evidence.capture(item_path, listing, extract_log=extract_log, write_log=write_log,
                                pipeline_latency_ms=round((time.perf_counter() - _t0) * 1000))
        out_path = item_path / "listing.json"
        listing_state.write(out_path, listing)

        listing["folder"] = folder_name
        _log_cost(folder_name, extract_usage, write_usage, listing)
        _write_run_log(folder_name, extract_log, write_log, extract_usage, write_usage, listing,
                       round((time.perf_counter() - _t0) * 1000))
        _sync_item_status(folder_name, listing)
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 422
    except Exception:
        return jsonify({"error": traceback.format_exc()}), 500

    return jsonify(listing), 200


def _progress(listings=None) -> dict:
    from app.services import progress, sales_history
    profile = profile_svc.load()
    return progress.summary(listings if listings is not None else _get_all_listings(), ITEMS_DIR,
                            profile_svc.daily_goal(profile), sales_history.today(),
                            perks_used=profile.get("perks_used") or {})


def _price_check_perk() -> bool:
    """A Pro price check is waiting (earned from daily chests and level-ups)."""
    try:
        return any(p["id"] == "price_check" and p["left"] > 0 for p in _progress()["perks"])
    except Exception:
        return False


def _spend_perk(perk: str) -> None:
    profile = profile_svc.load()
    used = dict(profile.get("perks_used") or {})
    used[perk] = int(used.get(perk, 0) or 0) + 1
    profile["perks_used"] = used
    profile_svc.save(profile)


@app.get("/api/progress")
def progress_api():
    p = _progress()
    return jsonify({k: p[k] for k in ("streak", "today_met", "today_count", "goal", "xp", "xp_today", "level",
                                      "quests", "chest_ready", "badges", "perks")})


@app.post("/api/progress/skin")
def progress_skin():
    skin = (request.get_json(silent=True) or {}).get("skin")
    if not any(s["id"] == skin and s["unlocked"] for s in _progress()["skins"]):
        return jsonify(error="That coin isn't unlocked yet."), 422
    profile = profile_svc.load()
    profile["coin_skin"] = skin
    profile_svc.save(profile)
    return jsonify(skin=skin)


@app.get("/progress")
def progress_page():
    from app.services import progress
    return render_template("progress.html", p=_progress(), active_tab="progress",
                           rules=[("List an item", progress.XP_LIST), ("Full photo set", progress.XP_FULL_SET),
                                  ("★ Premium piece", progress.XP_PREMIUM), ("🔥 Hot piece (premium, £40+)", progress.XP_HOT),
                                  ("Mark it sold", progress.XP_SOLD)])


@app.get("/drafts")
def drafts_page():
    from app.services import progress
    everything = _get_all_listings()
    for item in everything:
        item['tier'] = progress.tier(item)
    listings = [item for item in everything if item['inventory_status'] != 'sold']
    try:
        folders = {item['folder'] for item in listings}
        review_count = len(folders & set(item_store.get_items_needing_review()))
    except Exception:
        review_count = 0
    return render_template("drafts.html", listings=listings, draft_count=len(listings), active_tab="drafts",
                           review_count=review_count, progress=_progress(everything))


@app.get("/sold")
def sold_page():
    from app.services import sales_history
    rows = sales_history.read_all()
    try:
        summary = sales_history.monthly_summary(rows, request.args.get('month'))
    except ValueError:
        return jsonify(error="Choose a valid month."), 422
    listings = _get_all_listings()
    sold = sorted((item for item in listings if item['inventory_status'] == 'sold'
                   and (item['outcome'].get('sold_date') or '').startswith(summary['month']+'-')),
                  key=lambda item: item['outcome'].get('sold_date') or '', reverse=True)
    import calendar
    year, month = (int(part) for part in summary['month'].split('-'))
    today = sales_history.today()
    return render_template("drafts.html", listings=sold, sold_mode=True, sale_summary=summary,
                           draft_count=sum(item['inventory_status'] != 'sold' for item in listings),
                           active_tab="sold", month_is_current=(year, month) == (today.year, today.month),
                           month_name=calendar.month_name[month] + ('' if year == today.year else f' {year}'),
                           month_short=calendar.month_abbr[month])


@app.get("/connect")
def connect_page():
    return render_template("connect.html", active_tab="connect")


@app.get("/insights")
def insights_page():
    """What you sell, what it sells for and how often you list (tap the chart on Sold)."""
    from app.services import insights, progress as progress_svc, sales_history
    listings = _get_all_listings()
    for item in listings:
        made = progress_svc.created_on(item, ITEMS_DIR / item["folder"])
        item["created_date"] = made.isoformat() if made else None
    data = insights.build(listings, sales_history.read_all(), sales_history.today(), request.args.get("period", "90d"))
    return render_template("insights.html", data=data, active_tab="sold",
                           draft_count=sum(item["inventory_status"] != "sold" for item in listings))


@app.get("/stats")
def stats_page():
    listings = _get_all_listings()
    cost_history = _get_cost_history()
    stats = _compute_stats(listings, cost_history)
    from app.services import sales_history
    return render_template("stats.html", stats=stats, cost_history=cost_history, sales_metrics=sales_history.metrics(),
                           draft_count=len(listings), active_tab="stats")


def _backup_revision(folder: Path) -> str:
    """Content fingerprint; unchanged by a server restore, so phones skip unchanged items."""
    from app.services import item_backup
    try:
        return item_backup.revision(folder)
    except OSError:
        return ""


@app.get("/api/listings")
def api_listings():
    listings = _get_all_listings()
    for listing in listings:
        listing["backup_revision"] = _backup_revision(ITEMS_DIR / listing["folder"])
    return jsonify(listings)


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

@app.url_defaults
def _static_version(endpoint, values):
    """Static URLs carry the file's modified time, so phones fetch new CSS/JS after every deploy."""
    if endpoint == "static" and "filename" in values and "v" not in values:
        try:
            values["v"] = int((Path(app.static_folder) / values["filename"]).stat().st_mtime)
        except OSError:
            pass


@app.context_processor
def _nav_counts():
    """Red counts on the bottom bar (drafts, sold this month) and today's listings."""
    from datetime import date
    from app.services import sales_history
    try:
        rows = sales_history.read_all()
    except Exception:
        rows = []
    month = date.today().strftime('%Y-%m')
    sold_count = sum(1 for row in rows if row.get('status') == 'sold' and (row.get('sold_date') or '').startswith(month))
    from app.services import progress
    today, made_today = sales_history.today(), 0
    if ITEMS_DIR.exists():
        for item_dir in ITEMS_DIR.iterdir():
            listing = item_dir / "listing.json"
            if item_dir.is_dir() and not item_dir.name.startswith("_") and listing.exists():
                # Saved creation time, not file time: a restore from backup resets file times.
                try:
                    made_today += progress.created_on(json.loads(listing.read_text()), item_dir) == today
                except (OSError, ValueError):
                    continue
    profile = profile_svc.load()
    name = profile.get("name") or ""
    # Route-supplied values (e.g. draft_count) take precedence over these defaults.
    return {"sold_count": sold_count, "today_count": made_today, "draft_count": _draft_count(),
            "profile_initial": name[:1].upper(), "coin_skin": profile.get("coin_skin") or "brass"}


def _draft_count() -> int:
    from app.services import sales_history
    sold = {row['folder'] for row in sales_history.read_all() if row['status'] == 'sold'}
    if not ITEMS_DIR.exists():
        return 0
    return sum(
        1 for d in ITEMS_DIR.iterdir()
        if d.is_dir() and not d.name.startswith("_") and d.name not in sold and (d / "listing.json").exists()
    )


GRID_THUMB = "_grid.jpg"   # small card image; not backed up (underscore files aren't), rebuilt when the photo changes


def _grid_thumb(item_dir: Path, source: Path) -> str:
    """URL of a ~480px card image instead of the full 2048px photo (saves bandwidth on every Drafts load)."""
    thumb = item_dir / GRID_THUMB
    try:
        if not thumb.exists() or thumb.stat().st_mtime < source.stat().st_mtime:
            from PIL import Image, ImageOps
            with Image.open(source) as image:
                image = ImageOps.exif_transpose(image).convert("RGB")
                image.thumbnail((480, 480))
                tmp = item_dir / (GRID_THUMB + ".tmp")
                image.save(tmp, "JPEG", quality=78, optimize=True)
                tmp.replace(thumb)
        return f"/items/{item_dir.name}/{GRID_THUMB}?v={int(thumb.stat().st_mtime)}"
    except Exception:
        return f"/items/{item_dir.name}/{source.name}"


def _get_all_listings() -> list[dict]:
    listings = []
    if not ITEMS_DIR.exists():
        return listings
    from app.services import sales_history, crosslist, progress as progress_svc
    outcomes = {row['folder']: row for row in sales_history.read_all()}
    today = sales_history.today()
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
            listing['outcome'] = outcomes.get(item_dir.name)
            listing['inventory_status'] = (listing['outcome'] or {}).get('status', 'draft')
            crosslist.decorate(listing, listing['outcome'])
            listing['stale_days'] = progress_svc.stale_days(listing, item_dir, today)
            # A saved thumbnail URL may outlive its file after a restore.
            listing.pop("thumbnail_url", None)
            for role in ["front", "back", "brand"]:
                for ext in [".jpg", ".jpeg", ".png", ".webp"]:
                    if (item_dir / f"{role}{ext}").exists():
                        listing["thumbnail_url"] = _grid_thumb(item_dir, item_dir / f"{role}{ext}")
                        break
                if listing.get("thumbnail_url"):
                    break
            # Restored as a summary: a small preview until the full photos are fetched.
            if not listing.get("thumbnail_url") and (item_dir / "_thumb.jpg").exists():
                listing["thumbnail_url"] = f"/items/{item_dir.name}/_thumb.jpg"
            # Lazy migration: write status to DB if this item has no record yet
            item_store.sync_from_listing(item_dir.name, listing)
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

    from app.services import model_usage
    events = model_usage.read_events()
    run_ids = {e.get("run_id") for e in events if e.get("run_id")}
    # Ledger events include paid responses that never produced a listing.
    # Historical CSV estimates are additive, except runs already represented in the ledger.
    legacy_rows = [r for r in cost_history if not r.get("run_id") or r["run_id"] not in run_ids]
    total_spend_gbp = sum(float(r.get("cost_gbp", 0)) for r in legacy_rows)
    total_spend_gbp += sum(e.get("cost_gbp") or 0 for e in events)
    count = len(legacy_rows) + len(run_ids)
    avg_cost = total_spend_gbp / count if count else 0
    unpriced_calls = sum(e.get("cost_gbp") is None for e in events)
    def tokens(value):
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0
    # Anthropic input_tokens excludes both cache writes and cache reads.
    total_input = sum(tokens(r.get("input_tokens")) for r in legacy_rows)
    total_input += sum(tokens(e.get("input_tokens")) + tokens(e.get("cache_creation_input_tokens"))
                       + tokens(e.get("cache_read_input_tokens")) for e in events)
    total_output = sum(tokens(r.get("output_tokens")) for r in legacy_rows)
    total_output += sum(tokens(e.get("output_tokens")) for e in events)
    cache_writes = sum(tokens(e.get("cache_creation_input_tokens")) for e in events)
    cache_reads = sum(tokens(e.get("cache_read_input_tokens")) for e in events)
    labels = {l.get("folder"): l.get("brand") for l in listings}
    recent = {}
    for event in events:
        key = event.get("run_id") or event["id"]
        row = recent.setdefault(key, {"folder": event.get("item"), "brand": labels.get(event.get("item")),
                                     "timestamp": event.get("timestamp") or "", "input_tokens": 0,
                                     "output_tokens": 0, "cost_gbp": 0, "cost_complete": True})
        row["input_tokens"] += tokens(event.get("input_tokens")) + tokens(event.get("cache_creation_input_tokens")) + tokens(event.get("cache_read_input_tokens"))
        row["output_tokens"] += tokens(event.get("output_tokens"))
        row["cost_gbp"] += event.get("cost_gbp") or 0
        row["cost_complete"] &= event.get("cost_gbp") is not None
    recent_rows = list(recent.values()) + [dict(r, cost_complete=True) for r in legacy_rows]
    recent_rows.sort(key=lambda r: r.get("timestamp") or "", reverse=True)
    total_value = sum(float(l.get("price_gbp", 0)) for l in listings)

    # ROI: items where we know the buy price
    profit_items = [
        l for l in listings
        if l.get("buy_price_gbp") is not None and l.get("price_gbp")
    ]
    potential_profit = sum(
        float(l["price_gbp"]) - float(l["buy_price_gbp"])
        for l in profit_items
    )

    brands = Counter(l.get("brand") or "Unknown" for l in listings)

    return {
        "total_items": total_items,
        "total_spend_gbp": round(total_spend_gbp, 5),
        "unpriced_calls": unpriced_calls,
        "avg_cost_gbp": round(avg_cost, 4),
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "cache_write_tokens": cache_writes,
        "cache_read_tokens": cache_reads,
        "recent_usage": recent_rows[:12],
        "total_value_gbp": round(total_value, 2),
        "potential_profit_gbp": round(potential_profit, 2),
        "profit_item_count": len(profit_items),
        "brands": [{"brand": b, "count": c} for b, c in brands.most_common(10)],
    }


def _draft_error_summary(exc: Exception) -> str:
    """Return a short operator-friendly error message for draft creation failures.

    Full traceback is never stored in listing.json — it stays in logs/console only.
    """
    msg = str(exc).strip()
    # Strip long Python paths that are meaningless to an operator
    if "\n" in msg:
        msg = msg.splitlines()[-1].strip()
    return msg[:200] if msg else "Draft creation failed — check logs for details"


def _sync_item_status(folder: str, listing: dict) -> None:
    """Derive and write item status to DB. Swallows all errors."""
    try:
        from app.services import sales_history
        outcome = sales_history.get(folder)
        status, review_needed = item_store.derive_status(listing)
        if outcome and outcome['status'] == 'sold':
            status, review_needed = 'sold', False
        item_store.set_status(folder, status, review_needed=review_needed)
    except Exception:
        pass


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
        "extract_input_tokens":  extract_usage.get("input_tokens", 0),
        "extract_output_tokens": extract_usage.get("output_tokens", 0),
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
        "model_calls": extract_usage.get("calls", []) + write_usage.get("calls", []),
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
    from app.services import sales_history
    listing['outcome'] = sales_history.get(safe_folder)
    listing['sales_history'] = sales_history.comparisons(listing)
    from app.services import crosslist
    crosslist.decorate(listing, listing['outcome'])
    from app.services.ebay_comps import search_links, EbayQueryError
    try:
        listing['ebay_links'] = search_links(listing)
    except EbayQueryError:
        pass
    return jsonify(listing), 200


@app.route("/listing/<folder>/feedback", methods=["GET", "POST"])
def listing_feedback(folder):
    from app.services import review_evidence
    path = ITEMS_DIR / Path(folder).name
    if not (path / "listing.json").is_file():
        return jsonify(error="Listing not found"), 404
    if request.method == "GET":
        return jsonify(review_evidence.read(path))
    try:
        result = review_evidence.save(path, request.get_json(silent=True))
    except ValueError as error:
        return jsonify(error=str(error)), 422
    return jsonify(result)


@app.post("/listing/<folder>/check-evidence")
def check_saved_evidence(folder):
    from app.services import review_evidence
    path = ITEMS_DIR / Path(folder).name
    if not (path / "listing.json").is_file():
        return jsonify(error="Listing not found"), 404
    listing = review_evidence.recheck(path)
    listing['folder'] = path.name
    _sync_item_status(path.name, listing)
    return jsonify(listing)


@app.post("/listing/<folder>/measurements")
def confirm_measurements(folder):
    from app.services import measurements
    from app.validate_listing import validate_or_raise
    safe_folder = Path(folder).name
    path = ITEMS_DIR / safe_folder / "listing.json"
    if not path.exists():
        return jsonify(error="Listing not found"), 404
    body = request.get_json(silent=True)
    try:
        values = measurements.confirmed(body.get("measurements") if isinstance(body, dict) else None)
        listing = json.loads(path.read_text())
        listing["measurements"] = values
        measurements.apply_description(listing)
        validate_or_raise(listing)
    except (ValueError, TypeError):
        return jsonify(error="Enter valid measurements in cm (0.5–250); each dimension once."), 422
    listing_state.write(path, listing)
    _sync_item_status(safe_folder, listing)
    listing["folder"] = safe_folder
    return jsonify(listing)


@app.patch("/listing/<folder>")
def patch_listing(folder):
    """PATCH /listing/<folder>  Body: {field: value, ...}  — update specific fields in listing.json.
    Changed fields are logged as correction events in data/corrections.jsonl."""
    safe_folder = Path(folder).name
    listing_path = ITEMS_DIR / safe_folder / "listing.json"
    if not listing_path.exists():
        return jsonify({"error": "listing not found"}), 404
    try:
        updates = request.get_json(force=True, silent=True)
        listing_edits.validate_updates(updates)
        if any(k in updates for k in ("measurements", "measurement_proposals")):
            return jsonify(error="Use the measurement confirmation form."), 422
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
        # Snapshot before update for alias detection
        old_listing = dict(listing)
        # Capture old size before applying updates (needed for title patch below)
        old_size = listing.get("normalized_size") or listing.get("tagged_size") or ""
        listing = listing_edits.apply(listing, updates)

        # ── Alias memory capture ──────────────────────────────────────────────
        # Brand: save alias + mark confirmed when low-confidence brand is corrected
        if "brand" in updates:
            old_brand = old_listing.get("brand") or ""
            new_brand = updates["brand"] or ""
            if old_listing.get("brand_confidence") == "low" and old_brand != new_brand and new_brand:
                _alias_memory.save_brand_alias(old_brand, new_brand)
                listing["brand_confirmed"] = True

        # Category: save alias + lock when category is corrected
        if "category" in updates:
            old_cat = old_listing.get("category") or ""
            new_cat = updates["category"] or ""
            if old_cat != new_cat and new_cat:
                _alias_memory.save_category_alias(old_cat, new_cat)
                listing["category_locked"] = True

        # Item type: save alias + clear category_locked so category re-validates
        if "item_type" in updates:
            old_it = old_listing.get("item_type") or ""
            new_it = updates["item_type"] or ""
            if old_it != new_it and new_it:
                _alias_memory.save_item_type_alias(old_it, new_it)
                listing.pop("category_locked", None)
        # If condition_summary or flaws_note changed, recompute condition_line immediately
        if "condition_summary" in updates or "flaws_note" in updates:
            from app.services import condition as _cond_svc
            _cond_svc.apply_condition(listing)
        # If normalized_size was corrected, replace the old size token in the title too
        if "normalized_size" in updates:
            new_size = updates["normalized_size"]
            title = listing.get("title", "")
            if old_size and 'title' not in (old_listing.get('manual_fields') or []):
                from app.services.premium_features import retitle_size
                if new_size:
                    retitle_size(listing, old_size)
                elif old_size in title:
                    listing["title"] = title.replace(old_size, '', 1)
        from app.services import review_evidence
        review_evidence.capture(listing_path.parent, old_listing)
        from app.validate_listing import validate_or_raise
        validate_or_raise(listing)
        from app.services.pricing import refresh_profitability
        refresh_profitability(listing)
        listing_state.write(listing_path, listing)
        _sync_item_status(safe_folder, listing)
        listing["folder"] = safe_folder  # always include so frontend can re-render
    except ValueError as error:
        return jsonify(error=str(error)), 422
    except Exception:
        return jsonify({"error": traceback.format_exc()}), 500
    return jsonify(listing), 200


@app.post("/reprice/<folder>")
def reprice_listing(folder):
    """Propose a price from saved facts/history without AI or copy changes."""
    safe_folder = Path(folder).name
    item_path = ITEMS_DIR / safe_folder
    listing_path = item_path / "listing.json"
    if not listing_path.exists():
        return jsonify({"error": "listing not found"}), 404

    existing = json.loads(listing_path.read_text())
    from copy import deepcopy
    from app.services import pricing
    proposal = deepcopy(existing)
    proposal['folder'] = safe_folder
    proposal['price_gbp'] = existing.get('ai_price_gbp', existing.get('price_gbp'))
    pricing.apply_pricing(proposal, pricing_mode=profile_svc.load().get('pricing_mode', 'balanced'))
    existing['price_proposal'] = {
        'price_gbp': proposal.get('price_gbp'), 'evidence': proposal.get('price_evidence'),
        'adjustments': proposal.get('price_adjustments'),
        'range': proposal.get('price_range'),
        'previous_price_gbp': existing.get('price_gbp'),
        'suggested_at': datetime.now().isoformat(timespec='seconds'),
    }
    existing['sales_history'] = proposal.get('sales_history')
    listing_state.write(listing_path, existing)
    existing['folder'] = safe_folder
    return jsonify(existing), 200


@app.post("/reanalyze/<folder>")
def reanalyze_listing(folder):
    """Read the saved photos afresh and replace the listing. The AI run happens on a temporary
    copy first, so a failed or interrupted run never changes the original."""
    from app.services import photo_reanalysis, review_evidence
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify(error='Invalid analysis request.'), 400
    try:
        source, target, target_folder, baseline, paths = photo_reanalysis.prepare(ITEMS_DIR, folder, body.get('request_id'))
        with listing_state.locked(ITEMS_DIR, target_folder):
            # Same request again (double tap, retry): already applied, never pay twice.
            current = json.loads((source/'listing.json').read_text())
            if current.get('reanalysis_request') == target_folder:
                return jsonify(dict(current, folder=folder)), 200
            if target.exists():
                return jsonify(error='This analysis is already running or did not finish. Try again; your listing is unchanged.'), 409
            photo_reanalysis.copy_photos(source, target, folder, paths)
            try:
                started = time.perf_counter()
                listing, eu, wu, el, wl = pipeline_svc.run_pipeline(
                    target, {}, buy_price_gbp=baseline.get('buy_price_gbp'),
                    pricing_mode=profile_svc.load().get('pricing_mode', 'balanced'))
            except Exception:
                shutil.rmtree(target, ignore_errors=True)
                raise
            listing['reanalysis_request'] = target_folder
            listing['reanalysis_baseline'] = photo_reanalysis.baseline_fields(baseline)
            listing['cost_gbp'] = (listing.get('run_stats') or {}).get('total_cost_gbp') \
                or round((_calc_cost_usd(eu)+_calc_cost_usd(wu))*_USD_TO_GBP, 5)
            listing['model_calls'] = eu.get('calls', [])+wu.get('calls', [])
            listing['cost_complete'] = eu.get('cost_complete', True) and wu.get('cost_complete', True)
            listing['cost_status'] = 'estimated' if listing['cost_complete'] else 'incomplete'
            listing['cost_tokens'] = {'input':eu['input_tokens']+wu['input_tokens'], 'output':eu['output_tokens']+wu['output_tokens']}
            latency = round((time.perf_counter()-started)*1000)
            review_evidence.capture(target, listing, extract_log=el, write_log=wl, pipeline_latency_ms=latency)
            # The request already holds the original's lock (serialize_item_requests).
            photo_reanalysis.promote(source, target, listing, json.loads((source/'listing.json').read_text()))
            _log_cost(folder, eu, wu, listing)
            _write_run_log(folder, el, wl, eu, wu, listing, latency)
            _sync_item_status(folder, listing)
            return jsonify(dict(listing, folder=folder)), 200
    except FileNotFoundError:
        return jsonify(error='Saved listing or photos not found. Your listing is unchanged.'), 404
    except ValueError as error:
        return jsonify(error=str(error)), 422
    except Exception:
        return jsonify(error='Photo analysis failed. Your listing is unchanged.'), 500


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

    body = request.get_json(silent=True)
    try:
        if not isinstance(body, dict):
            raise ValueError('Enter listing updates.')
        updates = listing_edits.validate_updates(body.get('updates', {}))
        existing = json.loads(listing_path.read_text())
        # Migrate older manual edits by comparing saved facts with first-run evidence.
        analysis_path = item_path / 'analysis.json'
        if analysis_path.exists():
            original = json.loads(analysis_path.read_text()).get('listing', {})
            manual = set(existing.get('manual_fields') or [])
            manual.update(key for key in listing_edits.FIELDS if key in original and existing.get(key) != original.get(key))
            existing['manual_fields'] = sorted(manual)
        candidate = listing_edits.apply(existing, updates)
        if body.get('regenerate_copy') is True:
            candidate['manual_fields'] = [key for key in candidate.get('manual_fields', []) if key not in {'title', 'description'}]
        from app.validate_listing import validate_or_raise
        validate_or_raise(candidate)
        from app.services import review_evidence, model_usage
        with model_usage.run(item_path):
            new_listing, usage = listing_writer.write(candidate, hints=pipeline_svc.build_hints_from_listing(candidate, updates) or None)
        pipeline_svc.preserve_user_fields(candidate, new_listing, updates)
        from app.services import pricing
        chosen_price = candidate.get('price_gbp')
        new_listing['folder'] = safe_folder
        pricing.apply_pricing(new_listing, pricing_mode=profile_svc.load().get('pricing_mode', 'balanced'))
        new_listing['price_proposal'] = {
            'price_gbp': new_listing.get('price_gbp'), 'evidence': new_listing.get('price_evidence'),
            'adjustments': new_listing.get('price_adjustments'),
            'suggested_at': datetime.now().isoformat(timespec='seconds'),
        }
        calls = candidate.get('model_calls', []) + usage.get('calls', [])
        new_listing['model_calls'] = calls
        new_listing['cost_gbp'] = round((candidate.get('cost_gbp') or 0) + _calc_cost_usd(usage) * _USD_TO_GBP, 5)
        new_listing['cost_complete'] = candidate.get('cost_complete', True) and usage.get('cost_complete', True)
        new_listing['cost_status'] = 'estimated' if new_listing['cost_complete'] else 'incomplete'
        previous_tokens = candidate.get('cost_tokens') or {}
        new_listing['cost_tokens'] = {'input': previous_tokens.get('input', 0) + usage.get('input_tokens', 0),
                                     'output': previous_tokens.get('output', 0) + usage.get('output_tokens', 0)}
        new_listing['price_gbp'] = chosen_price
        new_listing['price_evidence'] = candidate.get('price_evidence', {})
        pricing.refresh_profitability(new_listing)
        from app.validate_listing import normalize_generated_listing, validate_or_raise
        normalize_generated_listing(new_listing)
        validate_or_raise(new_listing)
        review_evidence.capture(item_path, existing)
        new_listing['folder'] = safe_folder
        listing_state.write(listing_path, new_listing)
        _sync_item_status(safe_folder, new_listing)
    except ValueError as error:
        return jsonify(error=str(error)), 422
    except Exception:
        return jsonify(error='Could not regenerate this listing; your saved edits are unchanged.'), 500
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
    from app.services import removed_items
    removed_items.add(safe_folder)   # phones and cloud copies must not bring it back
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
    try:
        from app.services import sales_history
        listing["outcome"] = sales_history.get(safe_folder)   # "Live on Vinted" state
    except Exception:
        listing["outcome"] = None
    listing["folder"] = safe_folder
    if not listing.get("price_range"):
        from app.services.pricing import price_range
        listing["price_range"] = price_range(listing)  # display only; not saved

    # Collect photo filenames: front first, then the order photos are taken in.
    extensions = {".jpg", ".jpeg", ".png", ".webp"}
    role_order = ["front", "back", "brand", "model_size", "material"]
    photos = sorted(
        (f.name for f in item_path.iterdir() if f.is_file() and f.suffix.lower() in extensions),
        key=lambda name: (role_order.index(name.rsplit(".", 1)[0]) if name.rsplit(".", 1)[0] in role_order
                          else len(role_order), name),
    )

    profile = profile_svc.load()
    return render_template(
        "review.html",
        listing=listing,
        photos=photos,
        folder=safe_folder,
        item_revision=listing_state.revision(item_path),
        error_categories=run_logger.ERROR_CATEGORIES,
        draft_count=_draft_count(),
        active_tab="drafts",
        show_guidance=profile_svc.show_guidance(profile),
        is_reseller=profile_svc.is_reseller(profile),
        category_groups=_category_groups(listing.get("category")),
    )


def _category_groups(current: str | None) -> dict[str, list[str]]:
    """Vinted categories the draft filler knows, grouped by Men / Women / ..."""
    from app.services.category_validator import CATEGORY_NAV
    groups: dict[str, list[str]] = {}
    for key in CATEGORY_NAV:
        groups.setdefault(key.split(" > ")[0], []).append(key)
    if current and current not in CATEGORY_NAV:
        groups.setdefault(current.split(" > ")[0], []).insert(0, current)
    return groups


@app.get("/settings")
def settings_page():
    profile = profile_svc.load()
    return render_template("settings.html", profile=profile, active_tab="settings",
                           daily_goal=profile_svc.daily_goal(profile))


@app.post("/api/profile/identity")
def update_identity():
    """Change name, email or the tips opt-in (validated like onboarding)."""
    try:
        profile = profile_svc.update_identity(request.get_json(silent=True))
    except ValueError as error:
        return jsonify(error=str(error)), 422
    return jsonify(name=profile["name"], email=profile["email"], marketing_opt_in=profile["marketing_opt_in"])


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
        listing_state.write(listing_path, listing)
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


@app.post("/listing/<folder>/mark-ready")
def mark_ready(folder):
    """POST /listing/<folder>/mark-ready — operator approves an item for drafting.
    Moves status from needs_review to ready."""
    safe_folder = Path(folder).name
    listing_path = ITEMS_DIR / safe_folder / "listing.json"
    if not listing_path.exists():
        return jsonify({"error": "listing not found"}), 404
    item_store.set_status(safe_folder, "ready", review_needed=False)
    return jsonify({"folder": safe_folder, "status": "ready"}), 200


@app.post("/api/listing/<folder>/fetch-ebay-comps")
def fetch_ebay_comps(folder):
    """POST /api/listing/<folder>/fetch-ebay-comps
    Fetch eBay market comp guidance on demand and persist a compact summary
    into listing.json. Does not modify price_gbp."""
    from app.services import ebay_comps
    safe_folder = Path(folder).name
    listing_path = ITEMS_DIR / safe_folder / "listing.json"
    if not listing_path.exists():
        return jsonify({"error": "listing not found"}), 404
    try:
        listing = json.loads(listing_path.read_text())
        ebay_comps.enrich(listing)
        listing_state.write(listing_path, listing)
        # Return just the comp summary fields so the UI can update without reload
        summary = {k: listing[k] for k in (
            "ebay_suggested_range", "ebay_vinted_range",
            "ebay_comps_count", "ebay_comps_titles",
            "ebay_comps_query", "ebay_comps_note",
            "ebay_comps_fetched_at", "ebay_comps_skipped", "ebay_market", "ebay_links", "ebay_comps_cache_hit",
        ) if k in listing}
        return jsonify(summary), 200
    except Exception:
        return jsonify({"error": traceback.format_exc()}), 500


@app.get("/api/private/backup")
def export_private_backup():
    if not app.config.get("HOSTED_TEST"):
        return jsonify(error="Private hosted backup only"), 503
    from app.services import item_backup
    selected = request.args.get("folder")
    if selected and item_backup.FOLDER.fullmatch(selected) and not (ITEMS_DIR / selected / "listing.json").is_file():
        return jsonify(error="Listing not found"), 404
    try:
        spool=item_backup.export_file(ITEMS_DIR, request.args.get("folder"))
    except (ValueError,OSError):
        return jsonify(error="Could not export backup."),422
    from flask import send_file
    return send_file(spool, mimetype="application/zip", as_attachment=True,
                     download_name="Vinted-Listings-Backup.zip")


@app.post("/api/private/restore-backup")
def restore_private_backup():
    if not app.config.get("HOSTED_TEST"):
        return jsonify(error="Private hosted restore only"), 503
    from app.services import item_backup, removed_items
    data = request.get_data()
    if any(removed_items.contains(folder) for folder in item_backup.folders_in(data)):
        return jsonify(error="This listing was removed.", code="REMOVED"), 410
    try:
        folders = item_backup.restore(data, ITEMS_DIR)
        for folder in folders:
            listing=json.loads((ITEMS_DIR/folder/"listing.json").read_text())
            _sync_item_status(folder,listing)
        return jsonify(restored=folders)
    except (ValueError, OSError, __import__('zipfile').BadZipFile):
        return jsonify(error="Invalid backup or item already exists; no seller edits overwritten."), 422


@app.post("/api/listing/<folder>/ebay-research")
def save_ebay_research(folder):
    from app.services.ebay_comps import research_metrics
    path = ITEMS_DIR / Path(folder).name / "listing.json"
    if not path.exists():
        return jsonify(error="Listing not found"), 404
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify(error="Enter a research object."),422
    try:
        metrics = research_metrics(body.get("active_count"), body.get("sold_count"), body.get("period_days"), body.get("mean_sold_gbp"))
    except (ValueError, TypeError):
        return jsonify(error="Enter whole-number active/sold counts and a period from 1 to 90 days."), 422
    listing = json.loads(path.read_text())
    from app.services.ebay_comps import search_links
    metrics["query"] = search_links(listing)["query"]
    listing["ebay_research"] = metrics
    listing_state.write(path, listing)
    return jsonify(metrics)


@app.post("/api/listing/<folder>/sold-comparisons")
def save_sold_comparisons(folder):
    path = ITEMS_DIR / Path(folder).name / 'listing.json'
    if not path.exists():
        return jsonify(error='Listing not found'), 404
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(error='Enter sold comparison titles and prices.'), 422
    listing = json.loads(path.read_text())
    from app.services.ebay_comps import sold_comparison_summary
    try:
        summary = sold_comparison_summary(listing, body.get('text'))
    except ValueError as error:
        return jsonify(error=str(error)), 422
    listing['ebay_sold_comparisons'] = summary
    listing_state.write(path, listing)
    return jsonify(summary)


@app.get("/tracker/status/<folder>")
def tracker_status(folder):
    """GET /tracker/status/<folder> — draft snapshot + latest performance metrics."""
    safe_folder = Path(folder).name
    data = listing_tracker.get_tracker_status(safe_folder)
    if data is None:
        return jsonify({"tracked": False}), 200
    data["tracked"] = True
    return jsonify(data), 200


@app.post("/tracker/refresh/<folder>")
def tracker_refresh(folder):
    """POST /tracker/refresh/<folder> — scrape Vinted for latest views/favourites/status."""
    safe_folder = Path(folder).name

    # Get listing_id from tracker DB or from listing.json
    status = listing_tracker.get_tracker_status(safe_folder)
    listing_id = (status or {}).get("listing_id")

    if not listing_id:
        # Try extracting from listing.json as fallback
        listing_path = ITEMS_DIR / safe_folder / "listing.json"
        if listing_path.exists():
            try:
                listing = json.loads(listing_path.read_text())
                draft_url = listing.get("draft_url") or ""
                m = __import__("re").search(r"/items/(\d+)", draft_url)
                if m:
                    listing_id = m.group(1)
            except Exception:
                pass

    result = listing_tracker.refresh_tracker(safe_folder, listing_id)
    return jsonify(result), 200


@app.get("/api/listings/review-queue")
def api_review_queue():
    """GET /api/listings/review-queue — folders with review_needed = 1, most recent first."""
    return jsonify(item_store.get_items_needing_review())


@app.get("/api/model-calls")
def api_model_calls():
    from app.services import model_usage
    return jsonify(list(reversed(model_usage.read_events()))[:200])


@app.get("/api/run-logs/summary")
def api_run_logs_summary():
    """GET /api/run-logs/summary — aggregate stats over all run logs."""
    return jsonify(run_logger.summarize_logs())


@app.get("/api/run-logs")
def api_run_logs():
    """GET /api/run-logs — all run log entries (most recent first, max 200)."""
    logs = run_logger.read_run_logs()
    return jsonify(list(reversed(logs))[:200])


@app.get("/api/profile")
def get_profile():
    """GET /api/profile — return current user profile."""
    return jsonify(profile_svc.load())


@app.patch("/api/profile")
def update_profile():
    """PATCH /api/profile — update one or more profile fields.
    Only recognised keys (from DEFAULTS) are accepted; unknown keys are ignored."""
    updates = request.json or {}
    profile = profile_svc.load()
    # Identity fields change only through validated onboarding.
    for key, value in updates.items():
        if key not in profile_svc.DEFAULTS or key in {"name", "email", "onboarded_at", "marketing_opt_in"}:
            continue
        if key in profile_svc.CHOICES and value not in profile_svc.CHOICES[key]:
            return jsonify(error=f"Choose an option for {key.replace('_', ' ')}."), 422
        profile[key] = value
    profile_svc.save(profile)
    return jsonify(profile)


@app.get("/api/vinted-fill/<folder>")
def vinted_fill_payload(folder):
    """Phone app: everything needed to fill Vinted's sell form for this listing (photos inline)."""
    from app.services import vinted_payload
    path = ITEMS_DIR / Path(folder).name
    if not (path / "listing.json").is_file():
        return jsonify(error="Listing not found"), 404
    return jsonify(vinted_payload.build(json.loads((path / "listing.json").read_text()), path))


@app.post("/api/vinted-fill-report")
def vinted_fill_report():
    """Phone app: what the form filler found and filled. Kept for debugging; a saved draft's
    Vinted link is stored on the listing so it shows as "In Vinted drafts"."""
    from urllib.parse import urlsplit
    report = request.get_json(silent=True)
    if not isinstance(report, dict):
        return jsonify(error="Report missing"), 400
    keep = {k: report.get(k) for k in ("folder", "url", "ua", "found", "steps", "filled", "total", "saved",
                                       "draft_url", "error", "errors")}
    keep["at"] = datetime.now().isoformat(timespec="seconds")
    line = json.dumps(keep, default=str)[:20000]
    path = ROOT / "data" / "vinted_fill_reports.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as out:
        out.write(line + "\n")
    app.logger.warning("Vinted fill report: %s", line[:1500])
    folder, draft_url = str(keep.get("folder") or ""), keep.get("draft_url")
    host = urlsplit(draft_url).netloc if isinstance(draft_url, str) else ""
    if keep.get("saved") and (host == "vinted.co.uk" or host.endswith(".vinted.co.uk")) \
            and (ITEMS_DIR / Path(folder).name / "listing.json").is_file():
        with listing_state.locked(ITEMS_DIR, Path(folder).name):
            listing_path = ITEMS_DIR / Path(folder).name / "listing.json"
            listing = json.loads(listing_path.read_text())
            listing["draft_url"] = draft_url
            listing.pop("draft_error", None)
            listing_state.write(listing_path, listing)
    return jsonify(ok=True)


@app.get("/privacy")
def privacy_page():
    return render_template("privacy.html")


@app.get("/favicon.ico")
def favicon():
    return redirect(url_for("static", filename="brand-mark.svg"))


@app.post("/api/account/delete-data")
def delete_my_data():
    """Settings → Delete my data. Needs the word DELETE typed, so it can't happen by accident."""
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict) or str(body.get("confirm", "")).strip().upper() != "DELETE":
        return jsonify(error='Type DELETE to confirm.'), 422
    from app.services import account_data
    current_cloud = app.extensions.get("current_cloud")
    result = account_data.wipe(ITEMS_DIR, current_cloud() if current_cloud else app.extensions.get("cloud_store"))
    return jsonify(deleted=True, **result)


@app.get("/health")
def health():
    return jsonify({"status": "ok"})
