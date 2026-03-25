# Dodis — Product Roadmap

## Status: Beta hardening → Public beta

---

## Now (Beta hardening)

Core pipeline is working. Focus is on reliability and operator experience.

- [x] Vision extraction (Claude Haiku 4.5 + Gemini fallback)
- [x] Listing generation (title, description, price, category)
- [x] Schema validation
- [x] Playwright draft creation on Vinted
- [x] Review routing for uncertain items
- [x] Run logs + correction logging
- [x] Price memory (local JSON)
- [x] Condition + flaws service
- [x] eBay comp fetch (on-demand)
- [x] Listing performance tracker
- [x] Google Sheets sync (MCP)
- [x] Dodis colour system on upload page
- [x] Brand identity (wordmark, icon concept)

---

## Reliability & Failure Handling (Pre-Beta)

Draft creation is the most fragile part of the pipeline. These are required before any external user touches the product.

**Draft failure recovery**
- If `draft_creator.py` fails mid-flow, the item must not be left in an unknown state
- On failure: set item status to `draft_failed`, log the step that failed, surface a clear retry option in the UI
- Do not silently swallow errors — every failure must be visible in run logs

**Screenshot capture on Playwright failure**
- Any unhandled Playwright exception must trigger a screenshot saved to `debug_screenshots/<folder>_<timestamp>.png`
- Screenshot path should be written into the run log entry for that item
- Already partially in place — needs to be consistent across all failure paths

**Retry strategy**
- One automatic retry on transient failures (network hiccup, element not found on first poll)
- No retry on auth errors (`VintedAuthError`) — surface immediately and prompt reconnect
- No retry on validation failures — these need operator input, not another attempt
- Max 1 retry to avoid duplicate drafts being created silently

**Logging expectations**
- Every draft attempt (success or failure) must produce a run log entry with: `step`, `error_type`, `screenshot_path` (if failed), `duration_ms`
- Failures must be distinguishable in the run log by `status: "draft_failed"` vs `"draft_created"`
- Stats page should surface draft failure rate so it's visible over time

---

## Next (Polish for first users)

Make the product feel like Dodis, not an internal tool.

- [ ] Apply Dodis design system across all pages (drafts, review, stats)
- [ ] Centralise category mapping (remove duplication between extractor + listing writer)
- [ ] Mobile PWA install experience (home screen, splash screen, icon)
- [ ] Onboarding flow — 5-question user profiling (casual / reseller / mixed) with Duolingo-style UX
- [ ] Streak / items listed counter on stats page
- [ ] Celebration moment on first draft created
- [ ] Pricing confidence indicator in review UI
- [ ] "Price like this" explanation in listing (why this price)
- [ ] eBay comps shown inline on review page

---

## Soon (Reseller features)

Make Dodis a real system for serious sellers.

- [ ] Batch upload (multiple items in one session)
- [ ] Markdown schedule automation (price drop rules)
- [ ] Profit/ROI per item on stats page
- [ ] Brand performance breakdown (which brands sell best/fastest)
- [ ] Low-confidence field highlighting with suggested fixes
- [ ] Correction learning (feed corrections back to improve future extractions)
- [ ] Search and filter in draft bank

---

## Later (Platform expansion)

- [ ] eBay listing creation (alongside Vinted)
- [ ] Depop listing creation
- [ ] Cross-platform dashboard (all platforms, one view)
- [ ] Mobile-first camera flow (photo → listing in-app)
- [ ] Telegram/push alerts on item sold
- [ ] Seller community / leaderboard features

---

## Never (explicit non-goals)

- Auto-publish without operator review
- Replacing operator judgement on condition or flaws
- Removing validation or schema checks
- Storing payment or financial data

---

## Version targets

| Version | Goal |
|---------|------|
| 0.x | Internal operator tool (current) |
| 1.0 | Public beta — casual seller can use it without help |
| 1.5 | Reseller tier — batch, analytics, markdown automation |
| 2.0 | Multi-platform — Vinted + eBay + Depop |
| 3.0 | Mobile app |
