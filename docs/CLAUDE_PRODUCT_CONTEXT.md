# Dodis — Product Context for Claude

## What is Dodis?

Dodis is an AI selling assistant for clothes. The name reads as an imperative: "Do this" — fast, confident, action-oriented. It automates the hardest parts of selling second-hand clothing: photo reading, listing writing, pricing, and platform publishing.

The flame on the "i" is the brand mark. The assistant *ignites* action.

---

## Who is it for?

**Two user types, one product:**

### Casual seller
- Clears out their wardrobe a few times a year
- Finds listing clothes tedious and time-consuming
- Doesn't know what to price things at
- Wants a one-tap shortcut from photo to live listing

### Reseller / operator
- Buys to sell — charity shops, car boots, online arbitrage
- Lists 10–100+ items per week
- Cares about pricing margin, not just getting it live
- Needs speed, batch workflows, and performance tracking

Dodis serves both. Casual sellers get magic. Resellers get a system.

---

## Core Job To Be Done

> "I have clothes I want to sell. Make it as fast and painless as possible, and make sure I don't leave money on the table."

---

## Product Philosophy

Inspired by:
- **Duolingo** — habit loops, streaks, progress feedback, celebration moments
- **Apple** — minimal UI, obvious actions, no clutter
- **Spotify** — personalisation that gets smarter over time, feels like it knows you
- **Strava** — tracking your activity, seeing progress, sharing milestones

Dodis is not a tool. It's an assistant with personality. The flame is alive.

---

## The Assistant Concept

The AI isn't hidden. It's the product. Dodis:
- reads your photos so you don't have to fill in a form
- writes the listing in the right tone for the platform
- prices based on market comps, brand, condition, and memory
- routes uncertain items to review, not to failure
- learns from your corrections over time

The assistant should feel like a knowledgeable friend who is also very fast.

---

## Current Platform

- **Vinted** is the primary target (UK + EU resale market)
- Playwright automation handles draft creation
- Flask web app is the operator interface
- Google Sheets for tracking and analytics
- Local JSON price memory + run logs

---

## Future Vision

- Cross-listing: same item published to eBay, Depop, Vinted simultaneously
- Mobile-first: PWA or native app, camera → listing in one flow
- Pricing intelligence: eBay sold comps, Vinted live search
- Social/community: share wins, streaks, seller leaderboards
- Subscription tiers: casual (free, limited) / reseller (paid, unlimited + analytics)

---

## Brand

- Name: **Dodis**
- Wordmark: Plus Jakarta Sans 800, "Do" in red `#C41E1E`, "is" in white
- Flame: E3 gradient `#AA1515 → #EE2222 → #FFE0C0` on the dotless i
- Icon: White D on red circle, flame visible through D counter (Negative D concept)
- Tone: Direct, confident, slightly playful. Never corporate.

---

## What Claude Should Know

- This is a real operational product, not a demo
- The operator workflow must stay fast and reliable
- Pricing is commercially important — not decorative
- The brand identity (Dodis, flame, colour system) is being actively developed alongside the product
- The codebase is beyond MVP and in active hardening
- Trust the CLAUDE.md file for engineering rules
