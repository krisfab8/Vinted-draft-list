"""
Shared pipeline helpers for listing creation and regeneration.

Functions here are called by web.py routes — they own no state,
make no HTTP calls, and do not interact with the browser.
"""
import re
from pathlib import Path

from app import extractor, listing_writer
from app.services import pricing


# ── Core pipeline ────────────────────────────────────────────────────────────

def run_pipeline(
    item_path: Path,
    hints: dict,
    buy_price_gbp: float | None = None,
) -> tuple[dict, dict, dict, dict, dict]:
    """Run extract → write → price for a new item.

    Returns:
        (listing, extract_usage, write_usage, extract_log, write_log)

    extract_log and write_log are observability dicts already popped from
    their respective usage/item dicts — callers don't need to pop them.
    """
    item, extract_usage = extractor.extract(item_path, hints=hints or None)
    extract_log = item.pop("_extract_log", {})

    if buy_price_gbp is not None:
        item["buy_price_gbp"] = float(buy_price_gbp)

    listing, write_usage = listing_writer.write(item, hints=hints or None)
    write_log = write_usage.pop("_write_log", {})

    pricing.apply_pricing(listing)

    return listing, extract_usage, write_usage, extract_log, write_log


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
    "draft_url", "draft_error", "cost_gbp", "cost_tokens",
    "listed_date", "photos_folder", "error_tags",
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

    return new_listing
