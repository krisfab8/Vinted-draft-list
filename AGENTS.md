# Vinted App AI Working Context

This file is intended to be placed in the root of the Vinted app repo, ideally as `AGENTS.md` or `docs/AI_WORKING_CONTEXT.md`.

Use it when asking Codex, Claude Code, or ChatGPT to audit, improve, or redesign the Vinted draft listing app.

## Project Identity

- Project: Vinted Draft Listing App
- GitHub repo: https://github.com/krisfab8/Vinted-draft-list
- Main goal: automate creation of high-quality Vinted draft listings so the seller focuses on sourcing, review, and manual publishing.
- Primary user: UK clothing reseller, mostly quality men’s clothing from charity shops and car boot sales.
- Target economics: buy around £5–£15, sell around £25–£120, protect profit and avoid low-margin listings.
- Core UX principle: the app should feel like a fast review cockpit, not a generic admin dashboard.

## Current Repo / App Understanding

Known project stack and architecture from previous work:

- Backend appears Python/Flask-style with routes such as:
  - `POST /upload`
  - `POST /create-listing`
  - `POST /create-draft`
  - `POST /edit-draft`
  - `POST /regen`
  - `POST /reprice`
  - `PATCH /listing`
  - `GET /api/listings/review-queue`
  - `GET /auth/status`
- Core data source:
  - `listing.json` is the practical source of truth for an item.
- Important files/modules previously discussed:
  - `app/extractor.py`
  - `app/listing_writer.py`
  - `app/draft_creator.py`
  - `app/services/pipeline.py`
  - `app/services/item_store.py`
  - `app/services/pricing.py`
  - `app/services/ebay_comps.py`
  - `app/run_logger.py`
  - `review.html`
  - `auth_state.json`
  - `data/run_logs.jsonl`
  - `data/corrections.jsonl`
  - `data/price_memory.json`

## Existing Functional Priorities

The app should preserve and improve:

- Upload clothing photos.
- Extract item details: brand, sub-brand, category, item type, material, size, condition, flaws.
- Write Vinted-ready title, description, tags, and pricing.
- Apply deterministic pricing/profit checks after AI output.
- Save listing state into `listing.json`.
- Create or edit Vinted drafts through Playwright.
- Use Playwright `storage_state` via `auth_state.json`, not fragile raw cookies.
- Detect expired/missing Vinted auth and return `VINTED_AUTH_EXPIRED`.
- Show draft errors clearly in the UI.
- Maintain a review queue based on warnings, confidence, draft state, and error tags.

## Key State Fields

When auditing or implementing UI, preserve meaning of these fields:

- `draft_url`: draft was successfully created.
- `draft_error`: last draft creation/edit failure.
- `warnings[]`: AI or deterministic warnings.
- `error_tags[]`: operator-facing issue taxonomy.
- `brand_confidence`: usually `high`, `medium`, or `low`.
- `material_confidence`: usually `high`, `medium`, or `low`.
- `confidence`: overall confidence float.
- `low_confidence_fields[]`: fields requiring human review.
- `category_locked`: user intentionally locked category choice.
- `price_gbp`: listing price.
- `buy_price_gbp`: item purchase price.
- `estimated_profit_gbp`: estimated profit after assumptions.
- `profit_multiple`: profitability category/ratio.
- `ebay_comps`: optional eBay comparison data.
- `ebay_suggested_range`: optional suggested Vinted range from eBay comps.
- `ebay_suggested_price`: optional suggested price, should not overwrite `price_gbp` without user action.

## Pricing Rules Context

Pricing is not only an AI prompt problem. It should be handled as AI + deterministic rules.

Known pricing logic:

- `pricing.apply_pricing(listing)` runs after LLM listing generation.
- Uses memory bands from `data/price_memory.json`.
- Uses condition percentile mapping from `condition_summary`.
- Applies flaws discount, e.g. around -15% when `flaws_note` exists.
- Clamps to memory band high when memory confidence is medium/high.
- Avoid relying only on a “3x buy price” rule.
- Use profitability warning flags:
  - low margin when estimated profit or multiple is too weak.
  - thin margin when close to the minimum useful return.
- Vinted fee assumption previously used:
  - estimated profit = `price * 0.95 - 0.70 - buy_price`

## UX Priorities

The frontend should help the user review and correct listings quickly.

The main UI should answer:

- What needs review?
- Why does it need review?
- What is the likely fix?
- Is it worth listing?
- Has a Vinted draft been created?
- If draft creation failed, what exactly failed?
- What action should I take next?

Avoid:

- Generic admin tables.
- Grey, lifeless SaaS dashboards.
- Hiding confidence/warnings in raw JSON.
- Making the user open each listing just to know what is wrong.
- Overwriting user-edited fields during regenerate/reprice flows.

Prefer:

- A card/grid review queue.
- Visual status chips.
- Confidence badges.
- Clear profit badges.
- Fast action buttons.
- Side-by-side before/after for regenerated fields.
- Inline field locking.
- One-click category fixes where deterministic conflict detection is possible.

## Design Direction

The visual identity should feel like:

- A premium reseller’s listing cockpit.
- Fast, confident, tactile, and practical.
- More “curated stockroom / thrift intelligence” than corporate SaaS.
- Inspired by Vinted/eBay selling workflows, but not a clone.
- Mobile-first enough to work well when sourcing or photographing items.

Possible visual language:

- Warm off-white or parchment background.
- Deep ink/charcoal text.
- Muted green for ready/profit/success.
- Amber for review/warnings.
- Red only for blocking errors.
- Subtle paper/card textures or resale-tag styling.
- Strong product-photo-first layouts.
- Rounded cards, crisp shadows, and readable spacing.

## Important Frontend Surfaces To Improve

Focus frontend/UI work on these first:

1. Review Queue
   - Prioritise items needing user action.
   - Filter by status: Needs review, Ready, Draft created, Draft failed, Low confidence, Low margin.
   - Show image, title, price, profit, confidence, warnings, and next action.

2. Item Review Page
   - Product photos prominent.
   - Editable listing fields grouped logically.
   - AI confidence and warnings near relevant fields.
   - Price explanation visible but compact.
   - Draft creation state obvious.
   - Field locks respected.

3. Pricing Panel
   - Show current price, suggested price, eBay range if available, estimated profit, and risk.
   - Explain why a price changed.
   - Never silently overwrite user price.
   - Let user accept suggested price explicitly.

4. Draft/Auth Status
   - Global Vinted connection indicator.
   - Clear `/connect` flow.
   - Specific error for expired session.
   - Draft failure message visible on the item card and review page.

5. Upload Flow
   - Mobile-friendly photo upload.
   - Allow camera and photo library.
   - Clear photo count/quality warnings.
   - Show progress without feeling technical.

## Code Quality Rules For Agents

When Codex or Claude edits the app:

- Read relevant files before editing.
- Reuse existing helpers and patterns.
- Do not duplicate pipeline logic across routes.
- Preserve response shapes unless intentionally changing API.
- Add or update tests when changing behavior.
- Do not add broad silent exception handling.
- Do not overwrite user edits during regenerate/reprice.
- Do not revert unrelated user changes.
- Use deterministic code for business rules where possible.
- Keep AI prompts smaller and specific; move stable rules into code/config where possible.
- Prefer small, complete vertical improvements over huge unfinished refactors.

## Suggested Agent Prompt Pattern

Use this when asking Codex or Claude to work on the repo:

```text
You are working in my Vinted Draft Listing App repo.

First read `AGENTS.md`, then inspect the relevant files before editing. Treat `listing.json` as the practical item source of truth. Preserve existing route response shapes unless a change is clearly necessary.

Task:
[describe the exact UI/code task]

Important constraints:
- Prioritise working code over a plan.
- Preserve user-edited listing fields during regen/reprice.
- Surface confidence, warnings, draft errors, and profit flags clearly.
- Add or update tests if behaviour changes.
- Do not overwrite unrelated changes.

Deliver:
- Implement the change.
- Run the narrowest relevant tests/checks available.
- Summarise changed files and any risks.
```

## Audit Prompt Pattern

```text
Audit the Vinted app frontend/UI using `AGENTS.md` as context.

Focus on:
- Review queue clarity
- Item review speed
- Pricing/profit visibility
- Confidence/warning visibility
- Draft/auth error visibility
- Mobile upload/review flow
- Design quality and visual hierarchy

Return findings first, ordered by severity. Include file references. Then propose a compact implementation plan with the smallest useful first patch.
```

## Frontend Redesign Prompt Pattern

```text
Improve the Vinted app frontend using `AGENTS.md` and `docs/FRONTEND_DESIGN_BRIEF.md`.

Goal:
Make it feel like a polished reseller review cockpit, not a generic admin dashboard.

Scope:
[route/component/page]

Requirements:
- Product-photo-first layout.
- Clear status chips for draft/auth/review states.
- Price/profit panel with warning states.
- Confidence badges near the fields they refer to.
- Mobile-friendly layout.
- Preserve current backend behaviour.
- Avoid generic purple SaaS styling.
- Use existing stack and conventions.

Implement the design, wire it to existing data, and run relevant checks.
```
