"""Daily quests, the daily chest, badges, perks and coin skins — all worked out from listings and sales.

Deterministic like XP: nothing is stored except how many perks have been spent (profile "perks_used"),
so it survives restarts and restores and can't drift from the real items.

Perks are short tastes of the paid tier. "price_check" runs the sold-price web search (eBay/Vinted sold
listings, normally off because it costs ~4p an item) on the seller's next listing.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

QUEST_POOL = {
    # id: (text, icon, xp)
    "list": ("List {n} items", "📸", 15),
    "full_set": ("Take a full photo set", "🖼️", 10),
    "premium": ("List a ★ premium piece", "★", 20),
    "hot": ("List a 🔥 hot piece (premium, £40+)", "🔥", 35),
    "sale": ("Record a sale", "💷", 25),
    "crosslist": ("Cross-list an item on eBay or Depop", "🔁", 15),
}
CHEST_XP = 25
CHEST_PERKS = {"price_check": 1}
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


def pick(day: date) -> list[str]:
    """Today's three quests: always a listing goal, plus two that rotate daily (same for everyone, every load)."""
    rest = [q for q in QUEST_POOL if q != "list"]
    return ["list"] + random.Random(day.toordinal()).sample(rest, 2)


def _day_quests(day: date, d: dict, goal: int) -> list[dict]:
    n = max(2, goal + 1)
    counts = {"list": d.get("listed", 0), "full_set": d.get("full_sets", 0), "premium": d.get("premium", 0),
              "hot": d.get("hot", 0), "sale": d.get("sold", 0), "crosslist": d.get("crosslisted", 0)}
    out = []
    for qid in pick(day):
        text, icon, xp = QUEST_POOL[qid]
        target = n if qid == "list" else 1
        have = min(target, counts[qid])
        out.append({"id": qid, "text": text.format(n=n), "icon": icon, "xp": xp, "have": have, "target": target,
                    "done": have >= target})
    return out


def daily_stats(day_stats: dict, goal: int, today: date) -> dict:
    """Today's quests plus totals over every active day: quest XP, chests opened."""
    quest_xp = chests = 0
    for day, d in day_stats.items():
        if day > today:
            continue
        qs = _day_quests(day, d, goal)
        quest_xp += sum(q["xp"] for q in qs if q["done"])
        if all(q["done"] for q in qs):
            chests += 1
            quest_xp += CHEST_XP
    today_q = _day_quests(today, day_stats.get(today, {}), goal)
    return {"quests": today_q, "chest_ready": all(q["done"] for q in today_q), "quest_xp": quest_xp, "chests": chests,
            "quest_xp_today": sum(q["xp"] for q in today_q if q["done"]) + (CHEST_XP if all(q["done"] for q in today_q) else 0)}


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
