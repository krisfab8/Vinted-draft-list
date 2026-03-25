"""
Deterministic post-processing pricing service.

Pure functions only — no I/O, no AI calls, no side effects.

Called after listing_writer.write() to:
1. Preserve the raw AI price as ai_price_gbp
2. Apply deterministic rules to produce the final price_gbp
3. Record each applied rule as a short string in price_adjustments
4. Calculate profitability metrics when buy_price_gbp is known

Rules applied in order:
    a) Price-memory band + condition band position
    b) Flaws discount (-15%) when flaws_note is present
    c) Memory-high ceiling clamp (medium/high confidence only)
    d) Fall through: keep AI price if insufficient evidence
    e) Profitability analysis (informational — never moves price_gbp)
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from app.services import rl_features as _rl_svc

# ── Price-memory loader ───────────────────────────────────────────────────────

_MEMORY_PATH = Path(__file__).parent.parent.parent / "data" / "price_memory.json"
_memory_cache: list[dict] | None = None
_memory_mtime: float = 0.0


def _load_memory() -> list[dict]:
    global _memory_cache, _memory_mtime
    try:
        mtime = _MEMORY_PATH.stat().st_mtime
        if _memory_cache is None or mtime != _memory_mtime:
            _memory_cache = json.loads(_MEMORY_PATH.read_text())["entries"]
            _memory_mtime = mtime
    except Exception:
        _memory_cache = _memory_cache or []
    return _memory_cache or []


# ── Memory lookup ─────────────────────────────────────────────────────────────

def _normalise(s: str | None) -> str:
    return (s or "").strip().lower()


def _material_group(materials: list[str] | str | None) -> str | None:
    """Map extracted material(s) to a memory material_group key."""
    _MAP = {
        "cashmere": "cashmere",
        "wool": "wool",
        "merino": "wool",
        "lambswool": "wool",
        "cotton": "cotton",
        "linen": "linen",
        "silk": "silk",
        "leather": "leather",
        "suede": "leather",
        "down": "down",
        "polyester": "synthetic",
        "nylon": "synthetic",
        "acrylic": "synthetic",
        "viscose": "synthetic",
        "lycra": "synthetic",
    }
    if isinstance(materials, str):
        materials = [materials]
    for m in (materials or []):
        key = _normalise(m)
        for token, group in _MAP.items():
            if token in key:
                return group
    return None


def lookup_memory(
    brand: str | None,
    item_type: str | None,
    materials: list[str] | str | None = None,
) -> dict | None:
    """Return the best-matching price-memory entry or None.

    Match priority (same as existing pipeline Step 4):
      1. brand + item_type + material_group
      2. brand + item_type
      3. item_type + material_group
      4. item_type only
    """
    entries = _load_memory()
    b = _normalise(brand)
    t = _normalise(item_type)
    mg = _material_group(materials)

    def _score(e: dict) -> int:
        eb = _normalise(e.get("brand"))
        et = _normalise(e.get("item_type"))
        emg = _normalise(e.get("material_group")) or None

        if et != t:
            return -1

        brand_match = eb == b if b and eb else (not b and not eb)
        mat_match = emg == mg if mg and emg else (not mg and not emg)

        if brand_match and mat_match:
            return 4
        if brand_match and emg is None:
            return 3
        if not eb and mat_match:
            return 2
        if not eb and not emg:
            return 1
        return -1

    best = max(entries, key=_score, default=None)
    if best and _score(best) >= 1:
        return best
    return None


# ── Condition → band percentile ───────────────────────────────────────────────

def _condition_percentile(condition_summary: str | None) -> float:
    """Map condition summary to a 0–1 position within the price band.

    Conditions follow the pricing_rules.md positioning guidance:
    - Standard / average:     lower 40 % of range  → 0.20 midpoint
    - Good brand or condition: midpoint             → 0.50
    - Very good:               upper 25-30 %        → 0.75
    - Exceptional / pristine:  at/near ceiling      → 0.92
    """
    s = _normalise(condition_summary)
    if not s:
        return 0.50  # no info — use midpoint

    if any(k in s for k in ("pristine", "mint", "new with tags", "deadstock", "bnwt")):
        return 0.92
    if any(k in s for k in ("very good", "excellent", "like new")):
        return 0.75
    if any(k in s for k in ("good",)):
        return 0.50
    if any(k in s for k in ("fair", "acceptable", "average", "standard")):
        return 0.20
    # Default — Vinted standard condition (our condition_summary always starts "Very good")
    return 0.75


# ── Core pricing function ─────────────────────────────────────────────────────

_PRICING_MODE_OFFSET: dict[str, float] = {
    "speed": -0.10,    # bottom of band — sell faster
    "price": +0.10,    # top of band — maximise return
    "balanced": 0.0,   # no adjustment (default)
}


def apply_pricing(listing: dict, pricing_mode: str = "balanced") -> dict:
    """Apply deterministic pricing rules to a listing dict.

    Mutates and returns the listing with:
      - ai_price_gbp: the original model price (preserved)
      - price_gbp:    the final chosen price
      - price_adjustments: list of short reason strings

    pricing_mode: "speed" | "price" | "balanced" — shifts band position ±0.10.
    Never raises — falls back to AI price on any failure.
    """
    try:
        return _apply_pricing_inner(listing, pricing_mode=pricing_mode)
    except Exception:
        # Safety net: if anything goes wrong, leave price_gbp untouched
        listing.setdefault("price_adjustments", [])
        return listing


def _apply_pricing_inner(listing: dict, pricing_mode: str = "balanced") -> dict:
    adjustments: list[str] = []

    # ── 0. Capture AI price ───────────────────────────────────────────────────
    ai_price = listing.get("price_gbp")
    if ai_price is not None:
        try:
            ai_price = float(ai_price)
        except (ValueError, TypeError):
            ai_price = None
    listing["ai_price_gbp"] = ai_price

    final_price = ai_price  # default: keep AI price

    # ── 1. Price-memory band + condition positioning ──────────────────────────
    memory_entry = lookup_memory(
        brand=listing.get("brand"),
        item_type=listing.get("item_type"),
        materials=listing.get("materials") or listing.get("material"),
    )

    if memory_entry:
        low = float(memory_entry.get("low", 0))
        high = float(memory_entry.get("high", 0))
        band_width = high - low

        if band_width > 0:
            pct = _condition_percentile(listing.get("condition_summary"))
            offset = _PRICING_MODE_OFFSET.get(pricing_mode, 0.0)
            if offset:
                pct = max(0.0, min(1.0, pct + offset))
                adjustments.append(f"pricing mode: {pricing_mode} ({'+' if offset > 0 else ''}{int(offset*100)}%)")
            memory_price = round(low + pct * band_width, 0)
            confidence = _normalise(memory_entry.get("confidence"))

            final_price = memory_price
            parts = [p for p in [memory_entry.get("brand"), memory_entry.get("item_type"), memory_entry.get("material_group")] if p]
            adjustments.append(f"memory: {' '.join(parts)} → £{int(low)}–£{int(high)}, {int(pct*100)}th percentile")
        else:
            confidence = "low"
    else:
        confidence = "low"
        if ai_price is not None:
            adjustments.append("no memory match — using AI price")

    # ── 2. Flaws discount (-15%) ──────────────────────────────────────────────
    flaws = (listing.get("flaws_note") or "").strip()
    if flaws and final_price is not None:
        discounted = round(final_price * 0.85, 0)
        adjustments.append(f"flaws −15% (£{int(final_price)} → £{int(discounted)})")
        final_price = discounted

    # ── 2.5. Ralph Lauren feature adjustments ────────────────────────────────
    rl = _rl_svc.detect_rl_features(listing)
    if rl is not None:
        listing["rl_features"] = rl  # always persist for review UI / debugging
        if final_price is not None:
            if rl.get("rl_logo_size") == "big":
                final_price = round(final_price * 1.25, 0)
                adjustments.append("RL big pony +25%")
            if rl.get("rl_embroidery"):
                final_price = round(final_price * 1.15, 0)
                adjustments.append("RL embroidery +15%")
            if rl.get("rl_fabric_type") == "terry":
                final_price = round(final_price * 1.20, 0)
                adjustments.append("RL terry/towelling +20%")
            if rl.get("rl_line") == "lauren":
                final_price = round(final_price * 0.80, 0)
                adjustments.append("Lauren line −20%")

    # ── 3. Memory-high ceiling clamp ─────────────────────────────────────────
    if memory_entry and confidence in ("medium", "high"):
        mem_high = float(memory_entry.get("high", 0))
        if mem_high > 0 and final_price is not None and final_price > mem_high:
            adjustments.append(f"clamped to memory ceiling £{int(mem_high)}")
            final_price = mem_high

    # ── 4. Round to nearest £1 and write back ─────────────────────────────────
    if final_price is not None:
        final_price = round(final_price)
        listing["price_gbp"] = final_price
    # else: leave price_gbp unchanged (AI value or None)

    listing["price_adjustments"] = adjustments

    # ── 5. Profitability analysis (informational — never moves price_gbp) ─────
    _apply_profitability(listing, final_price)

    return listing


# Vinted buyer fee: ~5 % + £0.70 per sale (deducted from seller proceeds)
_VINTED_FEE_PCT = 0.05
_VINTED_FEE_FIXED = 0.70


def _apply_profitability(listing: dict, final_price: float | None) -> None:
    """Add estimated_profit_gbp, profit_multiple, pricing_flags, profit_warning.

    Pure informational — never modifies price_gbp.
    """
    buy_price_raw = listing.get("buy_price_gbp")
    if buy_price_raw is None or final_price is None:
        return

    try:
        buy = float(buy_price_raw)
    except (ValueError, TypeError):
        return

    if buy <= 0:
        return

    # Net proceeds after Vinted fee
    net_proceeds = final_price * (1 - _VINTED_FEE_PCT) - _VINTED_FEE_FIXED
    profit = round(net_proceeds - buy, 2)
    multiple = round(final_price / buy, 2)

    listing["estimated_profit_gbp"] = profit
    listing["profit_multiple"] = multiple

    flags: list[str] = []
    if profit < 0:
        flags.append("loss")
    elif multiple < 1.5:
        flags.append("low_margin")
    elif multiple < 2.0:
        flags.append("thin_margin")

    listing["pricing_flags"] = flags
    listing["profit_warning"] = bool(flags)


# ── Convenience accessor ──────────────────────────────────────────────────────

def price_hint_text(listing: dict) -> str | None:
    """Return a short display string for the review UI, or None if nothing to show.

    Examples:
      "AI: £80 → Final: £95 (memory: barbour wax jacket)"
      "AI price kept (no memory match)"
    """
    ai = listing.get("ai_price_gbp")
    final = listing.get("price_gbp")
    adjustments = listing.get("price_adjustments") or []

    if ai is None and final is None:
        return None

    if ai is not None and final is not None and int(ai) != int(final):
        reason = adjustments[0] if adjustments else ""
        return f"AI: £{int(ai)} → £{int(final)}" + (f" ({reason})" if reason else "")

    if adjustments:
        return adjustments[0]

    return None
