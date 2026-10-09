"""Daily quests, chests, badges, perks and coin skins — deterministic from listings and sales."""
import json
from datetime import date, timedelta

from app import web
from app.services import item_store, progress, quests, sales_history, user_profile

DAY = date(2026, 10, 20)


def test_jobs_only_show_real_work_that_applies():
    jobs = quests.jobs({}, 1, stale=0, unpriced=0, still_live=0)
    assert [j["id"] for j in jobs] == ["list"] and not jobs[0]["done"]
    jobs = {j["id"]: j for j in quests.jobs({"listed": 1, "drops": 1}, 1, stale=4, unpriced=2, still_live=1)}
    assert jobs["list"]["done"] and jobs["stale"]["have"] == 1 and jobs["stale"]["target"] == 3 and not jobs["stale"]["done"]
    assert jobs["takedown"]["href"] == "/sold" and jobs["costs"]["target"] == 2
    assert quests.jobs({"drops": 3}, 1, stale=2, unpriced=0, still_live=0)[1]["done"]       # 3 price drops today: done


def test_upkeep_xp_and_the_daily_chest():
    xp, chest = quests.day_xp({"listed": 1, "drops": 12, "takedowns": 1}, 1)
    assert xp == quests.DROP_XP * quests.DROP_CAP + quests.TAKEDOWN_XP and chest
    assert quests.day_xp({"listed": 1}, 1) == (0, False)                     # listing alone: no chest
    assert quests.day_xp({"drops": 2}, 1)[1] is False                        # upkeep without the goal: no chest
    h = quests.history({DAY: {"listed": 1, "sold": 1}, DAY - timedelta(days=1): {"listed": 2, "drops": 1}}, 1, DAY)
    assert h["chests"] == 2 and h["chest_ready"] and h["upkeep_xp"] == quests.DROP_XP + 2 * quests.CHEST_XP


def test_badges_perks_and_skins():
    stats = {"listed": 12, "sold": 1, "profit": 30, "premium": 2, "full_sets": 0, "crosslisted": 0, "best_streak": 7, "chests": 0}
    unlocked = {b["id"] for b in quests.badges(stats) if b["unlocked"]}
    assert {"first_listing", "ten_listed", "first_sale", "streak_7"} <= unlocked and "profit_100" not in unlocked
    perk = quests.perks(chests=2, level_index=1, used={"price_check": 4})[0]
    assert perk["earned"] == 5 and perk["left"] == 1
    skins = {s["id"]: s["unlocked"] for s in quests.skins(1, set())}
    assert skins == {"brass": True, "silver": True, "rose": False, "emerald": False, "gold": False}
    assert {s["id"]: s["unlocked"] for s in quests.skins(0, {"quest_master"})}["gold"]


def test_summary_builds_jobs_from_stale_stock_and_sales(tmp_path):
    old = (DAY - timedelta(days=40)).isoformat()
    listings = [dict(folder="upload_00000001", brand="Gap", price_gbp=10, created_at=old),
                dict(folder="upload_00000002", brand="Gap", price_gbp=12, created_at=old,
                     price_history=[{"from_gbp": 15, "to_gbp": 12, "changed_at": DAY.isoformat()}]),
                dict(folder="upload_00000003", brand="Gap", price_gbp=9, created_at=DAY.isoformat(),
                     outcome={"status": "sold", "sold_date": DAY.isoformat(), "buy_price_gbp": None, "profit_gbp": None},
                     still_live=["eBay"])]
    s = progress.summary(listings, tmp_path, 1, DAY)
    jobs = {j["id"]: j for j in s["quests"]}
    assert s["stale"] == 1 and jobs["stale"]["have"] == 1                     # one stale left, one dropped today
    assert jobs["takedown"]["target"] == 1 and jobs["costs"]["target"] == 1
    assert s["chest_ready"]                                                  # goal hit + a price drop and a sale
    assert progress.stale_days(listings[0], None, DAY) == 40 and progress.stale_days(listings[1], None, DAY) == 0


def test_progress_api_skin_choice_and_perk_spending(tmp_path, monkeypatch):
    items = tmp_path / "items"; items.mkdir()
    monkeypatch.setattr(web, "ITEMS_DIR", items)
    monkeypatch.setattr(user_profile, "_PATH", tmp_path / "profile.json")
    monkeypatch.setattr(sales_history, "DB_PATH", tmp_path / "sales.db")
    monkeypatch.setattr(item_store, "DB_PATH", tmp_path / "items.db")
    client = web.app.test_client()
    body = client.get("/api/progress").json
    assert body["quests"][0]["id"] == "list" and "perks" in body
    assert client.post("/api/progress/skin", json={"skin": "emerald"}).status_code == 422   # locked
    assert client.post("/api/progress/skin", json={"skin": "brass"}).status_code == 200
    assert user_profile.load()["coin_skin"] == "brass"
    assert 'data-coin-skin="brass"' in client.get("/progress").get_data(as_text=True)
    assert not web._price_check_perk()                       # none earned yet
    web._spend_perk("price_check")
    assert user_profile.load()["perks_used"] == {"price_check": 1}


def test_price_check_perk_runs_the_sold_price_search_once(monkeypatch):
    """Off for everyone by default; a perk turns it on for one listing, and only a real result counts."""
    from pathlib import Path
    from unittest.mock import patch
    from app.services import pipeline, web_price
    monkeypatch.setattr(web_price, "enabled", lambda: False)
    monkeypatch.setattr(web_price, "available", lambda: True)
    calls = []
    monkeypatch.setattr(web_price, "estimate", lambda listing: calls.append(1) or {"typical_gbp": 40, "low_gbp": 30, "high_gbp": 50})
    with patch("app.services.pipeline.listing_writer") as writer, patch("app.services.pipeline.extractor") as extractor:
        extractor.extract.return_value = ({"brand": "Barbour", "_extract_log": {}}, {"model": "m"})
        writer.write.side_effect = lambda *a, **k: ({"title": "Barbour Jacket", "price_gbp": 60}, {"model": "m", "_write_log": {}})
        plain = pipeline.run_pipeline(Path("/fake/folder"), hints={})[0]
        perk = pipeline.run_pipeline(Path("/fake/folder"), hints={}, price_check=True)[0]
    assert len(calls) == 1 and "web_price_perk" not in plain and perk["web_price_perk"] is True
