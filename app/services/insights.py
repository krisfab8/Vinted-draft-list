"""Insights: what you sell, what it sells for, and how often you list — worked out from your own
listings and sales. Deterministic, no AI, nothing stored.

build() returns plain numbers for the Insights page:
  headline   sold, revenue, profit, average sale price, sell-through %, days to sell, listed count
  types      per item type: sold, still for sale, average price, sell-through %, days to sell, profit
  brands     top brands by sales
  rhythm     per week (short periods) or month (long): listed, sold, takings, profit

Sell-through = sold ÷ (sold + still for sale): the share of your stock that sold. Never over 100%.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from statistics import median

PERIODS = {"30d": 30, "90d": 90, "12m": 365, "all": None}
MAX_GROUPS = 8   # the rest fold into "Other" so charts stay readable

# Plain-English groups for free-text item types ("polo shirt" and "t-shirt" stay separate on purpose).
_ALIASES = {
    "tshirt": "T-shirt", "t shirt": "T-shirt", "tee": "T-shirt", "t-shirt": "T-shirt",
    "trainer": "Trainers", "trainers": "Trainers", "sneakers": "Trainers", "sneaker": "Trainers",
    "jean": "Jeans", "jeans": "Jeans", "shoe": "Shoes", "shoes": "Shoes", "boot": "Boots", "boots": "Boots",
    "hoodie": "Hoodie", "hoody": "Hoodie", "jumper": "Jumper", "sweater": "Jumper",
}


def type_group(item_type) -> str:
    text = " ".join(str(item_type or "").strip().lower().split())
    if not text:
        return "Unknown"
    if text in _ALIASES:
        return _ALIASES[text]
    if text.endswith("s") and text[:-1] in _ALIASES:
        return _ALIASES[text[:-1]]
    return text[:1].upper() + text[1:]


def brand_group(brand) -> str:
    text = " ".join(str(brand or "").split())
    return text if text and text.lower() not in {"unknown", "unbranded", "none", "n/a"} else "Unbranded"


def _day(value) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and len(value) >= 10:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _sell_through(sold: int, live: int):
    return round(100 * sold / (sold + live)) if sold + live else None


def _money(values):
    return round(sum(values) / len(values), 2) if values else None


def _fold(groups: dict, key) -> list:
    """Biggest groups first (by sold count, then name); everything past MAX_GROUPS becomes "Other"."""
    ordered = sorted(groups.items(), key=lambda kv: (-len(kv[1]["prices"]) - len(kv[1].get("live", [])) * 0.001, kv[0]))
    keep, rest = ordered[:MAX_GROUPS], ordered[MAX_GROUPS:]
    if rest:
        other = {"prices": [], "days": [], "profits": [], "live": []}
        for _, g in rest:
            for k in other:
                other[k].extend(g.get(k, []))
        keep.append(("Other", other))
    return [key(name, g) for name, g in keep]


def build(listings: list[dict], sales: list[dict], today: date, period: str = "90d") -> dict:
    """listings: _get_all_listings() rows (need item_type, brand, created date, inventory_status, price_gbp).
    sales: sales_history.read_all() rows (status, sold_date, sold_price_gbp, profit_gbp, days_to_sell, item)."""
    period = period if period in PERIODS else "90d"
    days = PERIODS[period]
    start = today - timedelta(days=days - 1) if days else None

    def in_period(d):
        return d is not None and d <= today and (start is None or d >= start)

    sold = []
    for row in sales:
        when = _day(row.get("sold_date"))
        price = row.get("sold_price_gbp")
        if row.get("status") == "sold" and in_period(when) and isinstance(price, (int, float)):
            item = row.get("item") or {}
            sold.append({"date": when, "price": float(price), "type": type_group(item.get("item_type")),
                         "brand": brand_group(item.get("brand")), "profit": row.get("profit_gbp"),
                         "days": row.get("days_to_sell"), "platform": row.get("platform") or "Other"})

    listed_dates = [d for d in (_day(item.get("created_date")) for item in listings) if in_period(d)]

    # Per item type, including what's still for sale (helps spot types that sit).
    types = defaultdict(lambda: {"prices": [], "days": [], "profits": [], "live": []})
    for s in sold:
        g = types[s["type"]]
        g["prices"].append(s["price"])
        if isinstance(s["days"], (int, float)):
            g["days"].append(s["days"])
        if isinstance(s["profit"], (int, float)):
            g["profits"].append(float(s["profit"]))
    for item in listings:
        if item.get("inventory_status") != "sold":
            types[type_group(item.get("item_type"))]["live"].append(item.get("price_gbp"))

    def type_row(name, g):
        prices = sorted(g["prices"])
        return {"name": name, "sold": len(prices), "for_sale": len(g["live"]),
                "revenue": round(sum(prices), 2),
                "avg": _money(prices), "median": round(median(prices), 2) if prices else None,
                "low": prices[0] if prices else None, "high": prices[-1] if prices else None,
                "avg_days": round(sum(g["days"]) / len(g["days"]), 1) if g["days"] else None,
                "avg_profit": _money(g["profits"]), "profit_known": len(g["profits"]),
                "sell_through": _sell_through(len(prices), len(g["live"]))}
    type_rows = _fold(types, type_row)

    brands = defaultdict(lambda: {"prices": []})
    for s in sold:
        brands[s["brand"]]["prices"].append(s["price"])
    brand_rows = [{"name": name, "sold": len(g["prices"]), "avg": _money(g["prices"]),
                   "revenue": round(sum(g["prices"]), 2)}
                  for name, g in sorted(brands.items(), key=lambda kv: (-len(kv[1]["prices"]), -sum(kv[1]["prices"]), kv[0]))
                  ][:MAX_GROUPS]

    prices = sorted(s["price"] for s in sold)
    sell_days = [s["days"] for s in sold if isinstance(s["days"], (int, float))]
    weeks = max(1, ((days or max(30, (today - min([s["date"] for s in sold] + listed_dates + [today])).days + 1)) / 7))
    live = sum(1 for item in listings if item.get("inventory_status") != "sold")
    profits = [float(s["profit"]) for s in sold if isinstance(s["profit"], (int, float))]
    headline = {
        "sold": len(sold), "revenue": round(sum(prices), 2), "listed": len(listed_dates), "for_sale": live,
        "profit": round(sum(profits), 2) if profits else None, "profit_known": len(profits),
        "sell_through": _sell_through(len(sold), live),
        "avg": _money(prices), "median": round(median(prices), 2) if prices else None,
        "low": prices[0] if prices else None, "high": prices[-1] if prices else None,
        "avg_days": round(sum(sell_days) / len(sell_days), 1) if sell_days else None,
        "listed_per_week": round(len(listed_dates) / weeks, 1),
        "best_type": max((t for t in type_rows if t["sold"] >= 2 and t["name"] != "Other"),
                         key=lambda t: t["avg"], default=None),
    }
    return {"period": period, "periods": list(PERIODS), "headline": headline, "types": type_rows,
            "brands": brand_rows, "rhythm": _rhythm(listed_dates, sold, today, days, start)}


def _rhythm(listed: list[date], sales: list[dict], today: date, days: int | None, start: date | None) -> dict:
    """Listed, sold, takings and profit per week (up to 90 days) or per month (longer)."""
    sold = [s["date"] for s in sales]
    weekly = days is not None and days <= 90
    if weekly:
        first = today - timedelta(days=today.weekday()) - timedelta(weeks=(days // 7))
        buckets = []
        cursor = first
        while cursor <= today:
            buckets.append(cursor)
            cursor += timedelta(weeks=1)

        def bucket(d):
            return d - timedelta(days=d.weekday())

        def label(b):
            return b.strftime("%-d %b")
    else:
        earliest = start or min(listed + sold + [today])
        months = (today.year - earliest.year) * 12 + today.month - earliest.month
        months = min(max(months, 0), 35)
        buckets = []
        y, m = today.year, today.month
        for _ in range(months + 1):
            buckets.append(date(y, m, 1))
            y, m = (y - 1, 12) if m == 1 else (y, m - 1)
        buckets.reverse()

        def bucket(d):
            return date(d.year, d.month, 1)

        def label(b):
            return b.strftime("%b") if b.month != 1 else b.strftime("%b %y")
    counts = {b: [0, 0, 0.0, 0.0, 0] for b in buckets}   # listed, sold, takings, profit, sales with profit
    for d in listed:
        if bucket(d) in counts:
            counts[bucket(d)][0] += 1
    for s in sales:
        c = counts.get(bucket(s["date"]))
        if c is not None:
            c[1] += 1
            c[2] += s["price"]
            if isinstance(s["profit"], (int, float)):
                c[3] += float(s["profit"])
                c[4] += 1
    return {"unit": "week" if weekly else "month",
            "rows": [{"label": label(b), "start": b.isoformat(), "listed": c[0], "sold": c[1],
                      "revenue": round(c[2], 2), "profit": round(c[3], 2) if c[4] else None}
                     for b, c in counts.items()]}
