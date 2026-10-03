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
import re
import json
import hashlib
import statistics
from pathlib import Path
from urllib.parse import urlencode
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
        first_mat = re.sub(r"^\s*\d+(?:\.\d+)?%\s*", "", str(materials[0])).split()[0].lower() if isinstance(materials, list) else ""
        # Only add if it meaningfully qualifies the search (skip "cotton", "other", etc.)
        _USEFUL_MATS = {"wool", "cashmere", "leather", "down", "suede", "linen", "silk", "tweed"}
        if first_mat in _USEFUL_MATS:
            parts.append(first_mat)

    model = listing.get("model_name")
    if model and listing.get("model_confidence") == "high":
        parts.append(str(model).strip())
    size = listing.get("normalized_size") or listing.get("tagged_size")
    if size and not {"size", "normalized_size", "tagged_size"} & set(listing.get("low_confidence_fields") or []):
        parts.append(str(size).strip())
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
            "filter": "conditions:{USED},buyingOptions:{FIXED_PRICE},itemLocationCountry:GB",
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
        if not math.isfinite(price_gbp) or price_gbp <= 0:
            continue
        shipping = item.get("shippingOptions") or []
        postage = None
        if shipping:
            cost = shipping[0].get("shippingCost") or {}
            if cost.get("currency") == "GBP":
                try:
                    value = float(cost["value"])
                    if math.isfinite(value) and value >= 0:
                        postage = value
                except (KeyError, ValueError, TypeError):
                    pass
        results.append({
            "shipping_gbp": postage,
            "title": (item.get("title") or "")[:120],
            "price_gbp": price_gbp,
            "condition": (item.get("condition") or ""),
            "url": (item.get("itemWebUrl") or ""),
        })
    return results


CACHE_TTL = 24 * 3600


def _cache_path():
    from app.config import ROOT
    return ROOT / "data" / "ebay_comps_cache.json"


def _cache_get(key):
    try:
        entry = json.loads(_cache_path().read_text()).get(key)
        if entry and 0 <= time.time() - entry['timestamp'] < CACHE_TTL:
            return entry['fields']
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def _cache_put(key, fields):
    try:
        path = _cache_path()
        data = json.loads(path.read_text()) if path.exists() else {}
        data = {k:v for k,v in data.items() if 0 <= time.time()-v['timestamp'] < CACHE_TTL}
        data[key] = {'timestamp':time.time(), 'fields':fields}
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(data))
        temp.replace(path)
    except (OSError, ValueError, KeyError, TypeError):
        pass


def search_links(listing):
    query = _build_query(listing)
    base = "https://www.ebay.co.uk/sch/i.html?"
    return {"query":query,
            "active":base+urlencode({'_nkw':query,'LH_ItemCondition':'3000','LH_BIN':'1'}),
            "sold":base+urlencode({'_nkw':query,'LH_ItemCondition':'3000','LH_Sold':'1','LH_Complete':'1'}),
            "research":"https://www.ebay.co.uk/sh/research"}


def _relevant(item, listing):
    title = item.get('title','').lower()
    words = set(re.findall(r"[a-z0-9]+", title))
    brand = set(re.findall(r"[a-z0-9]+", str(listing.get('brand') or '').lower()))
    if brand and not brand <= words:
        return False
    kind = set(re.findall(r"[a-z0-9]+", str(listing.get('item_type') or '').lower()))
    if 'cropped' in kind and 'capri' in words:
        words.add('cropped')
    if kind and not kind <= words:
        return False
    if re.search(r'\b(?:repair kit|sewing pattern|spares|joblot|bundle|lot of)\b', title):
        return False
    model = listing.get('model_name') if listing.get('model_confidence') == 'high' else None
    if model and not set(re.findall(r"[a-z0-9]+",str(model).lower())) <= words:
        return False
    size = listing.get('normalized_size') or listing.get('tagged_size')
    if size and not {'size', 'normalized_size', 'tagged_size'} & set(listing.get('low_confidence_fields') or []):
        if not re.search(r'(?<![a-z0-9])'+re.escape(str(size).lower())+r'(?![a-z0-9])',title):
            return False
    return True


def research_metrics(active, sold, days, mean_sold_gbp=None):
    """Counts are seller-supplied research, not a fetched or cohort sell-through rate."""
    for value in (active, sold, days):
        if isinstance(value,bool) or not isinstance(value,int) or value < 0:
            raise ValueError('Use nonnegative whole-number counts and a period in days.')
    if not 1 <= days <= 90:
        raise ValueError('Use a research period from 1 to 90 days.')
    if mean_sold_gbp is not None and (isinstance(mean_sold_gbp,bool) or not isinstance(mean_sold_gbp,(int,float)) or not math.isfinite(mean_sold_gbp) or mean_sold_gbp < 0 or sold == 0):
        raise ValueError('Average sold price needs a finite nonnegative value and at least one sale.')
    return {'active_count':active, 'sold_count':sold, 'period_days':days,
            'mean_sold_gbp':mean_sold_gbp,
            'sales_to_active_percent':round(sold/active*100,2) if active else None,
            'active_to_sold_ratio':round(active/sold,3) if sold else None,
            'sold_share_percent':round(sold/(sold+active)*100,2) if sold+active else None,
            'source':'seller_entered_research',
            'note':'Sales-to-active is a demand proxy and can exceed 100%; these counts are not a verified cohort sell-through rate.',
            'recorded_at':datetime.now(timezone.utc).isoformat()}


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
        listing['ebay_links'] = search_links(listing)
        for field in list(listing):
            if field.startswith('ebay_') and field not in ('ebay_links','ebay_research'):
                listing.pop(field)
        return _enrich_inner(listing)
    except Exception as exc:
        logger.warning("ebay_comps.enrich failed (%s)", type(exc).__name__)
        listing["ebay_comps_skipped"] = "error"
        return listing


def _enrich_inner(listing: dict) -> dict:
    cfg = _cfg()

    # ── Feature flag ─────────────────────────────────────────────────────────
    if not cfg.ENABLE_EBAY_COMPS:
        return listing

    query = _build_query(listing)
    key = hashlib.sha256((query + "|GB|GBP|USED|FIXED_PRICE|v2").encode()).hexdigest()
    cached = _cache_get(key)
    if cached:
        listing.update(cached)
        listing['ebay_comps_cache_hit'] = True
        listing.pop('ebay_comps_skipped',None)
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
    candidates = items
    items = [item for item in items if _relevant(item, listing)]
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
    clean_items = [i for i in sorted_items if i['price_gbp'] in clean_prices]
    top_titles = [i["title"] for i in clean_items[:5]]

    disc_pct = int(round((1 - discount) * 100))

    # ── Write to listing ──────────────────────────────────────────────────────
    listing["ebay_suggested_range"] = ebay_range
    listing["ebay_vinted_range"] = vinted_range
    listing["ebay_comps_count"] = len(clean_prices)
    listing["ebay_comps_titles"] = top_titles
    listing["ebay_comps_query"] = query
    listing["ebay_comps_note"] = (
        f"{len(clean_prices)} matched active asking prices; not sold prices. "
        f"The legacy Vinted adjustment is {disc_pct}%; it is not an observed sale-price estimate."
    )
    listing["ebay_comps_fetched_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    listing['ebay_market'] = {
        'source':'ebay_browse_active', 'currency':'GBP', 'query':query,
        'sample_count':len(clean_prices), 'candidate_count':len(candidates),
        'matched_before_outliers':len(items), 'mean_asking_gbp':round(statistics.mean(clean_prices),2),
        'median_asking_gbp':round(statistics.median(clean_prices),2),
        'sold_mean_gbp':None, 'sell_through_percent':None,
        'postage_known_count':sum(i.get('shipping_gbp') is not None for i in clean_items),
        'mean_delivered_gbp':round(statistics.mean([i['price_gbp']+i['shipping_gbp'] for i in clean_items]),2)
            if clean_items and all(i.get('shipping_gbp') is not None for i in clean_items) else None,
        'examples':clean_items[:5], 'fetched_at':listing['ebay_comps_fetched_at'],
        'note':'Matched sample of active UK fixed-price used listings. Unknown postage stays unknown; not a market-wide average or actual sold price.'}
    listing['ebay_comps_cache_hit'] = False
    fields = {k:v for k,v in listing.items() if k.startswith('ebay_') and k not in ('ebay_research','ebay_comps_skipped')}
    _cache_put(key, fields)
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
