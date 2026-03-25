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

## Next (Polish for first users)

Make the product feel like Dodis, not an internal tool.

- [ ] Apply Dodis design system across all pages (drafts, review, stats)
- [ ] Mobile PWA install experience (home screen, splash screen, icon)
- [ ] Onboarding flow for new users (first item walkthrough)
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
