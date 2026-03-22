"""
Listing intelligence tracker.

Tracks the lifecycle of a Vinted draft — from creation snapshot through
live performance metrics (views, favourites, current price, sold state).

Architecture
------------
- listing_drafts   — one row per item; snapshot of data at draft creation time
- listing_snapshots — append-only time-series of scraped performance metrics
- listing_performance — latest-state rollup (upserted on each scrape)

Public API
----------
init_tracker_tables()
    Idempotent; creates the three tables in items.db.

record_draft_snapshot(folder, listing)
    Called once after a successful create-draft. Never raises.

get_tracker_status(folder) -> dict | None
    Returns combined draft + latest performance data, or None if not tracked.

refresh_tracker(folder, listing_id) -> dict
    Scrapes Vinted with Playwright and upserts performance tables.
    Returns {views, favourites, price_gbp, status, scraped_at, ...}.
    Never raises — returns {"scrape_error": reason} on failure.

All DB writes are wrapped in try/except — DB failure must never affect
the main app flow.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Config (read lazily so tests can monkeypatch) ─────────────────────────────

def _cfg():
    from app import config as _c
    return _c


def _connect() -> sqlite3.Connection:
    from app.services.item_store import _DATA_DIR, DB_PATH
    _DATA_DIR.mkdir(exist_ok=True)
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    return con


# ── DDL ───────────────────────────────────────────────────────────────────────

_CREATE_DRAFTS = """
CREATE TABLE IF NOT EXISTS listing_drafts (
    folder              TEXT PRIMARY KEY,
    listing_id          TEXT,
    draft_url           TEXT,
    draft_created_at    TEXT NOT NULL,
    ai_title            TEXT,
    final_title         TEXT,
    ai_description      TEXT,
    final_description   TEXT,
    ai_price_gbp        REAL,
    final_price_gbp     REAL,
    brand               TEXT,
    category            TEXT,
    brand_confidence    TEXT,
    material_confidence TEXT,
    had_warnings        INTEGER DEFAULT 0,
    correction_count    INTEGER DEFAULT 0,
    pricing_flags       TEXT,
    profit_warning      INTEGER DEFAULT 0,
    ebay_suggested_price REAL
);
"""

_CREATE_SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS listing_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    folder          TEXT NOT NULL,
    listing_id      TEXT NOT NULL,
    scraped_at      TEXT NOT NULL,
    views           INTEGER,
    favourites      INTEGER,
    price_gbp       REAL,
    status_scraped  TEXT,
    offers_count    INTEGER,
    sold_price_gbp  REAL,
    sold_price_source TEXT,
    scrape_error    TEXT
);
"""

_CREATE_PERFORMANCE = """
CREATE TABLE IF NOT EXISTS listing_performance (
    folder          TEXT PRIMARY KEY,
    listing_id      TEXT NOT NULL,
    last_scraped_at TEXT,
    views           INTEGER,
    favourites      INTEGER,
    current_price   REAL,
    status          TEXT,
    offers_count    INTEGER,
    sold_price_gbp  REAL,
    sold_price_source TEXT,
    sold_date       TEXT,
    days_live       INTEGER,
    total_scrapes   INTEGER DEFAULT 0
);
"""


def init_tracker_tables() -> None:
    """Create tracker tables in items.db. Idempotent."""
    try:
        with _connect() as con:
            con.execute(_CREATE_DRAFTS)
            con.execute(_CREATE_SNAPSHOTS)
            con.execute(_CREATE_PERFORMANCE)
    except Exception as exc:
        logger.warning("init_tracker_tables failed: %s", exc)


# ── Draft snapshot ─────────────────────────────────────────────────────────────

def record_draft_snapshot(folder: str, listing: dict) -> None:
    """Record a snapshot of listing data at draft creation time.

    Called once after successful create-draft. Never raises.
    """
    try:
        _record_draft_snapshot_inner(folder, listing)
    except Exception as exc:
        logger.warning("record_draft_snapshot failed for %s: %s", folder, exc)


def _record_draft_snapshot_inner(folder: str, listing: dict) -> None:
    draft_url = listing.get("draft_url") or ""
    listing_id = _extract_listing_id(draft_url)

    ebay_mid: float | None = None
    ebay_range = listing.get("ebay_suggested_range") or {}
    if ebay_range.get("mid"):
        try:
            ebay_mid = float(ebay_range["mid"])
        except (ValueError, TypeError):
            pass

    pricing_flags = listing.get("pricing_flags") or []
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    with _connect() as con:
        con.execute(
            """
            INSERT INTO listing_drafts (
                folder, listing_id, draft_url, draft_created_at,
                ai_title, final_title, ai_description, final_description,
                ai_price_gbp, final_price_gbp,
                brand, category, brand_confidence, material_confidence,
                had_warnings, pricing_flags, profit_warning, ebay_suggested_price
            ) VALUES (
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?
            )
            ON CONFLICT(folder) DO UPDATE SET
                listing_id          = excluded.listing_id,
                draft_url           = excluded.draft_url,
                draft_created_at    = excluded.draft_created_at,
                ai_title            = excluded.ai_title,
                final_title         = excluded.final_title,
                ai_price_gbp        = excluded.ai_price_gbp,
                final_price_gbp     = excluded.final_price_gbp,
                brand               = excluded.brand,
                category            = excluded.category,
                brand_confidence    = excluded.brand_confidence,
                material_confidence = excluded.material_confidence,
                had_warnings        = excluded.had_warnings,
                pricing_flags       = excluded.pricing_flags,
                profit_warning      = excluded.profit_warning,
                ebay_suggested_price = excluded.ebay_suggested_price
            """,
            (
                folder, listing_id, draft_url, now,
                listing.get("title"), listing.get("title"),
                listing.get("description"), listing.get("description"),
                listing.get("ai_price_gbp"), listing.get("price_gbp"),
                listing.get("brand"), listing.get("category"),
                listing.get("brand_confidence"), listing.get("material_confidence"),
                int(bool(listing.get("warnings"))),
                json.dumps(pricing_flags) if pricing_flags else None,
                int(bool(listing.get("profit_warning"))),
                ebay_mid,
            ),
        )


def _extract_listing_id(draft_url: str) -> str | None:
    """Extract numeric listing ID from a Vinted URL like /items/123456789-..."""
    if not draft_url:
        return None
    m = re.search(r"/items/(\d+)", draft_url)
    return m.group(1) if m else None


# ── Status query ──────────────────────────────────────────────────────────────

def get_tracker_status(folder: str) -> dict | None:
    """Return combined draft + latest performance data, or None if not tracked."""
    try:
        with _connect() as con:
            draft = con.execute(
                "SELECT * FROM listing_drafts WHERE folder = ?", (folder,)
            ).fetchone()
            if not draft:
                return None

            perf = con.execute(
                "SELECT * FROM listing_performance WHERE folder = ?", (folder,)
            ).fetchone()

            result: dict[str, Any] = {
                "folder": folder,
                "listing_id": draft["listing_id"],
                "draft_url": draft["draft_url"],
                "draft_created_at": draft["draft_created_at"],
                "final_price_gbp": draft["final_price_gbp"],
            }
            if perf:
                result.update({
                    "views": perf["views"],
                    "favourites": perf["favourites"],
                    "current_price": perf["current_price"],
                    "status": perf["status"],
                    "offers_count": perf["offers_count"],
                    "sold_price_gbp": perf["sold_price_gbp"],
                    "sold_date": perf["sold_date"],
                    "days_live": perf["days_live"],
                    "last_scraped_at": perf["last_scraped_at"],
                    "total_scrapes": perf["total_scrapes"],
                })
            return result
    except Exception as exc:
        logger.warning("get_tracker_status failed for %s: %s", folder, exc)
        return None


# ── Vinted scraper ────────────────────────────────────────────────────────────

def refresh_tracker(folder: str, listing_id: str | None = None) -> dict:
    """Scrape Vinted performance metrics and upsert tracker tables.

    Reuses auth_state.json via Playwright. Never raises.
    Returns a dict with scraped fields or {"scrape_error": reason}.
    """
    try:
        return _refresh_inner(folder, listing_id)
    except Exception as exc:
        logger.warning("refresh_tracker failed for %s: %s", folder, exc)
        _append_snapshot(folder, listing_id or "", scrape_error=str(exc)[:200])
        return {"scrape_error": str(exc)[:200]}


def _refresh_inner(folder: str, listing_id: str | None) -> dict:
    cfg = _cfg()

    if not listing_id:
        # Try to get from DB
        status = get_tracker_status(folder)
        if status:
            listing_id = status.get("listing_id")
    if not listing_id:
        return {"scrape_error": "no listing_id — draft not yet created"}

    auth_state = cfg.ROOT / "auth_state.json"
    if not auth_state.exists():
        return {"scrape_error": "no auth_state.json — reconnect via app"}

    return _scrape_with_playwright(folder, listing_id, str(auth_state))


def _scrape_with_playwright(folder: str, listing_id: str, auth_state_path: str) -> dict:
    from playwright.sync_api import sync_playwright

    url = f"https://www.vinted.co.uk/items/{listing_id}"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            storage_state=auth_state_path,
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            data = _parse_item_page(page, listing_id)
        finally:
            browser.close()

    _upsert_performance(folder, listing_id, data)
    _append_snapshot(folder, listing_id, **data)
    return data


def _parse_item_page(page: Any, listing_id: str) -> dict:
    """Extract views, favourites, price, status from Vinted item page."""
    scraped_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # Detect sold / not found
    url = page.url
    status_scraped = "active"
    if "sold" in url.lower() or page.locator("text=Sold").first.is_visible():
        status_scraped = "sold"
    elif "/login" in url or "/signup" in url:
        return {"scrape_error": "session expired — reconnect", "scraped_at": scraped_at}

    # Price — JSON-LD is most reliable
    price_gbp: float | None = None
    try:
        json_ld_text = page.locator('script[type="application/ld+json"]').first.inner_text(timeout=3000)
        json_ld = json.loads(json_ld_text)
        offers = json_ld.get("offers") or {}
        raw_price = offers.get("price") or offers.get("lowPrice")
        if raw_price is not None:
            price_gbp = float(raw_price)
    except Exception:
        pass

    # Views — Vinted shows "X views" text somewhere on page
    views: int | None = None
    try:
        views_text = page.locator("text=/\\d+ views?/i").first.inner_text(timeout=2000)
        m = re.search(r"(\d+)", views_text)
        if m:
            views = int(m.group(1))
    except Exception:
        pass

    # Favourites — heart count
    favourites: int | None = None
    try:
        fav_text = page.locator("[data-testid='item-favourites-count']").first.inner_text(timeout=2000)
        m = re.search(r"(\d+)", fav_text)
        if m:
            favourites = int(m.group(1))
    except Exception:
        pass

    return {
        "views": views,
        "favourites": favourites,
        "price_gbp": price_gbp,
        "status_scraped": status_scraped,
        "offers_count": None,
        "sold_price_gbp": price_gbp if status_scraped == "sold" else None,
        "sold_price_source": "scraped" if status_scraped == "sold" else None,
        "scraped_at": scraped_at,
    }


# ── DB writes ─────────────────────────────────────────────────────────────────

def _append_snapshot(
    folder: str,
    listing_id: str,
    *,
    views: int | None = None,
    favourites: int | None = None,
    price_gbp: float | None = None,
    status_scraped: str | None = None,
    offers_count: int | None = None,
    sold_price_gbp: float | None = None,
    sold_price_source: str | None = None,
    scraped_at: str | None = None,
    scrape_error: str | None = None,
) -> None:
    now = scraped_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        with _connect() as con:
            con.execute(
                """
                INSERT INTO listing_snapshots (
                    folder, listing_id, scraped_at,
                    views, favourites, price_gbp, status_scraped,
                    offers_count, sold_price_gbp, sold_price_source, scrape_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    folder, listing_id, now,
                    views, favourites, price_gbp, status_scraped,
                    offers_count, sold_price_gbp, sold_price_source, scrape_error,
                ),
            )
    except Exception as exc:
        logger.warning("_append_snapshot failed: %s", exc)


def _upsert_performance(folder: str, listing_id: str, data: dict) -> None:
    now = data.get("scraped_at") or datetime.now(timezone.utc).isoformat(timespec="seconds")
    sold_date: str | None = None
    if data.get("status_scraped") == "sold":
        sold_date = now[:10]  # date portion only

    try:
        with _connect() as con:
            existing = con.execute(
                "SELECT total_scrapes, draft_created_at FROM listing_performance lp "
                "LEFT JOIN listing_drafts ld ON lp.folder = ld.folder "
                "WHERE lp.folder = ?", (folder,)
            ).fetchone()
            total_scrapes = (existing["total_scrapes"] if existing else 0) + 1

            # days_live from draft creation
            days_live: int | None = None
            try:
                draft = con.execute(
                    "SELECT draft_created_at FROM listing_drafts WHERE folder = ?", (folder,)
                ).fetchone()
                if draft and draft["draft_created_at"]:
                    created = datetime.fromisoformat(draft["draft_created_at"])
                    days_live = (datetime.now(timezone.utc) - created).days
            except Exception:
                pass

            con.execute(
                """
                INSERT INTO listing_performance (
                    folder, listing_id, last_scraped_at,
                    views, favourites, current_price, status,
                    offers_count, sold_price_gbp, sold_price_source,
                    sold_date, days_live, total_scrapes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(folder) DO UPDATE SET
                    listing_id      = excluded.listing_id,
                    last_scraped_at = excluded.last_scraped_at,
                    views           = excluded.views,
                    favourites      = excluded.favourites,
                    current_price   = excluded.current_price,
                    status          = CASE WHEN excluded.status IS NOT NULL THEN excluded.status ELSE listing_performance.status END,
                    offers_count    = excluded.offers_count,
                    sold_price_gbp  = CASE WHEN excluded.sold_price_gbp IS NOT NULL THEN excluded.sold_price_gbp ELSE listing_performance.sold_price_gbp END,
                    sold_price_source = CASE WHEN excluded.sold_price_source IS NOT NULL THEN excluded.sold_price_source ELSE listing_performance.sold_price_source END,
                    sold_date       = CASE WHEN excluded.sold_date IS NOT NULL THEN excluded.sold_date ELSE listing_performance.sold_date END,
                    days_live       = excluded.days_live,
                    total_scrapes   = excluded.total_scrapes
                """,
                (
                    folder, listing_id, now,
                    data.get("views"), data.get("favourites"),
                    data.get("price_gbp"),
                    data.get("status_scraped"),
                    data.get("offers_count"),
                    data.get("sold_price_gbp"), data.get("sold_price_source"),
                    sold_date, days_live, total_scrapes,
                ),
            )
    except Exception as exc:
        logger.warning("_upsert_performance failed: %s", exc)
