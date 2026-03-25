# Dodis — Beta Plan

## Goal

Get Dodis into the hands of 5–10 real sellers, gather feedback, and validate the core loop before any public launch.

---

## Beta definition

A successful beta means:
- A new user can list their first item without help from us
- The pipeline completes without errors in >90% of runs
- Pricing is defensible (seller agrees it's fair or adjusts it within 20%)
- Draft creation works on first attempt in >85% of runs

---

## Beta user profiles

### Target testers
1. **Casual wardrobe clearer** — lists 5–20 items total, not a regular seller
2. **Part-time reseller** — lists 20–100 items/month, cares about margin
3. **Power reseller** — 100+ items/month, needs speed and batch flow

### How to recruit
- Personal network first (clothing sellers, eBay/Vinted users we know)
- Reddit (r/UKfashion, r/VintedUK, r/Flipping)
- Twitter/X reseller community
- Do not advertise publicly until 1.0

---

## Pre-beta checklist

### Must have
- [ ] Dodis brand applied to all operator-facing pages
- [ ] Mobile upload works reliably (no capture bug)
- [ ] Review page is clear and usable by non-technical users
- [ ] Draft creation success rate >85%
- [ ] Validation errors show human-readable messages
- [ ] Auth reconnect flow works (Vinted session expiry)

### Nice to have
- [ ] Onboarding tooltip or walkthrough
- [ ] Stats page shows something useful after 5+ items
- [ ] Price explanation visible in review

---

## Beta feedback loop

For each tester session:
1. Observe or record the first listing flow
2. Note: where did they hesitate? What confused them?
3. Check run logs for extraction issues
4. Check corrections log for what they changed
5. Ask: "Would you use this instead of listing manually? Why / why not?"

Key questions:
- Did the extraction get the brand, size, and material right?
- Was the price reasonable?
- Did the draft create successfully?
- What would make you use this every time?

---

## Beta success metrics

| Metric | Target |
|--------|--------|
| Pipeline success rate | >90% |
| Draft creation success | >85% |
| Fields requiring manual correction | <2 per item |
| User would recommend | >7/10 |
| Price accepted without change | >70% of items |

---

## Known risks going into beta

| Risk | Mitigation |
|------|-----------|
| Vinted auth expires mid-session | Reconnect banner + clear error message |
| Wrong category assigned | Review routing catches low-confidence |
| Extraction fails on unusual tags | Reread logic + escalation to Sonnet |
| Playwright breaks on Vinted UI change | Monitor; draft_creator.py is isolated |
| Price too low on premium brands | Brand tiers in pricing; eBay comps available |

---

## Timeline (indicative)

| Milestone | When |
|-----------|------|
| Internal dogfooding complete | Now |
| Dodis design applied to all pages | Next sprint |
| First 3 beta testers onboarded | After design |
| Beta feedback synthesised | 2 weeks after |
| 1.0 scope locked | After feedback |
