"""Insights: per-type counts and prices, brands, listing rhythm and the time filter — all from your own data."""
import json
from datetime import date

from app import web
from app.services import insights, item_store, sales_history, user_profile

TODAY = date(2026, 10, 9)


def sale(day, price, item_type, brand="Nike", profit=None, days=None):
    return {"status": "sold", "sold_date": day, "sold_price_gbp": price, "profit_gbp": profit, "days_to_sell": days,
            "platform": "Vinted", "item": {"item_type": item_type, "brand": brand}}


def listing(made, item_type="T-shirt", status="draft", price=10):
    return {"created_date": made, "item_type": item_type, "inventory_status": status, "price_gbp": price}


SALES = [
    sale("2026-10-01", 10, "t-shirt", profit=6, days=4),
    sale("2026-10-02", 14, "T-Shirt", profit=9, days=6),
    sale("2026-10-03", 30, "tee", days=8),
    sale("2026-09-20", 60, "trainers", brand="Adidas", days=20),
    sale("2026-09-21", 40, "Trainer", brand="Adidas", days=10),
    sale("2025-01-05", 99, "coat", brand="Barbour"),           # outside 90 days
    {"status": "withdrawn", "sold_date": None, "item": {"item_type": "hat"}},
]


def test_types_group_and_price_spread():
    data = insights.build([listing("2026-10-05"), listing("2026-10-06", "Jeans")], SALES, TODAY, "90d")
    types = {t["name"]: t for t in data["types"]}
    tee = types["T-shirt"]
    assert (tee["sold"], tee["avg"], tee["median"], tee["low"], tee["high"]) == (3, 18.0, 14, 10, 30)
    assert tee["avg_days"] == 6.0 and tee["avg_profit"] == 7.5 and tee["profit_known"] == 2
    assert tee["for_sale"] == 1 and types["Jeans"]["sold"] == 0 and types["Jeans"]["for_sale"] == 1
    assert types["Trainers"]["sold"] == 2 and "Coat" not in types          # the coat sold before the period
    h = data["headline"]
    assert (h["sold"], h["revenue"], h["median"], h["low"], h["high"]) == (5, 154, 30, 10, 60)
    assert h["best_type"]["name"] == "Trainers" and h["listed"] == 2
    assert [b["name"] for b in data["brands"]] == ["Nike", "Adidas"]
    # Sell-through = sold / (sold + still for sale): 5 sold, 2 live → 71%; T-shirts 3 sold, 1 live → 75%.
    assert h["sell_through"] == 71 and tee["sell_through"] == 75 and types["Jeans"]["sell_through"] == 0
    assert h["profit"] == 15 and h["profit_known"] == 2


def test_all_time_includes_old_sales_and_bad_period_falls_back():
    assert insights.build([], SALES, TODAY, "all")["headline"]["sold"] == 6
    assert insights.build([], SALES, TODAY, "nonsense")["period"] == "90d"
    assert insights.build([], SALES, TODAY, "30d")["headline"]["sold"] == 5


def test_many_types_fold_into_other():
    many = [sale("2026-10-01", 5 + i, f"type {i}") for i in range(12)]
    names = [t["name"] for t in insights.build([], many, TODAY, "30d")["types"]]
    assert len(names) == insights.MAX_GROUPS + 1 and names[-1] == "Other"


def test_rhythm_counts_listed_and_sold_per_week_and_month():
    listings = [listing("2026-10-06"), listing("2026-10-07"), listing("2026-09-29")]
    weekly = insights.build(listings, SALES, TODAY, "30d")["rhythm"]
    assert weekly["unit"] == "week"
    this_week = weekly["rows"][-1]
    assert this_week["start"] == "2026-10-05" and (this_week["listed"], this_week["sold"]) == (2, 0)
    last_week = weekly["rows"][-2]
    assert (last_week["listed"], last_week["sold"]) == (1, 3)
    assert last_week["revenue"] == 54 and last_week["profit"] == 15 and this_week["profit"] is None
    monthly = insights.build(listings, SALES, TODAY, "12m")["rhythm"]
    assert monthly["unit"] == "month" and monthly["rows"][-1]["start"] == "2026-10-01"
    assert (monthly["rows"][-1]["listed"], monthly["rows"][-1]["sold"]) == (2, 3)


def test_empty_is_safe():
    data = insights.build([], [], TODAY, "90d")
    assert data["headline"]["sold"] == 0 and data["headline"]["avg"] is None and data["types"] == []


def test_insights_page_and_sold_link(tmp_path, monkeypatch):
    root = tmp_path / "items"; root.mkdir()
    monkeypatch.setattr(web, "ITEMS_DIR", root)
    monkeypatch.setattr(item_store, "DB_PATH", tmp_path / "items.db")
    monkeypatch.setattr(sales_history, "DB_PATH", tmp_path / "sales.db")
    monkeypatch.setattr(user_profile, "_PATH", tmp_path / "profile.json")
    item_store.init_db()
    folder = "upload_abcdef12"
    (root / folder).mkdir()
    (root / folder / "listing.json").write_text(json.dumps(dict(
        brand="Barbour", item_type="jacket", title="Barbour jacket", price_gbp=60, created_at="2026-10-01T10:00:00")))
    client = web.app.test_client()
    assert client.post(f"/listing/{folder}/outcome", json={"status": "sold", "platform": "Vinted",
                                                            "sold_price_gbp": 55}).status_code == 200
    page = client.get("/insights?period=all").get_data(as_text=True)
    assert "By type" in page and "Jacket" in page and "£55" in page and "Sell-through" in page
    assert "median" not in page.lower()
    assert 'aria-current="page">All time' in page
    assert client.get("/insights").status_code == 200
    assert 'href="/insights"' in client.get("/sold").get_data(as_text=True)
