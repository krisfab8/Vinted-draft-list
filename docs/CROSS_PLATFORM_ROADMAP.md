# Dodis: from Vinted review tool to multi-platform clothing listing app

Updated 2 October 2026. Product direction, not a claim that future integrations exist. Implementation status lives in `TASK_TRACKER.md`.

## Product promise

Photograph an item once, confirm what the app found, then prepare accurate platform-specific listings from one inventory record. Sellers retain control of descriptions, price and publication. The app should save time without producing unsupported brand/material claims or selling the same garment twice.

Start with UK clothing resellers. Maintain a useful casual-seller path. Kristian's existing workflow and heritage/outdoor/tailoring items are the first test set; the eventual product must also work for everyday brands and missing labels.

## What newer models help with

Models can read labels, identify visible garment attributes, draft short copy and propose mappings. Their capability does not grant marketplace API access or remove seller onboarding, category requirements, delivery policies, fee accounting and inventory reconciliation. Those are engineering and product work.

Choose routine models from measured accuracy/cost, rather than choosing a development model as the runtime default. Luna is the current candidate; Haiku is the baseline. Sol is a possible targeted difficult-case model. These remain hypotheses until tested on our photos.

## One inventory record, several platform listings

Keep platform-neutral evidence separate from platform-specific presentation.

| Shared inventory | Evidence/provenance | Per-platform record |
|---|---|---|
| Stable item ID/SKU; owner; quantity; purchase cost | Original images; readable label text; model/prompt/preprocessing version | Seller account; listing/offer ID; state; last sync |
| Confirmed brand, model, size, fibres, colour, flaws | Field confidence; user confirmation; correction history | Category and item specifics; platform condition |
| Photo roles; measurements; item state | Price-source date; asking/sold distinction | Title/description; asking price; delivery/return policies |
| Reserved/sold status | Actual transaction amount/source and sale time | Platform fees; publication timestamps; errors |

For the existing single-user app, listing.json remains authoritative until a planned migration. Multi-user ownership and cross-platform state require a transactional shared store, not several loosely synchronized copies of that file.

Platform adapters translate a confirmed item into requirements for a specific marketplace. A correction to a material should not overwrite an approved platform title unless the seller accepts regeneration. Store generation versions and show changes.

## Phase 1: private review and model test

Deliver: a private HTTPS test surface for uploads, extraction and editing, with Luna available for both extraction and writing, real spend observations, clear unsupported browser actions and persistence.

Acceptance: Kristian can upload phone photos, correct fields, reload/restart without losing state, see exact selected models and compare against ground truth. Reliability findings and cost limits must be resolved before treating it as a beta for other sellers.

Private single-operator password access is a test gate. It is not multi-user authentication, account isolation or a customer-ready product.

## Phase 2: reliable Vinted workflow and unit economics

Resolve false draft success, correction loss, invalid edits, buyer-fee accounting and complete usage tracking. Preserve crop originals and handle orientation/roles. Make uncertain extraction visible. Confirm local browser flow on today's Vinted form; decide a supported remote approach separately.

Measure total billed API/data cost per successful item, including failed attempts and retries, alongside accuracy, correction time and processing time. Report average and high-percentile costs. A sub-penny target does not include free server hosting; hosting, storage and support have their own economics.

## Phase 3: eBay listing preparation and publication

Price research via Browse is already separate from selling. eBay selling needs seller OAuth user tokens; an application token used for comps does not authorize publishing for a seller.

Use the official Inventory API path, subject to account/API eligibility:

1. Register the developer application and configure seller authorization with a safe callback. Distinguish sandbox and production credentials/tokens.
2. Confirm seller account readiness, business policies, inventory location and supported marketplaces.
3. Map the item into a stable SKU, category, item specifics, condition and images. Review missing required data instead of inventing it.
4. Create or replace the inventory item and create an **unpublished offer**. Persist SKU/offer identity and operation status.
5. Preview platform title, description, price, seller proceeds, delivery/returns and required fields.
6. Publish only after explicit seller action; persist listing ID and reconcile uncertain outcomes before retrying.
7. Track offer/listing state and orders using supported APIs; handle token expiry/revocation and platform errors visibly.

Begin with fixed-price, single-quantity UK clothing. Auctions, variants, international shipping and bulk operations come later. Creating an unpublished Inventory API offer is not the same as proving it appears as a draft in every eBay UI; verify actual behavior.

Acceptance: sandbox flow first, then one explicitly authorized production item with correct photos/fields/policies and no duplicate on retry. Confirm actual fee assumptions for seller account type and category, rather than reusing Vinted's profit formula.

Official references: [Inventory overview](https://developer.ebay.com/api-docs/sell/inventory/overview.html), [inventory item to offer flow](https://developer.ebay.com/api-docs/sell/static/inventory/inventory-item-to-offer.html), [authorization](https://developer.ebay.com/develop/guides/sell/authorization).

## Phase 4: safe cross-listing

Do not open simultaneous sales on several platforms until one shared quantity/state and reconciliation work.

Required behavior: reserve item on confirmed sale/order, prevent new publication, withdraw other live listings, retry safely, surface failed withdrawal and reconcile conflicting updates. Confirm what event really constitutes a sale on each platform. Platform delays mean absolute zero-oversell claims are inappropriate; design recovery and operator alerts.

Acceptance: a simulated and then controlled real sale causes other listings to be withdrawn or a clear unresolved-action alert. Expired tokens and an unreachable platform must not look successfully synchronized.

## Phase 5: more platforms, then invited beta

Add a platform only after verifying official API availability, account eligibility, authorized integration rules, category/fee requirements and operational support. Start with copyable listing/export packs when automated publication is unavailable. Label the manual step clearly.

Before 5–10 invited sellers: independent identities and items; isolated OAuth/auth sessions and pricing/correction memory; quotas and cost controls; privacy notice, consent, retention/deletion, backups and restore; measured onboarding and support. Choose shared infrastructure when a single disk/process no longer fits.

## Sustainable low-cost strategy

- Extract evidence once; reuse it across platform adapters.
- Cache by original-image hash, model, prompt/schema/preprocessing version and relevant hints.
- Use deterministic mappings, fee arithmetic, state transitions and validation.
- Retry only a failed field/label; escalate only with a recorded budget reason.
- Keep platform copy concise and return uncertain evidence to the seller.
- Retrieve eBay comps through the direct API, with relevance filters and reasonable caching.
- Keep asking prices, sold prices and seller-specific fees separate.
- Track costs per stage, successful listing, seller and month; enforce quotas before inviting users.

## Decisions still needed after testing

1. Does Luna meet accuracy/correction thresholds, or should some labels stay on Haiku/Sol?
2. Is the first audience primarily casual sellers or volume resellers? Validate with the small beta.
3. Is Vinted automation support worth its maintenance burden relative to export/review + eBay API publication?
4. Which hosting/data architecture meets measured usage, isolation and recovery needs?
5. What pricing model covers hosting/support and data/API costs at real seller usage?

Avoid building billing, every marketplace and automatic repricing before these measurements. The first expansion is a reliable eBay flow built on confirmed item evidence.
