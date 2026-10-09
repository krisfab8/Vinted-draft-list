"""Daily quests, the daily chest, badges, perks and coin skins — all worked out from listings and sales.

Deterministic like XP: nothing is stored except how many perks have been spent (profile "perks_used"),
so it survives restarts and restores and can't drift from the real items.

Perks are short tastes of the paid tier. "price_check" runs the sold-price web search (eBay/Vinted sold
listings, normally off because it costs ~4p an item) on the seller's next listing.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

STALE_DAYS = 30            # unsold this long (since listing or the last price change) = worth a price drop
DROP_XP, DROP_CAP = 5, 10  # per price drop, counted up to 10 a day
TAKEDOWN_XP = 10           # taking a sold item down elsewhere
CROSSLIST_XP = 5           # marking an item listed on another site
CHEST_XP = 25
CHEST_PERKS = {"price_check": 1}
LEVEL_UP_PERKS = {"price_check": 3}

PERKS = {"price_check": 1}
LEVEL_UP_PERKS = {"price_check": 3}

PERKS = {
    "price_check": ("Pro price check", "A sold-price search on eBay and Vinted for your next listing"),
}

BADGES = [
    # id, name, icon, description, test(stats)
    ("first_listing", "First listing", "🌱", "List your first item", lambda s: s["listed"] >= 1),
    ("ten_listed", "On a roll", "📦", "List 10 items", lambda s: s["listed"] >= 10),
    ("fifty_listed", "Stockroom", "🏬", "List 50 items", lambda s: s["listed"] >= 50),
    ("first_sale", "First sale", "💷", "Sell your first item", lambda s: s["sold"] >= 1),
    ("ten_sales", "Shopkeeper", "🛍️", "Sell 10 items", lambda s: s["sold"] >= 10),
    ("profit_100", "£100 profit", "💰", "Make £100 profit", lambda s: s["profit"] >= 100),
    ("streak_7", "Week on fire", "🔥", "Reach a 7-day streak", lambda s: s["best_streak"] >= 7),
    ("streak_30", "Unstoppable", "☄️", "Reach a 30-day streak", lambda s: s["best_streak"] >= 30),
    ("premium_hunter", "Premium hunter", "★", "List 10 premium pieces", lambda s: s["premium"] >= 10),
    ("photo_pro", "Photo pro", "📷", "Take 10 full photo sets", lambda s: s["full_sets"] >= 10),
    ("crosslister", "Cross-lister", "🔁", "List 5 items on 2+ sites", lambda s: s["crosslisted"] >= 5),
    ("quest_master", "Quest master", "🗝️", "Open 7 daily chests", lambda s: s["chests"] >= 7),
]

# Coin skins: just for fun. Unlocked by level index (0 Rookie … 3 Top Seller) or by a badge.
SKINS = [
    ("brass", "Brass", {"level": 0}),
    ("silver", "Silver", {"level": 1}),
    ("rose", "Rose gold", {"level": 2}),
    ("emerald", "Emerald", {"level": 3}),
    ("gold", "Quest gold", {"badge": "quest_master"}),
]


def day_xp(d: dict, goal: int) -> tuple[int, bool]:
    """XP from upkeep actions on one day, and whether that day's chest was earned:
    hit the listing goal and did at least one real upkeep job (price drop, take-down, sale, cross-list)."""
    xp = DROP_XP * min(DROP_CAP, d.get("drops", 0)) + TAKEDOWN_XP * d.get("takedowns", 0) + CROSSLIST_XP * d.get("crosslisted", 0)
    upkeep = d.get("drops", 0) + d.get("takedowns", 0) + d.get("sold", 0) + d.get("crosslisted", 0)
    return xp, d.get("listed", 0) >= max(1, goal) and upkeep > 0


def jobs(today_stats: dict, goal: int, stale: int, unpriced: int, still_live: int) -> list[dict]:
    """Today's jobs: only real work, only what applies. Done jobs stay ticked for the day."""
    listed, out = today_stats.get("listed", 0), []
    out.append({"id": "list", "icon": "🔥", "text": f"List {max(1, goal)} today to keep your streak" if listed < goal else "Daily goal hit",
                "have": min(listed, goal), "target": max(1, goal), "done": listed >= goal, "xp": "+10 each", "href": "/"})
    drops = today_stats.get("drops", 0)
    if stale or drops:
        target = min(3, stale + drops) or 1
        out.append({"id": "stale", "icon": "💤", "text": f"Drop the price on {stale} item{'s' if stale != 1 else ''} unsold {STALE_DAYS}+ days" if stale else "Stale items refreshed",
                    "have": min(drops, target), "target": target, "done": not stale or drops >= target, "xp": f"+{DROP_XP} each",
                    "href": "/drafts?stale=1"})
    takedowns = today_stats.get("takedowns", 0)
    if still_live or takedowns:
        out.append({"id": "takedown", "icon": "⚠️", "text": f"Take down {still_live} sold item{'s' if still_live != 1 else ''} still live elsewhere" if still_live else "Nothing left to take down",
                    "have": takedowns, "target": takedowns + still_live, "done": not still_live, "xp": f"+{TAKEDOWN_XP} each", "href": "/sold"})
    if unpriced:
        out.append({"id": "costs", "icon": "🧾", "text": f"Add what you paid for {unpriced} sale{'s' if unpriced != 1 else ''}",
                    "have": 0, "target": unpriced, "done": False, "xp": "better profit stats", "href": "/sold"})
    return out


def history(day_stats: dict, goal: int, today: date) -> dict:
    """Upkeep XP and chests over every active day (deterministic from timestamps)."""
    total = chests = 0
    for day, d in day_stats.items():
        if day > today:
            continue
        xp, chest = day_xp(d, goal)
        total += xp + (CHEST_XP if chest else 0)
        chests += chest
    xp_today, chest_today = day_xp(day_stats.get(today, {}), goal)
    return {"upkeep_xp": total, "chests": chests, "chest_ready": chest_today,
            "xp_today": xp_today + (CHEST_XP if chest_today else 0)}


def badges(stats: dict) -> list[dict]:
    return [{"id": bid, "name": name, "icon": icon, "desc": desc, "unlocked": bool(test(stats))}
            for bid, name, icon, desc, test in BADGES]


def perks(chests: int, level_index: int, used: dict | None) -> list[dict]:
    used = used or {}
    out = []
    for pid, (name, desc) in PERKS.items():
        earned = chests * CHEST_PERKS.get(pid, 0) + level_index * LEVEL_UP_PERKS.get(pid, 0)
        out.append({"id": pid, "name": name, "desc": desc, "earned": earned,
                    "left": max(0, earned - int(used.get(pid, 0) or 0))})
    return out


def skins(level_index: int, unlocked_badges: set[str]) -> list[dict]:
    out = []
    for sid, name, rule in SKINS:
        ok = level_index >= rule.get("level", 99) or rule.get("badge") in unlocked_badges
        hint = f"Reach {['Rookie', 'Trader', 'Pro Seller', 'Top Seller'][rule['level']]}" if "level" in rule else "Quest master badge"
        out.append({"id": sid, "name": name, "unlocked": ok, "hint": hint})
    return out
