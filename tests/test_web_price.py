"""Web sold-price search: parsing, cost/time capture and how pricing uses it."""
import json
from types import SimpleNamespace

import pytest

from app import config
from app.services import model_usage, pricing, web_price

REPLY = {"typical_gbp": 32, "low_gbp": 26, "high_gbp": 40, "confidence": "medium",
         "examples": [{"title": "Peter Millar Summer Comfort polo NWT", "price_gbp": 34, "sold": True,
                       "url": "https://www.ebay.co.uk/itm/1"},
                      {"title": "Peter Millar polo S", "price_gbp": 28.5, "sold": True, "url": "javascript:x"},
                      {"title": "Peter Millar polo asking", "price_gbp": 45, "sold": False, "url": ""}],
         "note": "NWT examples sell around £30–£35."}


class FakeClient:
    replies = []

    def __init__(self, **kwargs):
        self.messages = self

    def create(self, **kwargs):
        assert kwargs["tools"][0]["type"] == "web_search_20250305"
        assert kwargs["tools"][0]["max_uses"] == web_price.MAX_SEARCHES
        stop, text = FakeClient.replies.pop(0)
        usage = SimpleNamespace(input_tokens=9000, output_tokens=400, cache_creation_input_tokens=0,
                                cache_read_input_tokens=0,
                                server_tool_use=SimpleNamespace(web_search_requests=2))
        return SimpleNamespace(stop_reason=stop, usage=usage,
                               content=[SimpleNamespace(type="text", text=text)])


@pytest.fixture
def fake(monkeypatch, tmp_path):
    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", FakeClient)
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(model_usage, "LEDGER_PATH", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(web_price, "MODEL", "claude-haiku-4-5-20251001")
    return FakeClient


ITEM = dict(brand="Peter Millar", item_type="polo shirt", normalized_size="S",
            tag_keywords=["Summer Comfort"], condition_summary="New with tags")


def test_estimate_parses_reply_and_records_cost_and_time(fake):
    fake.replies = [("end_turn", "Here you go:\n" + json.dumps(REPLY))]
    with model_usage.run("upload_0123abcd"):
        result = web_price.estimate(ITEM)
    assert result["typical_gbp"] == 32 and result["sold_count"] == 2
    assert result["examples"][1]["url"] == ""  # non-http links dropped
    assert result["searches"] == 2
    # 9000 in + 400 out on Haiku ($1/$5 per M) + 2 searches at $0.01
    expected_usd = (9000 * 1 + 400 * 5) / 1e6 + 0.02
    assert result["cost_gbp"] == round(expected_usd * model_usage.USD_TO_GBP, 5)
    assert result["condition_level"] == "New with tags" and result["latency_ms"] >= 0


def test_pause_turn_continues_and_bad_reply_is_not_used(fake):
    fake.replies = [("pause_turn", ""), ("end_turn", "no prices, sorry")]
    with model_usage.run("upload_0123abcd"):
        result = web_price.estimate(ITEM)
    assert result["confidence"] == "none" and result["searches"] == 4
    assert "typical_gbp" not in result


def test_disabled_without_key(monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    assert web_price.estimate(ITEM) is None


@pytest.fixture
def no_memory(monkeypatch):
    monkeypatch.setattr(pricing, "lookup_memory", lambda **kwargs: None)
    from app.services import sales_history
    monkeypatch.setattr(sales_history, "comparisons", lambda listing: {})


def web(**extra):
    return {**REPLY, "sold_count": 2, "condition_level": "New with tags", **extra}


def test_pricing_uses_web_sold_prices_over_ai_guess(no_memory):
    listing = pricing.apply_pricing(dict(ITEM, price_gbp=25, ai_price_condition="Excellent", web_price=web()))
    assert listing["price_gbp"] == 32
    assert listing["price_evidence"]["source"] == "web_sold_search"
    assert listing["price_range"]["basis"] == "web"
    assert not any(a.startswith("no memory match") for a in listing["price_adjustments"])


def test_web_price_follows_later_condition_change(no_memory):
    listing = pricing.apply_pricing(dict(ITEM, price_gbp=25, condition_summary="Good used condition",
                                         web_price=web()))
    assert listing["price_gbp"] == round(32 * 0.85 / 1.30)


def test_weak_web_evidence_is_ignored(no_memory):
    weak = web(confidence="low")
    listing = pricing.apply_pricing(dict(ITEM, price_gbp=30, ai_price_condition="New with tags", web_price=weak))
    assert listing["price_gbp"] == 30
    one_sale = web(sold_count=1)
    assert pricing.apply_pricing(dict(ITEM, price_gbp=30, ai_price_condition="New with tags",
                                      web_price=one_sale))["price_gbp"] == 30


def test_run_stats_split_time_and_cost_by_stage():
    from app.services.pipeline import _run_stats
    calls = [{"cost_gbp": 0.01, "input_tokens": 100, "output_tokens": 10, "model": "m"},
             {"cost_gbp": 0.002, "input_tokens": 50, "output_tokens": 5, "model": "m"},
             {"cost_gbp": 0.02, "input_tokens": 9000, "output_tokens": 400, "model": "m", "web_search_requests": 2}]
    marks = [("Reading photos", 0.0, 0), ("Writing listing", 4.0, 1), ("Web price search", 6.5, 2),
             ("Pricing", 15.0, 3), ("end", 15.01, 3)]
    stats = _run_stats(marks, calls, "now")
    assert [s["name"] for s in stats["stages"]] == ["Reading photos", "Writing listing", "Web price search", "Pricing"]
    assert stats["stages"][2]["searches"] == 2 and stats["stages"][2]["ms"] == 8500
    assert stats["total_cost_gbp"] == 0.032 and stats["total_ms"] == 15010
