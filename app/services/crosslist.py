"""Where an item is listed, and what to take down when it sells somewhere.

Stored in listing.json under "crosslist" so it travels with the item (backups, cloud restore):
    {"Vinted": {"status": "live", "url": "...", "at": "..."}, "eBay": {...}}
status: live | sold (the platform it sold on) | removed (taken down after selling elsewhere).

Platforms with a delister (eBay once connected) are ended automatically; the rest become a
checklist for the seller. Vinted is always a manual tap: no automation on Vinted.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

PLATFORMS = ("Vinted", "eBay", "Depop", "Other")

# platform -> fn(listing, entry) -> True when the listing was ended on that platform.
DELISTERS: dict[str, Callable[[dict, dict], bool]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _check(platform: str) -> str:
    if platform not in PLATFORMS:
        raise ValueError("Unknown platform.")
    return platform


def where_listed(listing: dict) -> dict:
    """Every platform the item is on. A saved Vinted draft counts as listed on Vinted."""
    entries = {k: dict(v) for k, v in (listing.get("crosslist") or {}).items()
               if k in PLATFORMS and isinstance(v, dict)}
    if listing.get("draft_url") and "Vinted" not in entries:
        entries["Vinted"] = {"status": "live", "url": listing["draft_url"]}
    return entries


def set_listed(listing: dict, platform: str, live: bool = True, url: str | None = None) -> dict:
    """Seller says the item is (or isn't) listed on a platform. Returns where_listed()."""
    entries = where_listed(listing)
    platform = _check(platform)
    if live:
        entry = entries.get(platform, {})
        entry.update(status="live", at=_now())
        if url and url.startswith("https://"):
            entry["url"] = url[:500]
        entries[platform] = entry
    else:
        entries.pop(platform, None)
    listing["crosslist"] = entries
    return entries


def mark_removed(listing: dict, platform: str) -> dict:
    entries = where_listed(listing)
    entry = entries.get(_check(platform))
    if entry and entry.get("status") == "live":
        entry.update(status="removed", at=_now())
    listing["crosslist"] = entries
    return entries


def still_live(listing: dict, sold_platform: str | None) -> list[str]:
    """Platforms still showing the item after it sold on sold_platform (oversell risk)."""
    return [p for p, e in where_listed(listing).items() if p != sold_platform and e.get("status") == "live"]


def after_sale(listing: dict, sold_platform: str) -> list[dict]:
    """Mark where it sold and take it down elsewhere. Returns one task per other live platform:
    {"platform", "url", "done", "auto"}; "done" tasks were ended automatically."""
    entries = where_listed(listing)
    if sold_platform in PLATFORMS:
        entry = entries.setdefault(sold_platform, {})
        entry.update(status="sold", at=_now())
    listing["crosslist"] = entries
    tasks = []
    for platform in still_live(listing, sold_platform):
        entry, done = entries[platform], False
        delist = DELISTERS.get(platform)
        if delist:
            try:
                done = bool(delist(listing, entry))
            except Exception:
                done = False      # never block recording the sale; it shows as a manual task instead
            if done:
                entry.update(status="removed", at=_now())
        tasks.append({"platform": platform, "url": entry.get("url"), "done": done, "auto": bool(delist)})
    return tasks


def decorate(listing: dict, outcome: dict | None) -> dict:
    """Add "crosslist" (where it's listed) and "still_live" (oversell risk) for the UI."""
    listing["crosslist"] = where_listed(listing)
    sold_on = outcome.get("platform") if outcome and outcome.get("status") == "sold" else None
    listing["still_live"] = still_live(listing, sold_on) if sold_on else []
    return listing
