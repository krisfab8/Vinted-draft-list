"""
eBay market comp guidance service.

Pure-ish service: stateless except for a module-level OAuth token cache.
Network I/O only when credentials are present and the feature is enabled.

Public API
----------
enrich(listing: dict) -> dict
    Adds eBay comp summary fields to the listing dict in-place.
    Never raises. Returns the listing unchanged on any failure.

Fields written to listing
--------------------------
ebay_suggested_range    dict  {"low": int, "mid": int, "high": int, "currency": "GBP"}
ebay_vinted_range       dict  {"low": int, "high": int}   — after discount
ebay_comps_count        int   results after outlier removal
ebay_comps_titles       list  up to 5 representative titles (for operator context)
ebay_comps_query        str   search query used
ebay_comps_note         str   human-readable footnote
ebay_comps_fetched_at   str   ISO-8601 UTC timestamp
ebay_comps_skipped      str   populated on skip/failure; absent on success
"""
from __future__ import annotations

import logging
import math
import time
from datetime import datetime, timezone
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ── Config (read lazily so tests can monkeypatch config before first call) ────

def _cfg():
    from app import config as _c
    return _c


# ── OAuth token cache ─────────────────────────────────────────────────────────

_TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
_SCOPE = "https://api.ebay.com/oauth/api_scope"

_token_cache: dict[str, Any] = {}   # {"token": str, "expires_at": float}
_TOKEN_REFRESH_BUFFER = 60          # refresh if ≤60 s before expiry


def _get_token() -> str:
    """Return a valid OAuth access token, refreshing if needed."""
    import base64

    cfg = _cfg()
    app_id = cfg.EBAY_APP_ID
    cert_id = cfg.EBAY_CERT_ID
    if not app_id or not cert_id:
        raise EbayConfigError("EBAY_APP_ID / EBAY_CERT_ID not set")

    now = time.time()
    if _token_cache.get("token") and now < _token_cache.get("expires_at", 0) - _TOKEN_REFRESH_BUFFER:
        return _token_cache["token"]

    creds = base64.b64encode(f"{app_id}:{cert_id}".encode()).decode()
    resp = requests.post(
        _TOKEN_URL,
        headers={
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={"grant_type": "client_credentials", "scope": _SCOPE},
        timeout=10,
    )
    if resp.status_code != 200:
        raise EbayAuthError(f"eBay token fetch failed: HTTP {resp.status_code}")

    body = resp.json()
    token = body.get("access_token") or ""
    expires_in = int(body.get("expires_in", 7200))
    _token_cache["token"] = token
    _token_cache["expires_at"] = now + expires_in
    return token


# ── Search ────────────────────────────────────────────────────────────────────

_BROWSE_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
_MARKETPLACE_HEADER = "EBAY_GB"
_MAX_RESULTS = 50    # request from API; we filter down further


def _build_query(listing: dict) -> str:
    """Build a deterministic eBay search query from listing fields."""
    parts = []

    brand = (listing.get("brand") or "").strip()
    if brand:
        parts.append(brand)

    item_type = (listing.get("item_type") or "").strip()
    if item_type:
        parts.append(item_type)

    if not parts:
        raise EbayQueryError("Cannot build query: missing brand and item_type")

    # Append primary material only when brand confidence is high and item has one
    brand_conf = (listing.get("brand_confidence") or "").lower()
    materials = listing.get("materials") or []
    if brand_conf == "high" and materials:
        # Take first material, one word only
        first_mat = str(materials[0]).split()[0].lower() if isinstance(materials, list) else ""
        # Only add if it meaningfully qualifies the search (skip "cotton", "other", etc.)
        _USEFUL_MATS = {"wool", "cashmere", "leather", "down", "suede", "linen", "silk", "tweed"}
        if first_mat in _USEFUL_MATS:
            parts.append(first_mat)

    return " ".join(parts)


def _search(query: str, token: str) -> list[dict]:
    """Call eBay Browse API and return normalised GBP item summaries."""
    resp = requests.get(
        _BROWSE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": _MARKETPLACE_HEADER,
            "Content-Type": "application/json",
        },
        params={
            "q": query,
            "filter": "conditions:{USED}",
            "limit": str(_MAX_RESULTS),
        },
        timeout=15,
    )
    if resp.status_code == 429:
        raise EbayRateLimitError("eBay rate limit hit")
    if resp.status_code >= 400:
        raise EbayApiError(f"eBay search failed: HTTP {resp.status_code}")

    raw_items = resp.json().get("itemSummaries") or []
    results = []
    for item in raw_items:
        price_info = item.get("price") or {}
        currency = (price_info.get("currency") or "").upper()
        if currency != "GBP":
            continue
        try:
            price_gbp = float(price_info.get("value", 0))
        except (ValueError, TypeError):
            continue
        if price_gbp <= 0:
            continue
        results.append({
            "title": (item.get("title") or "")[:120],
            "price_gbp": price_gbp,
            "condition": (item.get("condition") or ""),
            "url": (item.get("itemWebUrl") or ""),
        })
    return results


# ── Outlier removal + range ───────────────────────────────────────────────────

_MIN_RESULTS = 3   # need at least this many after outlier removal to derive a range


def _remove_outliers(prices: list[float]) -> list[float]:
    """Remove outliers using IQR method (Tukey fences, k=1.5)."""
    if len(prices) < 4:
        return prices

    sorted_p = sorted(prices)
    n = len(sorted_p)
    q1 = sorted_p[n // 4]
    q3 = sorted_p[(3 * n) // 4]
    iqr = q3 - q1

    if iqr == 0:
        return sorted_p   # all same price — keep all

    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    return [p for p in sorted_p if lower <= p <= upper]


def _compute_range(prices: list[float]) -> dict:
    """Return {low, mid, high} from a cleaned price list."""
    s = sorted(prices)
    n = len(s)
    mid_idx = n // 2
    median = s[mid_idx] if n % 2 == 1 else (s[mid_idx - 1] + s[mid_idx]) / 2
    return {
        "low": int(round(s[0])),
        "mid": int(round(median)),
        "high": int(round(s[-1])),
        "currency": "GBP",
    }


def _apply_discount(ebay_range: dict, discount: float) -> dict:
    """Derive suggested Vinted range by applying active-to-sold discount."""
    return {
        "low": int(round(ebay_range["low"] * discount)),
        "high": int(round(ebay_range["high"] * discount)),
    }


# ── Public entry point ────────────────────────────────────────────────────────

def enrich(listing: dict) -> dict:
    """Fetch eBay comp guidance and write summary fields into listing.

    Mutates listing in-place. Never raises. Returns listing.
    Sets ebay_comps_skipped with a reason string when no comps are available.
    """
    try:
        return _enrich_inner(listing)
    except Exception as exc:
        logger.warning("ebay_comps.enrich failed: %s", exc, exc_info=True)
        listing["ebay_comps_skipped"] = "error"
        return listing


def _enrich_inner(listing: dict) -> dict:
    cfg = _cfg()

    # ── Feature flag ─────────────────────────────────────────────────────────
    if not cfg.ENABLE_EBAY_COMPS:
        return listing

    # ── Credentials check ────────────────────────────────────────────────────
    if not cfg.EBAY_APP_ID or not cfg.EBAY_CERT_ID:
        listing["ebay_comps_skipped"] = "no credentials"
        return listing

    # ── Token ────────────────────────────────────────────────────────────────
    try:
        token = _get_token()
    except (EbayConfigError, EbayAuthError) as e:
        logger.warning("eBay auth failed: %s", e)
        listing["ebay_comps_skipped"] = "auth failed"
        return listing

    # ── Query ────────────────────────────────────────────────────────────────
    try:
        query = _build_query(listing)
    except EbayQueryError as e:
        logger.info("eBay query skipped: %s", e)
        listing["ebay_comps_skipped"] = "no query"
        return listing

    # ── Search ───────────────────────────────────────────────────────────────
    try:
        items = _search(query, token)
    except EbayRateLimitError:
        listing["ebay_comps_skipped"] = "rate limited"
        return listing
    except EbayApiError as e:
        logger.warning("eBay search failed: %s", e)
        listing["ebay_comps_skipped"] = "api error"
        return listing

    if not items:
        listing["ebay_comps_skipped"] = "no results"
        return listing

    # ── Normalise + outlier removal ───────────────────────────────────────────
    prices = [item["price_gbp"] for item in items]
    clean_prices = _remove_outliers(prices)

    if len(clean_prices) < _MIN_RESULTS:
        listing["ebay_comps_skipped"] = "insufficient results"
        return listing

    # ── Compute ranges ────────────────────────────────────────────────────────
    ebay_range = _compute_range(clean_prices)
    discount = float(cfg.EBAY_ACTIVE_TO_SOLD_DISCOUNT)
    vinted_range = _apply_discount(ebay_range, discount)

    # Representative titles (first 5 from clean price set — match closest to median)
    mid = ebay_range["mid"]
    sorted_items = sorted(items, key=lambda x: abs(x["price_gbp"] - mid))
    top_titles = [i["title"] for i in sorted_items[:5]]

    disc_pct = int(round((1 - discount) * 100))

    # ── Write to listing ──────────────────────────────────────────────────────
    listing["ebay_suggested_range"] = ebay_range
    listing["ebay_vinted_range"] = vinted_range
    listing["ebay_comps_count"] = len(clean_prices)
    listing["ebay_comps_titles"] = top_titles
    listing["ebay_comps_query"] = query
    listing["ebay_comps_note"] = (
        f"{len(clean_prices)} active eBay (used) listings; "
        f"Vinted range applies {disc_pct}% discount as sold proxy"
    )
    listing["ebay_comps_fetched_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    listing.pop("ebay_comps_skipped", None)   # clear any prior skip reason

    return listing


# ── Exceptions ────────────────────────────────────────────────────────────────

class EbayConfigError(RuntimeError):
    pass

class EbayAuthError(RuntimeError):
    pass

class EbayQueryError(RuntimeError):
    pass

class EbayApiError(RuntimeError):
    pass

class EbayRateLimitError(EbayApiError):
    pass
