"""Streaks, XP, levels and premium/hot tiers — deterministic from listings."""
import json
from datetime import date, timedelta

from app import web
from app.services import progress, user_profile

TODAY = date(2026, 10, 7)


def made(days_ago, **extra):
    return dict(created_at=(TODAY - timedelta(days=days_ago)).isoformat() + "T10:00:00", **extra)


def test_tiers_from_flag_brand_or_material_and_price():
    assert progress.tier({"brand": "Primark", "price_gbp": 60}) is None
    assert progress.tier({"brand": "Barbour", "price_gbp": 30}) == "premium"
    assert progress.tier({"brand": "Barbour", "price_gbp": 40}) == "hot"
    assert progress.tier({"materials": ["100% Cashmere"], "price_gbp": 45}) == "hot"
    assert progress.tier({"premium": True, "price_gbp": 10}) == "premium"


def test_xp_per_item_and_sale(tmp_path):
    folder = tmp_path / "upload_1"; folder.mkdir()
    for role in progress.FULL_SET:
        (folder / f"{role}.jpg").write_bytes(b"x")
    assert progress.item_xp({"brand": "Barbour", "price_gbp": 50}, folder) == 10 + 5 + 25
    sold = {"outcome": {"status": "sold", "profit_gbp": 12.6}}
    assert progress.item_xp(sold) == 10 + 20 + 12


def test_streak_stays_alive_until_today_ends_and_counts_goal_days():
    counts = {TODAY - timedelta(days=1): 2, TODAY - timedelta(days=2): 1, TODAY - timedelta(days=3): 3}
    assert progress.streak(counts, 1, TODAY) == (3, False)          # not listed today yet: still alive
    assert progress.streak({**counts, TODAY: 1}, 1, TODAY) == (4, True)
    assert progress.streak(counts, 2, TODAY) == (1, False)          # day -2 missed a goal of 2
    assert progress.best_streak(counts, 1) == 3


def test_summary_levels_week_and_restored_file_times_do_not_count_as_today(tmp_path):
    listings = [dict(made(0, brand="Barbour", price_gbp=50), folder="a"),
                dict(made(1), folder="b"), dict(made(2), folder="c")]
    s = progress.summary(listings, tmp_path, 1, TODAY)
    assert s["streak"] == 3 and s["today_met"] and s["today_count"] == 1
    assert s["xp"] == 35 + 10 + 10 and s["xp_today"] == 35 and s["hot"] == 1
    assert s["level"]["name"] == "Rookie" and s["level"]["next_name"] == "Trader" and s["level"]["to_next"] == 245
    assert [d["count"] for d in s["week"]][-3:] == [1, 1, 1] and s["week"][-1]["label"] == "Today"
    # A listing with a saved timestamp is dated by it, not by when the file was restored.
    assert progress.created_on({"run_stats": {"finished_at": "2026-09-01T09:00:00"}}) == date(2026, 9, 1)


def test_progress_page_and_drafts_chip(monkeypatch, tmp_path):
    items = tmp_path / "items"; items.mkdir()
    monkeypatch.setattr(web, "ITEMS_DIR", items)
    monkeypatch.setattr(user_profile, "_PATH", tmp_path / "profile.json")
    folder = items / "upload_1"; folder.mkdir()
    (folder / "listing.json").write_text(json.dumps(dict(brand="Barbour", title="Barbour jacket", price_gbp=55,
                                                         tagged_size="L", created_at="2026-10-07T09:00:00")))
    client = web.app.test_client()
    page = client.get("/progress").get_data(as_text=True)
    assert "Earn XP" in page and "Rookie" in page and "+25" in page
    assert 'class="sn-back" href="/drafts"' in page
    drafts = client.get("/drafts").get_data(as_text=True)
    assert 'href="/progress" class="sn-streak sn-xp-chip' in drafts and "35 XP" in drafts
    assert 'draft-premium-tag hot' in drafts
    # The spinning XP coin: big on Progress, mini in the chip, script on every page.
    assert 'id="pgCoin" data-coin="idle"' in page and "coin.js" in page
    assert 'class="coin" data-coin="idle" style="--coin:18px"' in drafts
