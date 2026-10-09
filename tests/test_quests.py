"""Daily quests, chests, badges, perks and coin skins — deterministic from listings and sales."""
import json
from datetime import date, timedelta

from app import web
from app.services import item_store, progress, quests, sales_history, user_profile

DAY = date(2026, 10, 20)


def test_three_quests_a_day_always_starting_with_listing():
    for offset in range(30):
        picked = quests.pick(DAY + timedelta(days=offset))
        assert picked[0] == "list" and len(set(picked)) == 3
    assert quests.pick(DAY) == quests.pick(DAY)               # same quests on every load


def test_finishing_all_three_opens_the_chest_and_pays_xp():
    picked = quests.pick(DAY)
    everything = {"listed": 5, "full_sets": 1, "premium": 1, "hot": 1, "sold": 1, "crosslisted": 1}
    out = quests.daily_stats({DAY: everything}, 1, DAY)
    assert out["chest_ready"] and out["chests"] == 1
    expected = sum(quests.QUEST_POOL[q][2] for q in picked) + quests.CHEST_XP
    assert out["quest_xp"] == expected == out["quest_xp_today"]
    half = quests.daily_stats({DAY: {"listed": 1}}, 1, DAY)
    assert not half["chest_ready"] and half["quests"][0]["have"] == 1 and half["quests"][0]["target"] == 2


def test_badges_perks_and_skins():
    stats = {"listed": 12, "sold": 1, "profit": 30, "premium": 2, "full_sets": 0, "crosslisted": 0, "best_streak": 7, "chests": 0}
    unlocked = {b["id"] for b in quests.badges(stats) if b["unlocked"]}
    assert {"first_listing", "ten_listed", "first_sale", "streak_7"} <= unlocked and "profit_100" not in unlocked
    perk = quests.perks(chests=2, level_index=1, used={"price_check": 4})[0]
    assert perk["earned"] == 5 and perk["left"] == 1
    skins = {s["id"]: s["unlocked"] for s in quests.skins(1, set())}
    assert skins == {"brass": True, "silver": True, "rose": False, "emerald": False, "gold": False}
    assert {s["id"]: s["unlocked"] for s in quests.skins(0, {"quest_master"})}["gold"]


def test_summary_counts_todays_quests_from_real_listings(tmp_path):
    listings = [dict(folder=f"upload_{i:08x}", brand="Barbour", price_gbp=45, created_at=DAY.isoformat()) for i in range(3)]
    s = progress.summary(listings, tmp_path, 1, DAY)
    q = {x["id"]: x for x in s["quests"]}
    assert q["list"]["done"] and s["xp"] > sum(progress.item_xp(l) for l in listings)   # quest XP on top
    assert s["badges"][0]["unlocked"] and s["perks"][0]["id"] == "price_check" and s["skins"][0]["unlocked"]


def test_progress_api_skin_choice_and_perk_spending(tmp_path, monkeypatch):
    items = tmp_path / "items"; items.mkdir()
    monkeypatch.setattr(web, "ITEMS_DIR", items)
    monkeypatch.setattr(user_profile, "_PATH", tmp_path / "profile.json")
    monkeypatch.setattr(sales_history, "DB_PATH", tmp_path / "sales.db")
    monkeypatch.setattr(item_store, "DB_PATH", tmp_path / "items.db")
    client = web.app.test_client()
    body = client.get("/api/progress").json
    assert len(body["quests"]) == 3 and "perks" in body
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
