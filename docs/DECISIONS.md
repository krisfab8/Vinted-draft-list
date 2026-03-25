# Dodis — Product Decisions Log

Record of meaningful choices made about the product, brand, and system.
Newest first. Each entry: what was decided, why, and what was ruled out.

---

## 2026-03-25 — Logo: Plus Jakarta Sans 800 as wordmark font

**Decided:** Plus Jakarta Sans 800 is the Dodis wordmark font.

**Why:** Tried 18+ fonts across 4 rounds. Others were rejected for:
- Fraunces: too Forbes / editorial
- Syne, Raleway, Cormorant: too fashion-magazine
- Unbounded, Anton, Orbitron: too tech/esports
- Josefin, Cinzel: too geometric/cold
- Teko, Kanit, Exo 2: too condensed/industrial
- Poppins, Nunito, Baloo 2: too rounded/playful (lost confidence)

Plus Jakarta Sans 800 hits the right balance: confident, modern, slightly rounded without being childish. Pairs well with the flame.

**Ruled out:** Animated flame, gradient on letters (only the flame uses gradient).

---

## 2026-03-25 — Wordmark: "Do" red, "is" white, no letter gradients

**Decided:** "Do" = solid `#C41E1E`, "is" = solid white. Flame is the only gradient element.

**Why:** Gradient letters felt cheap and hard to read. Solid red/white split creates clear two-word read: "Do" + "dis" = "Dodis". The flame does the expressive work.

**Ruled out:** Gradient on letters, teal for "dis", black wordmark.

---

## 2026-03-25 — Icon: Negative D on red circle

**Decided:** Primary app icon is a white D (evenodd cutout) on a red circle, with the E3 flame showing through the D's counter.

**Why:** Among 6 concepts explored (D Blaze, Hanger Hook, Pure Fire, Price Tag Flame, Photo Flash, Negative D), Negative D was the strongest because:
- Instantly reads as "D" for Dodis
- Flame visible through the cutout = personality without kitsch
- Simple at small sizes
- Red circle works at any scale

**Ruled out:** Hanger icon (too generic), animated flame icon, letter-less fire mark.

---

## 2026-03-25 — Flame: E3 gradient, SVG bezier path, no animation

**Decided:** Flame is a static SVG bezier path with E3 gradient (`#AA1515 → #EE2222 → #FFE0C0`, bottom-to-top). No CSS animation.

**Why:** Animated flame was tried and rejected as "fake". The bezier path reads as a real flame shape. Animation would be distracting in a UI context and hard to control across sizes.

**Ruled out:** CSS clip-path flame, emoji flame, candle with wax, glowing dot.

---

## 2026-03-25 — App name: Dodis

**Decided:** The product is called Dodis.

**Why:** Reads as "Do this" — a direct command, which matches the product's job (take action, list the item). Polish pronunciation is "Do-dis". The two-word read ("Do" + "dis") enables the red/white split in the wordmark and the visual identity.

**Ruled out:** Working title "Vinted Draft List" (too literal, not brandable).

---

## 2026-03 — Pricing philosophy: market-first, no hard buy-price floor

**Decided:** Pricing is anchored to market band (find brand/type comps, position within band by condition percentile). Buy price is analytics only — not a hard floor.

**Why:** A floor would cause underpricing for strong brands and overpricing for weak ones. Market-first gets the right price regardless of what was paid.

**Ruled out:** Cost-plus pricing, fixed markup %, eBay race-to-bottom pricing.

---

## 2026-03 — Condition: auto-downgrade from flaws note

**Decided:** The condition service auto-downgrades condition based on keywords in the flaws note (e.g. "stain" → Good, "hole" → Satisfactory). New items bypass downgrade.

**Why:** Operators often forget to adjust condition when adding a flaw note. Auto-downgrade prevents over-grading. Operator can still override.

**Ruled out:** Manual-only condition, AI-inferred condition from photos (too unreliable).

---

## 2026-03 — Vision model: Claude Haiku 4.5 default, Sonnet escalation

**Decided:** Use Claude Haiku 4.5 for all extraction. Escalate to Sonnet if confidence < 0.7.

**Why:** Haiku is ~10× cheaper than Sonnet. Most items have clear tags and photos. Escalation catches the hard cases without burning cost on every item.

**Ruled out:** GPT-4o (more expensive, no meaningful accuracy gain for tag reading), Gemini only (kept as fallback not primary).

---

## 2026-03 — Draft creation: no auto-publish

**Decided:** Dodis always creates a *draft* on Vinted, never publishes directly.

**Why:** Operator must review price, photos, and description before going live. Auto-publish is too risky — a wrong price or bad photo goes live instantly with no chance to catch it.

**Ruled out:** Auto-publish mode, "publish immediately" toggle.

---

## 2026-03 — State: folder-based items, local JSON

**Decided:** Items are stored as folders in `items/`. State is local JSON (listing.json, price_memory.json, run_logs.jsonl).

**Why:** Simple, inspectable, no database dependency for v0. Easy to back up and version.

**When to revisit:** When multi-user or cloud access is needed. Move to SQLite or Postgres at that point.

---

## 2026-03 — Review routing: low-confidence fields trigger review page

**Decided:** Items with low-confidence fields (brand, material, size, category) are routed to the review page before draft creation.

**Why:** Better to catch uncertainty explicitly than silently create a bad listing. The review page lets operators correct specific fields without re-running the full pipeline.

**Ruled out:** Always-on review (too slow), skip review entirely (too many errors).
