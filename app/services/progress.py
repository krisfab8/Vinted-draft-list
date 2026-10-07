"""Streaks, XP and levels — worked out from listings and sales, never stored, never AI.

Deterministic so it survives restarts/restores and can't drift from the real items.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

XP_LIST = 10            # every listing created
XP_FULL_SET = 5         # front, back, brand, size and care label photos all present
XP_PREMIUM = 15         # ★ premium piece
XP_HOT = 25             # 🔥 hot piece (premium and £40+); replaces the premium bonus
XP_SOLD = 20            # marked sold, plus £1 of profit = 1 XP
HOT_PRICE_GBP = 40

LEVELS = [(0, "Rookie"), (300, "Trader"), (1200, "Pro Seller"), (4000, "Top Seller")]

PREMIUM_BRANDS = {
    "barbour", "belstaff", "grenfell", "gloverall", "margaret howell", "brora", "john smedley",
    "suitsupply", "suit supply", "ermenegildo zegna", "zegna", "canali", "corneliani", "hackett",
    "paul smith", "peter millar", "ralph lauren purple label", "loro piana", "brunello cucinelli",
    "stone island", "c.p. company", "cp company", "moncler", "burberry", "hugo boss", "boss",
    "acne studios", "arc'teryx", "arcteryx", "patagonia", "canada goose", "vitale barberis canonico",
}
PREMIUM_MATERIALS = ("cashmere", "merino", "silk", "leather", "suede", "alpaca", "mohair",
                     "camel", "vicuna", "down", "lambswool", "angora")
FULL_SET = ("front", "back", "brand", "model_size", "material")


def created_on(listing: dict, folder: Path | None = None) -> date | None:
    """When the listing was made: saved timestamps first; file time only as a last resort
    (a restore from backup resets file times, which would put everything on one day)."""
    for value in (listing.get("created_at"), (listing.get("run_stats") or {}).get("finished_at"),
                  listing.get("listed_date")):
        if isinstance(value, str) and len(value) >= 10:
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                pass
    if folder is not None:
        try:
            return datetime.fromtimestamp((folder / "listing.json").stat().st_mtime).date()
        except OSError:
            return None
    return None


def tier(listing: dict) -> str | None:
    """'hot' (premium and £40+), 'premium', or None. Premium: flagged by the writer, a premium
    brand, or a premium material."""
    brand = (listing.get("brand") or "").strip().lower()
    materials = " ".join(listing.get("materials") or []).lower()
    premium = bool(listing.get("premium")) or brand in PREMIUM_BRANDS \
        or any(word in materials for word in PREMIUM_MATERIALS)
    if not premium:
        return None
    try:
        price = float(listing.get("price_gbp") or 0)
    except (TypeError, ValueError):
        price = 0
    return "hot" if price >= HOT_PRICE_GBP else "premium"


def item_xp(listing: dict, folder: Path | None = None) -> int:
    xp = XP_LIST
    if folder is not None and all(any((folder / f"{role}{ext}").exists() for ext in (".jpg", ".jpeg", ".png", ".webp"))
                                  for role in FULL_SET):
        xp += XP_FULL_SET
    xp += {"hot": XP_HOT, "premium": XP_PREMIUM}.get(tier(listing), 0)
    outcome = listing.get("outcome") or {}
    if outcome.get("status") == "sold":
        xp += XP_SOLD + max(0, int(outcome.get("profit_gbp") or 0))
    return xp


def level(xp: int) -> dict:
    current = [lvl for lvl in LEVELS if xp >= lvl[0]][-1]
    following = next((lvl for lvl in LEVELS if lvl[0] > xp), None)
    out = {"name": current[1], "xp": xp}
    if following:
        span = following[0] - current[0]
        out.update(next_name=following[1], to_next=following[0] - xp,
                   progress=round((xp - current[0]) / span, 3))
    else:
        out.update(next_name=None, to_next=0, progress=1.0)
    return out


def streak(day_counts: dict, goal: int, today: date) -> tuple[int, bool]:
    """Days in a row meeting the goal. Today only counts once met; until then the streak is
    still alive from yesterday (like Duolingo). Returns (streak, today_met)."""
    goal = max(1, goal)
    today_met = day_counts.get(today, 0) >= goal
    day, count = (today if today_met else today - timedelta(days=1)), 0
    while day_counts.get(day, 0) >= goal:
        count += 1
        day -= timedelta(days=1)
    return count, today_met


def best_streak(day_counts: dict, goal: int) -> int:
    best = run = 0
    previous = None
    for day in sorted(d for d, n in day_counts.items() if n >= max(1, goal)):
        run = run + 1 if previous and day - previous == timedelta(days=1) else 1
        best, previous = max(best, run), day
    return best


def summary(listings: list[dict], root: Path, goal: int, today: date) -> dict:
    """Everything the Progress page and chips need, from the item list."""
    day_counts, xp_total, xp_today, tiers = {}, 0, 0, {"hot": 0, "premium": 0}
    for listing in listings:
        folder = root / listing["folder"] if listing.get("folder") else None
        made = created_on(listing, folder)
        xp = item_xp(listing, folder)
        xp_total += xp
        if made:
            day_counts[made] = day_counts.get(made, 0) + 1
            if made == today:
                xp_today += xp
        kind = tier(listing)
        if kind:
            tiers[kind] += 1
    current, today_met = streak(day_counts, goal, today)
    week = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        count = day_counts.get(day, 0)
        week.append({"label": "Today" if offset == 0 else day.strftime("%a")[:1], "count": count,
                     "met": count >= max(1, goal), "today": offset == 0})
    return {"streak": current, "today_met": today_met, "best_streak": max(best_streak(day_counts, goal), current),
            "today_count": day_counts.get(today, 0), "goal": goal, "xp": xp_total, "xp_today": xp_today,
            "level": level(xp_total), "week": week, "hot": tiers["hot"], "premium": tiers["premium"]}
