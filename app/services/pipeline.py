"""
Shared pipeline helpers for listing creation and regeneration.

Functions here are called by web.py routes — they own no state,
make no HTTP calls, and do not interact with the browser.
"""
import re
from pathlib import Path

from app import extractor, listing_writer
from app.services import pricing, model_usage


# ── Core pipeline ────────────────────────────────────────────────────────────

@model_usage.pipeline
def run_pipeline(
    item_path: Path,
    hints: dict,
    buy_price_gbp: float | None = None,
    pricing_mode: str = "balanced",
    price_check: bool = False,
) -> tuple[dict, dict, dict, dict, dict]:
    """Run extract → write → price for a new item.

    Returns:
        (listing, extract_usage, write_usage, extract_log, write_log)

    extract_log and write_log are observability dicts already popped from
    their respective usage/item dicts — callers don't need to pop them.
    """
    import time
    from datetime import datetime, timezone
    from app.config import ENABLE_SINGLE_PASS, VISION_PROVIDER, LISTING_PROVIDER
    run_calls = (model_usage._context.get() or {}).get("calls", [])
    marks = [("Reading photos", time.perf_counter(), len(run_calls))]
    single_pass = ENABLE_SINGLE_PASS and VISION_PROVIDER == LISTING_PROVIDER and VISION_PROVIDER in ("claude-haiku", "openai")
    if single_pass:
        item, extract_usage = extractor.extract(item_path, hints=hints or None, single_pass=True)
    else:
        item, extract_usage = extractor.extract(item_path, hints=hints or None)
    extract_log = item.pop("_extract_log", {})

    if buy_price_gbp is not None:
        item["buy_price_gbp"] = float(buy_price_gbp)

    marks.append(("Writing listing", time.perf_counter(), len(run_calls)))
    if single_pass:
        from app.services.single_pass import assemble
        listing, write_usage = assemble(item, hints or {})
    else:
        listing, write_usage = listing_writer.write(item, hints=hints or None)
    write_log = write_usage.pop("_write_log", {})

    from app.services.ebay_comps import search_links, EbayQueryError
    try:
        listing["ebay_links"] = search_links(listing)
    except EbayQueryError:
        pass
    listing["measurement_proposals"] = item.get("measurement_proposals", [])
    from app.services import web_price
    # Normally off (cost); a "Pro price check" perk turns it on for this one listing.
    perk = price_check and not web_price.enabled() and web_price.available()
    if web_price.enabled() or perk:
        marks.append(("Web price search", time.perf_counter(), len(run_calls)))
        listing["web_price"] = web_price.estimate(listing)
        if perk and listing["web_price"]:
            listing["web_price_perk"] = True
    marks.append(("Pricing", time.perf_counter(), len(run_calls)))
    pricing.apply_pricing(listing, pricing_mode=pricing_mode)
    marks.append(("end", time.perf_counter(), len(run_calls)))
    listing["run_stats"] = _run_stats(marks, run_calls, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    print(stats_line(Path(item_path).name, listing["run_stats"], listing), flush=True)
    _release_memory()
    if extract_log.get("reread_errors"):
        listing.setdefault("warnings", []).append("reread_failed")
    listing["analysis_models"] = {
        "vision": extract_usage.get("model"), "listing": write_usage.get("model"),
    }

    return listing, extract_usage, write_usage, extract_log, write_log


def _release_memory():
    """Hand freed image/OCR buffers back to the OS between analyses.

    Without this, resident memory crept ~40 MB per item until the next label
    read pushed the 512 MB Render instance over its limit.
    """
    import ctypes
    import gc
    gc.collect()
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        pass  # not glibc (e.g. macOS dev machine)


def _run_stats(marks, calls, finished_at):
    """Time, cost and tokens per pipeline stage, from the run's own call ledger."""
    stages = []
    for (name, start, first), (_, end, last) in zip(marks, marks[1:]):
        stage_calls = calls[first:last]
        stages.append({
            "name": name, "ms": round((end - start) * 1000),
            "cost_gbp": round(sum(c.get("cost_gbp") or 0 for c in stage_calls), 5),
            "calls": len(stage_calls),
            "input_tokens": sum(c.get("input_tokens") or 0 for c in stage_calls),
            "output_tokens": sum(c.get("output_tokens") or 0 for c in stage_calls),
            "cached_tokens": sum(c.get("cache_read_input_tokens") or 0 for c in stage_calls),
            "searches": sum(c.get("web_search_requests") or 0 for c in stage_calls),
            "models": sorted({c["model"] for c in stage_calls if c.get("model")}),
        })
    return {"stages": stages, "finished_at": finished_at,
            "total_ms": sum(s["ms"] for s in stages),
            "total_cost_gbp": round(sum(s["cost_gbp"] for s in stages), 5),
            "cost_complete": all(c.get("cost_gbp") is not None for c in calls)}


def stats_line(folder, stats, listing=None):
    """One greppable log line per analysis ("Analysis stats …") for the Render logs."""
    listing = listing or {}
    parts = [f"{stats['total_cost_gbp'] * 100:.2f}p", f"{stats['total_ms'] / 1000:.1f}s"]
    for s in stats["stages"]:
        detail = f"{s['name']} {s['ms'] / 1000:.1f}s"
        if s["calls"]:
            detail += (f" {s['cost_gbp'] * 100:.2f}p ({s['input_tokens']} in/{s['output_tokens']} out,"
                       f" cached {s['cached_tokens']})")
        if s["searches"]:
            detail += f" {s['searches']} searches"
        parts.append(detail)
    models = sorted({m for s in stats["stages"] for m in s["models"]})
    if models:
        parts.append("models " + ",".join(models))
    if listing.get("price_gbp") is not None:
        parts.append(f"price £{listing['price_gbp']}")
    return f"Analysis stats [{folder}]: " + " | ".join(parts)


# ── Hint reconstruction ───────────────────────────────────────────────────────

_WL_PAT = re.compile(r"^W\d+\s*L\d+$", re.IGNORECASE)
_LETTER_PAT = re.compile(r"^(XS|S|M|L|XL|XXL|XXXL)$", re.IGNORECASE)


def build_hints_from_listing(existing: dict, updates: dict | None = None) -> dict:
    """Reconstruct listing_writer hints from an existing listing + optional updates.

    Policy (identical for /reprice and /regen):
    - updates take priority over existing values
    - confirmed brand, gender, made_in, item_type are always forwarded
    - size: explicit update > existing W/L > existing letter size > W+L measurements
    """
    updates = updates or {}
    hints: dict = {}

    brand = updates.get("brand") or existing.get("brand") or ""
    if brand:
        hints["brand"] = brand

    gender = updates.get("gender") or existing.get("gender")
    if gender:
        hints["gender"] = gender

    made_in = updates.get("made_in") or existing.get("made_in")
    if made_in:
        hints["made_in"] = made_in

    item_type = updates.get("item_type") or existing.get("item_type")
    if item_type:
        hints["item_type"] = item_type

    existing_size = str(existing.get("normalized_size") or "")
    if updates.get("normalized_size"):
        hints["size"] = updates["normalized_size"]
    elif _WL_PAT.match(existing_size):
        hints["size"] = existing_size          # confirmed W/L — preserve
    elif _LETTER_PAT.match(existing_size.strip()):
        hints["size"] = existing_size          # letter size — never replace
    else:
        w = updates.get("trouser_waist") or existing.get("trouser_waist")
        l = updates.get("trouser_length") or existing.get("trouser_length")
        if w and l:
            hints["size"] = f"W{w} L{l}"

    return hints


# ── Field preservation ────────────────────────────────────────────────────────

_META_FIELDS = (
    "draft_url", "draft_error", "cost_gbp", "cost_tokens", "measurement_proposals", "measurements",
    "listed_date", "photos_folder", "error_tags", "buy_price_gbp", "brand_confirmed",
    "manual_fields", "analysis_models", "model_calls", "cost_complete", "cost_status",
    "price_history", "initial_asking_price_gbp",
)


def preserve_user_fields(
    existing: dict,
    new_listing: dict,
    updates: dict | None = None,
) -> dict:
    """Apply field-preservation policy after a listing_writer.write() call.

    Preserves:
    - meta fields (draft_url, cost_gbp, etc.) that listing_writer never sets
    - condition_summary if not explicitly included in updates
    - style if existing had it and the new write omitted it
    - category + category_locked if the category was locked by the user

    Mutates and returns new_listing.
    """
    updates = updates or {}

    for field in _META_FIELDS:
        if field in existing:
            new_listing.setdefault(field, existing[field])
    for field in ('buy_price_gbp', 'brand_confirmed', 'manual_fields', 'price_history', 'initial_asking_price_gbp'):
        if field in existing:
            new_listing[field] = existing[field]

    if existing.get("condition_summary") and not updates.get("condition_summary"):
        new_listing["condition_summary"] = existing["condition_summary"]

    # flaws_note: preserve the operator's value (including explicit null) unless
    # the current update explicitly changes it.
    if "flaws_note" in existing and "flaws_note" not in updates:
        new_listing["flaws_note"] = existing["flaws_note"]

    if existing.get("style") and not new_listing.get("style"):
        new_listing["style"] = existing["style"]

    if existing.get("category_locked") and existing.get("category"):
        new_listing["category"] = existing["category"]
        new_listing["category_locked"] = True

    from app.services import measurements
    new_listing["measurements"] = measurements.confirmed(existing.get("measurements", []))
    new_listing["measurement_proposals"] = existing.get("measurement_proposals", [])
    measurements.apply_description(new_listing)

    # Manual facts are authoritative, including explicit blank values. Retain
    # ancillary evidence omitted by the writer rather than losing it on regen.
    for field, value in existing.items():
        if field.startswith('ebay_'):
            new_listing.setdefault(field, value)
    for field in set(existing.get('manual_fields') or []) | set(updates):
        if field in updates:
            new_listing[field] = updates[field]
        elif field in existing:
            new_listing[field] = existing[field]
        else:
            new_listing.pop(field, None)
    from app.services import condition, description_layout
    condition.apply_condition(new_listing)
    if 'description' not in (existing.get('manual_fields') or []):
        description_layout.apply(new_listing)
        measurements.apply_description(new_listing)

    if {'tagged_size', 'normalized_size'} & set(updates):
        from app.services.label_safety import sync_edited_size
        sync_edited_size(new_listing)
    return new_listing
