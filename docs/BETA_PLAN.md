# Dodis — Beta Execution Plan

## What beta means

5–10 real sellers using Dodis without help. The pipeline completes reliably. Pricing is defensible. A first-time user can list an item without asking a question.

**Exit criteria:**
- Pipeline success rate >90%
- Draft creation success on first attempt >85%
- Fields needing manual correction <2 per item average
- Price accepted without change >70% of items
- User would recommend: >7/10

---

## 1. Must Do Before Beta

Ordered by dependency. Work top to bottom.

### 1.1 Draft failure recovery `~1 day`
The single biggest risk. If a draft fails silently, the operator has no idea what happened.

- On any Playwright failure: set item status to `draft_failed`
- Log the step that failed + error type in run log
- Show a clear retry button in the UI (draft bank + review page)
- No silent swallowing of errors — failure must always be visible

### 1.2 Screenshot capture on Playwright failure `~half day`
Partially in place. Needs to be consistent across all failure paths.

- Any unhandled Playwright exception → screenshot to `debug_screenshots/<folder>_<timestamp>.png`
- Write screenshot path into the run log entry
- Operator should be able to see exactly what the browser saw when it failed

### 1.3 1-retry strategy for transient failures `~half day`
- 1 automatic retry on transient failures (network, element not found on first poll)
- No retry on `VintedAuthError` — prompt reconnect immediately
- No retry on validation failures — needs operator input
- Max 1 retry to prevent silent duplicate drafts

### 1.4 Auth reconnect flow hardened `~half day`
Vinted sessions expire. This must be seamless for beta users.

- Reconnect banner visible and obvious when session expires
- `/auth/status` returns clear state (likely / expired / missing)
- Reconnect flow takes operator back to where they were, not to home

### 1.5 Apply Dodis design system to all pages `~2–3 days`
Upload page is done. Drafts, review, and stats pages still look like an internal tool. Beta users will judge the product by how it looks.

- Drafts page: Dodis colours, card layout, status indicators
- Review page: cleaner field layout, warnings less alarming, Dodis brand visible
- Stats page: summary cards, Dodis palette, something useful after 5 items
- Base template: consistent header, nav, typography

### 1.6 Validation errors are human-readable `~half day`
Schema errors currently surface as technical messages. Beta users will not understand them.

- Map schema error codes to plain English
- Show next to the relevant field in review, not as a raw JSON dump
- "Brand is required" not "required property 'brand' missing"

### 1.7 Mobile upload works reliably `~half day`
Already fixed (`capture="environment"` removed). Needs a smoke test on a real device before beta.

- Test on iOS Safari (home screen PWA install)
- Test on Android Chrome
- Confirm photos attach and pipeline runs end-to-end

### 1.8 Draft failure rate visible on stats page `~half day`
Operators need to know if Playwright is degrading over time.

- Add `draft_failed` count to stats page
- Show success rate (e.g. "47 of 50 drafts succeeded")
- Pull from run logs — no new data store needed

---

**Must-do total: ~6–7 days of focused work**

---

## 2. Nice to Have Before Beta

These improve the experience meaningfully but do not block launch. Do them if time allows before onboarding the first tester.

### 2.1 "Why this price?" in review UI `~1 day`
One sentence explaining the price: "£28 based on Ralph Lauren polo eBay comps (avg £32 sold)."
Builds trust. Reduces the number of times operators second-guess the price.

### 2.2 eBay comps shown inline on review page `~half day`
Already fetchable on-demand. Just needs to surface automatically in the review UI rather than requiring a manual fetch.

### 2.3 Pricing confidence indicator `~half day`
High / medium / low next to the price field. Low confidence → operator prompted to check.

### 2.4 Review page warnings as inline suggestions `~1 day`
Replace warning banners with field-level nudges: "Did you mean: Barbour?" next to the brand field. Less alarming, more actionable.

### 2.5 Mobile PWA install prompt `~half day`
Add a `manifest.json` and iOS meta tags so the app installs cleanly to the home screen with the Dodis icon and splash screen.

### 2.6 Centralise category mapping `~1 day`
There is duplication between extractor and listing writer. Not user-facing but reduces a class of subtle bugs before external users hit edge cases.

---

**Nice-to-have total: ~4–5 days**

---

## 3. Beta-Phase Tasks

Things to do *while* beta is running, in response to what testers surface.

### 3.1 Run the feedback loop per tester session
For each session:
1. Observe or record the first listing flow — where did they hesitate?
2. Check corrections log for what they manually changed
3. Check run logs for extraction failures or low-confidence fields
4. Ask: "Would you use this instead of listing manually? Why / why not?"
5. Note the one thing that would make them use it every time

### 3.2 Track and triage extraction errors
- Which fields are being corrected most? (brand, size, material, category?)
- Any consistent failure patterns by item type or brand?
- Feed findings back into extraction prompts or confidence thresholds

### 3.3 Triage draft creation failures
- Is the failure rate staying under 15%?
- Are failures concentrated on a particular Playwright step?
- If Vinted changes their UI: isolate, patch `draft_creator.py`, test

### 3.4 Pricing calibration
- Are prices being accepted or consistently adjusted?
- Which brand/item types are weakest?
- Update `price_memory.json` and pricing tiers based on real corrections

### 3.5 Onboarding walkthrough (if confusion persists) `~1–2 days`
If beta testers repeatedly get stuck at the same step, add a 3-step guided walkthrough for first-time use. Only build this if the data says it's needed.

### 3.6 Streak / items counter on stats page `~half day`
Low effort, high motivation. "You've listed 14 items this week." Shows value accumulation. Add once enough testers are active to make it feel real.

---

## 4. Post-Beta Vision

Do not let these delay beta. Lock scope hard.

### 4.1 Batch upload
Multiple items queued, extracted in parallel, reviewed in sequence. The biggest productivity unlock for resellers. Needs the core loop to be stable first.

### 4.2 Markdown schedule automation
Auto price-drop rules (e.g. −10% after 14 days, −20% after 30). Already partially scoped. High commercial value for resellers.

### 4.3 Correction learning
Feed manual corrections back as extraction examples. Self-improving per operator. Meaningful accuracy gain over time.

### 4.4 eBay listing creation
Same extraction, eBay-specific template. Playwright on eBay sell flow. Doubles reach without doubling listing effort.

### 4.5 Mobile-first camera flow
Take/pick photos in-app, skip the folder system. Required for the casual seller at scale. Probably a React Native or PWA camera integration.

### 4.6 Depop integration
Younger audience, higher streetwear margins. Different listing format but same extraction pipeline.

### 4.7 Cross-platform dashboard
All platforms, one view. Meaningful only once 2+ platforms are live.

---

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|-----------|
| Vinted changes their UI mid-beta | Medium | `draft_creator.py` is isolated; monitor and patch fast |
| Session expiry frustrates testers | High | Auth reconnect flow (item 1.4) must be airtight |
| Prices feel wrong to testers | Medium | "Why this price?" + eBay comps inline (items 2.1–2.2) |
| Extraction wrong on unusual items | Medium | Review routing catches low-confidence; escalation to Sonnet |
| Testers confused by the UI | Medium | Dodis design (item 1.5); onboarding only if needed (3.5) |

---

## Recruiting

- Personal network first — clothing sellers, eBay/Vinted users we know
- Reddit: r/VintedUK, r/Flipping, r/UKfashion
- Twitter/X reseller community
- Do not advertise publicly until 1.0 is stable

Target mix: 2–3 casual sellers, 2–3 part-time resellers, 1–2 power resellers.
