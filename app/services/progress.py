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

MILESTONES = (3, 7, 14, 30, 50, 100, 200, 365)
FREEZE_EVERY = 7        # a 7-day run earns a streak freeze
MAX_FREEZES = 2

# Honest seller tips: Vinted's own help page says recency/new listings get visibility; eBay's ranking
# is unpublished, so we only say what's widely agreed (sales history and steady selling help).
TIPS = (
    "Vinted shows new listings first, so a few items every day keeps you in front of buyers.",
    "Little and often beats one big batch: each new item lands at the top of Vinted's \"Newest first\".",
    "eBay ranks listings that sell. Listing steadily builds the sales history that helps you climb.",
    "Steady sellers build momentum: more listings live means more chances to be found every day.",
    "Answer messages quickly and post within a day. Fast sellers get more repeat buyers.",
    "Clear daylight photos get more clicks, and more clicks help a listing get shown more.",
)


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


def _has_full_set(folder: Path) -> bool:
    from app.services.item_backup import backup_files
    try:
        stems = {name.rsplit(".", 1)[0] for name in backup_files(folder)}  # includes photos still in the cloud
    except OSError:
        return False
    return all(role in stems for role in FULL_SET)


def item_xp(listing: dict, folder: Path | None = None) -> int:
    xp = XP_LIST
    if folder is not None and _has_full_set(folder):
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


def streak_info(day_counts: dict, goal: int, today: date) -> dict:
    """The streak with Duolingo-style freezes: every 7-day run earns a freeze (max 2), and a missed day
    uses one up automatically instead of breaking the streak. Today only counts once met.
    Returns run (current streak), before_today, today_met, freezes, frozen (days saved), best."""
    goal = max(1, goal)
    met = lambda d: day_counts.get(d, 0) >= goal
    first = min((d for d in day_counts if met(d) and d <= today), default=None)
    run = best = freezes = 0
    frozen: list[date] = []
    if first is not None:
        day = first
        while day < today:
            if met(day):
                run += 1
                if run % FREEZE_EVERY == 0:
                    freezes = min(MAX_FREEZES, freezes + 1)
            elif run and freezes:
                freezes -= 1
                frozen.append(day)
            else:
                run = 0
            best = max(best, run)
            day += timedelta(days=1)
    before = run
    today_met = met(today)
    if today_met:
        run += 1
        if run % FREEZE_EVERY == 0:
            freezes = min(MAX_FREEZES, freezes + 1)
    return {"run": run, "before_today": before, "today_met": today_met, "freezes": freezes,
            "frozen": frozen, "best": max(best, run)}


def milestones(run: int) -> dict:
    """Next milestone and how far along the way to it the streak is."""
    previous = max((m for m in MILESTONES if m <= run), default=0)
    upcoming = next((m for m in MILESTONES if m > run), None)
    out = {"previous": previous, "next": upcoming, "hit_today": run in MILESTONES}
    if upcoming:
        out.update(to_go=upcoming - run, progress=round((run - previous) / (upcoming - previous), 3))
    else:
        out.update(to_go=0, progress=1.0)
    return out


def _day(value) -> date | None:
    if isinstance(value, str) and len(value) >= 10:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def summary(listings: list[dict], root: Path, goal: int, today: date, perks_used: dict | None = None) -> dict:
    """Everything the Progress page and chips need, from the item list."""
    from app.services import quests
    day_counts, xp_total, xp_today, tiers = {}, 0, 0, {"hot": 0, "premium": 0}
    day_stats: dict = {}                         # per day: listed, full_sets, premium, hot, sold, crosslisted
    totals = {"listed": 0, "sold": 0, "profit": 0.0, "premium": 0, "full_sets": 0, "crosslisted": 0}
    bump = lambda day, key: day_stats.setdefault(day, {}).__setitem__(key, day_stats[day].get(key, 0) + 1)
    for listing in listings:
        folder = root / listing["folder"] if listing.get("folder") else None
        made = created_on(listing, folder)
        xp = item_xp(listing, folder)
        xp_total += xp
        kind = tier(listing)
        full = folder is not None and _has_full_set(folder)
        totals["listed"] += 1
        totals["full_sets"] += full
        if kind:
            tiers[kind] += 1
            totals["premium"] += 1
        if made:
            day_counts[made] = day_counts.get(made, 0) + 1
            if made == today:
                xp_today += xp
            bump(made, "listed")
            if full:
                bump(made, "full_sets")
            if kind:
                bump(made, "premium")
            if kind == "hot":
                bump(made, "hot")
        outcome = listing.get("outcome") or {}
        if outcome.get("status") == "sold":
            totals["sold"] += 1
            totals["profit"] += float(outcome.get("profit_gbp") or 0)
            sold_on = _day(outcome.get("sold_date"))
            if sold_on:
                bump(sold_on, "sold")
        where = listing.get("crosslist") or {}
        if len(where) >= 2:
            totals["crosslisted"] += 1
        for platform, entry in where.items():
            marked = _day((entry or {}).get("at")) if platform != "Vinted" else None
            if marked and (entry or {}).get("status") in ("live", "removed", "sold"):
                bump(marked, "crosslisted")
    info = streak_info(day_counts, goal, today)
    current, today_met = info["run"], info["today_met"]
    frozen = set(info["frozen"])
    week = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        count = day_counts.get(day, 0)
        week.append({"label": "Today" if offset == 0 else day.strftime("%a")[:1], "count": count,
                     "met": count >= max(1, goal), "today": offset == 0, "frozen": day in frozen})
    saved_yesterday = (today - timedelta(days=1)) in frozen
    best = max(best_streak(day_counts, goal), info["best"])
    daily = quests.daily_stats(day_stats, goal, today)
    xp_total += daily["quest_xp"]
    xp_today += daily["quest_xp_today"]
    lvl = level(xp_total)
    level_index = [name for _, name in LEVELS].index(lvl["name"])
    stats = dict(totals, best_streak=best, chests=daily["chests"])
    badge_list = quests.badges(stats)
    unlocked = {b["id"] for b in badge_list if b["unlocked"]}
    return {"streak": current, "today_met": today_met, "best_streak": best,
            "streak_before_today": info["before_today"], "freezes": info["freezes"], "freeze_saved_yesterday": saved_yesterday,
            "milestone": milestones(current), "tip": TIPS[today.toordinal() % len(TIPS)],
            "today_count": day_counts.get(today, 0), "goal": goal, "xp": xp_total, "xp_today": xp_today,
            "listed": totals["listed"], "sold": totals["sold"], "level": lvl, "week": week, "hot": tiers["hot"], "premium": tiers["premium"],
            "quests": daily["quests"], "chest_ready": daily["chest_ready"], "chests": daily["chests"],
            "chest_xp": quests.CHEST_XP, "badges": badge_list, "perks": quests.perks(daily["chests"], level_index, perks_used),
            "skins": quests.skins(level_index, unlocked)}
