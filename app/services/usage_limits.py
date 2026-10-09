"""Monthly limits that protect the owner's AI bill (hosted app).

- Whole-app budget: AI spend this month across the owner and every seller (removed sellers too, since
  their spend is still on the bill), in £ estimated from the per-call ledger (same numbers as Stats).
  Every AI action pauses once it's reached.
- Free listings per seller per month: new items that used AI successfully this month (failed calls
  don't use one up; re-runs and corrections of an item never count twice). The owner has no listing limit.
The month is the UK calendar month, like every other date in the app. The owner sets both in Settings.
"""
from __future__ import annotations

import os
import threading
from datetime import datetime, timezone

from app.services import accounts, model_usage

_cache: dict = {}            # ledger path -> (size, mtime_ns, month, result): unchanged file = no re-read
_cache_lock = threading.Lock()


def _month() -> str:
    from app.services.progress import uk_day
    return uk_day(datetime.now(timezone.utc).isoformat()).strftime("%Y-%m")


def _event_month(event) -> str:
    from app.services.progress import uk_day
    day = uk_day(str(event.get("timestamp", "")))
    return day.strftime("%Y-%m") if day else ""


def usage(month: str | None = None) -> dict:
    """The active account's AI use this month: {"spend_gbp", "items", "folders"}."""
    month = month or _month()
    path = os.fspath(model_usage.LEDGER_PATH)
    try:
        stat = os.stat(path)
        key = (stat.st_size, stat.st_mtime_ns, month)
    except OSError:
        return {"spend_gbp": 0.0, "items": 0, "folders": set()}
    with _cache_lock:
        hit = _cache.get(path)
        if hit and hit[0] == key:
            return {**hit[1], "folders": set(hit[1]["folders"])}
    spend, items = 0.0, set()
    for event in model_usage.read_events():
        if _event_month(event) != month:
            continue
        cost = model_usage.cost_usd(event)
        if cost:
            spend += cost * model_usage.USD_TO_GBP
        if event.get("item") and not event.get("error_type"):
            items.add(event["item"])
    result = {"spend_gbp": round(spend, 2), "items": len(items), "folders": frozenset(items)}
    with _cache_lock:
        _cache[path] = (key, result)
    return {**result, "folders": set(items)}


def everyone(month: str | None = None) -> dict:
    """Owner + each seller this month (removed sellers count toward the total but aren't listed)."""
    month = month or _month()
    with accounts.scope(None):
        owner = usage(month)
    owner.pop("folders")
    shown = {s["id"]: s for s in accounts.sellers()}
    sellers, total = [], owner["spend_gbp"]
    for account_id in accounts.all_ids():
        with accounts.scope(account_id):
            used = usage(month)
        used.pop("folders")
        total += used["spend_gbp"]
        if account_id in shown:
            sellers.append({**shown[account_id], **used})
    return {"owner": owner, "sellers": sellers, "total_gbp": round(total, 2)}


def blocked(account_id: str | None, folder: str | None = None, new_item: bool = True) -> str | None:
    """A message for the person if they can't run AI right now, else None.
    new_item=False (corrections of an existing listing) is only stopped by the budget; a folder already
    counted this month never uses up another free listing."""
    limits = accounts.limits()
    if everyone()["total_gbp"] >= limits["monthly_cap_gbp"]:
        return ("This month's AI budget has been reached, so new listings are paused until next month."
                if account_id else "You've reached this month's AI budget. Raise it in Settings to keep listing.")
    if account_id and new_item:
        with accounts.scope(account_id):
            used = usage()
        if used["items"] >= limits["seller_items"] and folder not in used["folders"]:
            return f"You've used your {limits['seller_items']} free listings this month. More next month."
    return None
