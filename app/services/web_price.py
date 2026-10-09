"""Second-opinion resale price from a short web search of sold listings.

One Claude call with Anthropic's server-side web search (at most a few
searches). Returns a typical price, a range and the sold examples it found,
or None. Never raises; a failed search must not block a listing.
"""
import json
import logging
import os
import re
import time

from app import config
from app.services import model_usage

log = logging.getLogger(__name__)

MODEL = os.getenv("WEB_PRICE_MODEL", config.HAIKU_MODEL)
MAX_SEARCHES = int(os.getenv("WEB_PRICE_MAX_SEARCHES", "3"))

_PROMPT = """You price second-hand clothing for a UK Vinted seller.
Search the web for recently SOLD prices of this item or the closest equivalents
(eBay UK sold listings first, then Vinted, Depop, eBay US). Prefer the same brand,
product line and condition. Convert to GBP. Asking prices are weaker evidence than sold prices.

Item:
{facts}

Reply with ONLY this JSON, no other text:
{{"typical_gbp": number, "low_gbp": number, "high_gbp": number,
  "confidence": "high" | "medium" | "low",
  "examples": [{{"title": string, "price_gbp": number, "sold": true | false, "url": string}}],
  "note": "one short sentence on what the evidence shows"}}
Use at most 6 examples. If you find nothing useful, set confidence to "low"."""


def available():
    """The search can run at all (an API key is set), whether or not it's switched on for every item."""
    return bool(config.ANTHROPIC_API_KEY)


def enabled():
    # Off by default: ~4p and ~9s per item for little pricing gain in the first
    # live test (7 Oct 2026). Set ENABLE_WEB_PRICE=1 to try it again.
    return bool(config.ANTHROPIC_API_KEY) and os.getenv("ENABLE_WEB_PRICE", "0") == "1"


def _facts(listing):
    from app.services.condition import canonical_level
    rows = [("Brand", listing.get("brand")), ("Item", listing.get("item_type")),
            ("Model / line", listing.get("model_name")),
            ("Tag words", ", ".join(listing.get("tag_keywords") or [])),
            ("Size", listing.get("normalized_size") or listing.get("tagged_size")),
            ("Colour", listing.get("colour")), ("Materials", ", ".join(listing.get("materials") or [])),
            ("Condition", canonical_level(listing.get("condition_summary"))),
            ("Flaws", listing.get("flaws_note")), ("Title", listing.get("title"))]
    return "\n".join(f"- {name}: {value}" for name, value in rows if value)


def _parse(text):
    match = re.search(r"\{[\s\S]*\}", text or "")
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        typical, low, high = (float(data[k]) for k in ("typical_gbp", "low_gbp", "high_gbp"))
    except (ValueError, KeyError, TypeError):
        return None
    if not 0 < low <= typical <= high <= 5000:
        return None
    examples = []
    for ex in data.get("examples") or []:
        if not isinstance(ex, dict):
            continue
        try:
            price = round(float(ex.get("price_gbp")), 2)
        except (TypeError, ValueError):
            continue
        url = str(ex.get("url") or "")
        examples.append({"title": str(ex.get("title") or "")[:160], "price_gbp": price,
                         "sold": ex.get("sold") is True,
                         "url": url if url.startswith(("https://", "http://")) else ""})
    return {"typical_gbp": round(typical, 2), "low_gbp": round(low, 2), "high_gbp": round(high, 2),
            "confidence": data.get("confidence") if data.get("confidence") in ("high", "medium", "low") else "low",
            "examples": examples[:6], "sold_count": sum(ex["sold"] for ex in examples[:6]),
            "note": str(data.get("note") or "")[:300]}


def estimate(listing):
    """Return the web price dict (always with cost/latency when a call was made) or None."""
    if not enabled():
        return None
    import anthropic
    from app.services.condition import canonical_level
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, max_retries=1, timeout=90)
    messages = [{"role": "user", "content": _PROMPT.format(facts=_facts(listing))}]
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": MAX_SEARCHES,
              "user_location": {"type": "approximate", "country": "GB"}}]
    started, events, text = time.perf_counter(), [], ""
    try:
        for _ in range(3):  # pause_turn: let a long search turn continue
            response = model_usage.call(client.messages.create, stage="web_price", model=MODEL,
                                        max_tokens=2000, tools=tools, messages=messages)
            events.append(response)
            if response.stop_reason != "pause_turn":
                break
            messages = messages + [{"role": "assistant", "content": response.content}]
        text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text")
    except Exception as error:
        log.error("Web price search failed (%s)", type(error).__name__)
    ctx_calls = [c for c in (model_usage._context.get() or {}).get("calls", []) if c.get("stage") == "web_price"]
    calls = ctx_calls[-len(events):] if events else []
    result = _parse(text) or {"confidence": "none", "examples": [], "sold_count": 0,
                              "note": "Web search found no usable prices."}
    result.update(condition_level=canonical_level(listing.get("condition_summary")),
                  latency_ms=round((time.perf_counter() - started) * 1000),
                  searches=sum(c.get("web_search_requests") or 0 for c in calls),
                  cost_gbp=round(sum(c.get("cost_gbp") or 0 for c in calls), 5),
                  model=MODEL)
    return result
