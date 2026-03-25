# Dodis — Ideas Backlog

## How to maintain this file

Add any idea here the moment it comes up — in conversation, during testing, or from user feedback.
Don't filter too hard. Raw ideas are fine. Clean them up when they graduate.

Rules:
- Use the section that best fits. If unsure, add to **Future Ideas**.
- One line per idea unless it needs context.
- When an idea gets committed to the roadmap, move it to **Graduated** at the bottom.
- When an idea is ruled out permanently, move it to **Parking Lot** with a one-line reason.
- Do not delete ideas — archive them in Parking Lot instead.

Prompt to update this file after a conversation:
> "Update docs/IDEAS.md with any new ideas from this conversation. Add each to the right section. Move anything we committed to the roadmap into Graduated. Don't invent ideas — only use what came up."

---

## Beta Improvements

Ideas that would make the current product better before launch. Directly actionable.

- **"Why this price?" explanation** — one sentence in the review UI. E.g. "£28 based on Ralph Lauren polo eBay comps (avg £32 sold)." Builds trust without friction.
- **Review page warnings as inline suggestions** — replace warning banners with "Did you mean: Barbour?" inline next to the field.
- **Item age nudge in draft bank** — "This draft has been sitting for 12 days. Lower the price?" Prompted, not automatic.
- **Pricing confidence indicator** — show high/medium/low confidence next to the price in review.
- **eBay comps shown inline on review page** — already fetchable on-demand, just needs surfacing.
- **Correction heatmap in stats** — which fields get corrected most? Use to improve extraction prompts over time.
- **Draft failure rate on stats page** — visible metric so operator knows if Playwright is degrading.

---

## Future Ideas

Bigger or less certain. Worth exploring after beta.

- **Condition auto-photo detection** — scan photos for visible flaws (pills, stains) using vision model. Pre-fill flaws note.
- **Material quality score** — rate materials (wool/cashmere = premium, polyester = standard) and feed into pricing.
- **Live Vinted price comps** — scrape active Vinted search results for brand + item type. Show price range in review.
- **Price memory auto-update on sale** — when an item sells, update `price_memory.json` with the sell price. Self-improving.
- **Smarter title A/B testing** — generate 2 title variants, track which gets more views/favourites on Vinted.
- **Dark mode** — Dodis dark palette: charcoal/slate bg, red + white wordmark, green accents.
- **Onboarding walkthrough** — 3-step guided first listing. "Take photos → We read the tags → Review and list."
- **Streak + items listed counter** — Duolingo-style. "You've listed 14 items this week" on stats or post-listing screen.
- **Celebration moment on first draft** — one-time flame animation when the very first draft is created.

---

## Reseller Ideas

For power users listing 20–100+ items/month.

- **Batch upload session** — queue multiple items, run extraction in parallel, review in sequence.
- **Supplier tagging** — tag where each item was sourced (charity shop, car boot, eBay). Analytics by source.
- **Turn rate by brand** — which brands sell fastest? Surface in stats. Helps resellers buy smarter.
- **"Sell faster" vs "Sell higher" toggle** — per-item mode. Affects pricing band position (bottom vs top third of comps).
- **Markdown schedule automation** — auto price-drop rules (e.g. -10% after 14 days, -20% after 30).
- **Profit/ROI per item** — show on stats page. Requires buy price input.
- **Brand performance breakdown** — which brands sell best and fastest, over time.
- **Search and filter in draft bank** — filter by brand, category, age, status.

---

## Marketing Ideas

How people discover, share, and talk about Dodis.

- **Referral mechanic** — "Invite a friend, both get 50 free listings." Duolingo-style virality.
- **Public seller profile** — optional shareable page showing your listed items. Like a mini-shop link.
- **"Listed with Dodis" watermark option** — subtle brand presence on listing photos (opt-in).
- **Seller leaderboard** — needs community scale first. Park until post-launch.

---

## Assistant Ideas

How the AI assistant gets smarter and more useful over time.

- **Correction learning** — feed manual corrections back into extraction prompts as examples. Self-improving per operator.
- **Per-brand extraction hints** — store known brand quirks (e.g. "Barbour sizes run large") and inject as context.
- **Confidence explanation** — tell the operator *why* a field is low confidence, not just that it is.
- **Cross-item learning** — if the same brand/type has been corrected 5+ times in the same way, apply it automatically going forward.

---

## UI / Design Ideas

Visual and interaction improvements.

- **Mobile PWA install experience** — home screen prompt, splash screen, iOS icon.
- **Camera → listing flow** — take/pick photos in-app, skip the folder system. For casual sellers.
- **Widget / home screen shortcut** — iOS widget showing items listed this week, potential earnings.
- **Gamified seller rank** — Iron → Gold → Flame tier. Could feel gimmicky — needs the right execution.

---

## Platform Ideas

Expanding beyond Vinted.

- **eBay draft creation** — same extraction, eBay-specific template. Playwright on eBay sell flow.
- **Depop integration** — younger audience, higher streetwear margins. Different listing format.
- **"Post to all" mode** — one extraction, three platform drafts simultaneously.
- **Cross-platform dashboard** — all platforms, one view.
- **Telegram/push alerts on item sold** — instant notification when something sells.

---

## Parking Lot

Ruled out or deprioritised. Kept for reference.

- **Vinted messaging automation** — likely violates ToS. Do not pursue.
- **Auto-publish without review** — too risky for pricing and quality. Explicit non-goal.
- **Facebook Marketplace** — low resale value audience, not worth integration effort.
- **Seller leaderboard** — needs community scale that doesn't exist yet.

---

## Graduated to Roadmap

- eBay comp fetch (on-demand) → shipped
- Listing performance tracker → shipped
- Condition + flaws service → shipped
- Price memory → shipped
- Draft failure recovery + screenshot capture → in roadmap (pre-beta)
