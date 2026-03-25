# Dodis — Ideas Backlog

A living list. Add ideas freely. Move to PRODUCT_ROADMAP.md when committed.

Format: `[tag] Idea — brief note`
Tags: `[ux]` `[ai]` `[pricing]` `[growth]` `[platform]` `[reseller]` `[mobile]` `[data]`

---

## High interest

[ux] **"Why this price?" explanation** — one sentence in review UI explaining the price logic. Builds seller trust. E.g. "Priced at £28 based on Ralph Lauren polo comps on eBay (avg £32 sold)."

[ux] **Streak + items listed counter** — Duolingo-style. "You've listed 14 items this week 🔥" on the stats page or post-listing screen.

[ux] **Celebration moment on first draft** — confetti / flame animation when a user creates their very first Vinted draft. One-time, memorable.

[ai] **Condition auto-photo detection** — scan photos for visible flaws (pills, stains) using vision model. Pre-fill flaws note. Reduces operator effort.

[pricing] **Live Vinted price comps** — scrape active Vinted search results for the brand + item type. Show range in review UI.

[pricing] **"Sell faster" vs "Sell higher" toggle** — operator picks a mode per item. Affects pricing band positioning (bottom vs top third).

[reseller] **Batch upload session** — list multiple items in one sitting. Queue them up, run extraction in parallel, review in sequence.

[mobile] **Camera → listing flow** — take photos in-app (or pick from camera roll), skip the folder system entirely. For casual sellers.

---

## Interesting, explore later

[ux] **Review page warnings as inline suggestions** — instead of warning banners, show "Did you mean: Barbour?" inline next to the brand field.

[ux] **Item age tracking** — "This draft has been sitting for 12 days. Want to lower the price?" Prompted nudge in draft bank.

[ai] **Material quality score** — beyond just extracting materials, rate them: "Wool/cashmere = premium", "Polyester = standard". Feed into pricing.

[ai] **Smarter title A/B testing** — generate 2 title variants, track which gets more views/favourites on Vinted.

[growth] **Referral mechanic** — "Share Dodis with a friend, both get 50 free listings". Duolingo-style virality.

[growth] **Public seller profile** — optional page showing your listed items, with a shareable link. Like a mini-shop.

[platform] **eBay draft creation** — parallel to Vinted. Same extraction, different template. Playwright on eBay sell flow.

[platform] **Depop integration** — younger audience, higher margin on streetwear. Depop listing has different format requirements.

[platform] **"Post to all" mode** — one extraction, three platform drafts created simultaneously.

[reseller] **Supplier tagging** — tag where you bought the item (charity shop, car boot, eBay). Analytics by source.

[reseller] **Turn rate by brand** — which brands sell fastest? Surface this in stats. Helps resellers buy smarter.

[data] **Price memory auto-update on sale** — when an item sells, update price_memory.json with the sell price. Self-improving pricing.

[data] **Correction heatmap** — which fields do operators correct most? Show in stats. Use to improve extraction prompts.

[mobile] **Widget / home screen shortcut** — iOS widget showing items listed this week, total potential earnings.

[ux] **Dark mode** — with Dodis dark palette: charcoal/slate bg, red + white wordmark, green accents.

[ux] **Onboarding walkthrough** — 3-step guided first listing. Step 1: "Take or upload photos of your item." Step 2: "We'll read the tags for you." Step 3: "Review and list."

---

## Unlikely / parking lot

[ux] Gamified seller rank / levels (Iron → Gold → Flame tier) — could feel gimmicky

[platform] Vinted messaging automation — risky, violates ToS likely

[ai] Auto-publish without review — too risky for pricing/quality

[growth] Seller leaderboard — need community scale first

[platform] Facebook Marketplace — low resale value audience, probably not worth it

---

## Recently graduated to roadmap

- eBay comp fetch (on-demand) → shipped
- Listing performance tracker → shipped
- Condition + flaws service → shipped
- Price memory → shipped
