"""Monthly limits that protect the owner's AI bill (hosted app).

- Whole-app budget: AI spend this month across the owner and every seller, in £ (estimated from the
  per-call ledger, the same numbers as Stats). New listings pause once it's reached.
- Free listings per seller per month: distinct items that used AI this month (re-runs of the same item
  don't count twice). The owner has no listing limit, only the budget.
The owner sets both in Settings (accounts.set_limits).
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.services import accounts, model_usage


def _this_month(event, month: str) -> bool:
    return str(event.get("timestamp", ""))[:7] == month


def _month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def usage(month: str | None = None) -> dict:
    """The active account's AI use this month: {"spend_gbp", "items"}."""
    month = month or _month()
    spend, items = 0.0, set()
    for event in model_usage.read_events():
        if not _this_month(event, month):
            continue
        cost = model_usage.cost_usd(event)
        if cost:
            spend += cost * model_usage.USD_TO_GBP
        if event.get("item"):
            items.add(event["item"])
    return {"spend_gbp": round(spend, 2), "items": len(items), "folders": items}


def everyone(month: str | None = None) -> dict:
    """Owner + each seller this month, and the total."""
    month = month or _month()
    with accounts.scope(None):
        owner = usage(month)
    owner.pop("folders")
    sellers = []
    for seller in accounts.sellers():
        with accounts.scope(seller["id"]):
            used = usage(month)
            used.pop("folders")
            sellers.append({**seller, **used})
    total = round(owner["spend_gbp"] + sum(s["spend_gbp"] for s in sellers), 2)
    return {"owner": owner, "sellers": sellers, "total_gbp": total}


def blocked(account_id: str | None, folder: str | None = None) -> str | None:
    """A message for the person if they can't start a new AI listing right now, else None.
    Re-running an item already counted this month never uses up another free listing."""
    limits = accounts.limits()
    if everyone()["total_gbp"] >= limits["monthly_cap_gbp"]:
        return ("This month's AI budget has been reached, so new listings are paused until next month."
                if account_id else "You've reached this month's AI budget. Raise it in Settings to keep listing.")
    if account_id:
        with accounts.scope(account_id):
            used = usage()
        if used["items"] >= limits["seller_items"] and folder not in used["folders"]:
            return f"You've used your {limits['seller_items']} free listings this month. More next month."
    return None
