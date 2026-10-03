# Quality, cost and eBay research — 3 October 2026

Working branch: `work/vinted-quality-market`, based on deployed
`5c0e53d2a226185f80c93ac75cb8497aace04287`.
Original `vinted-private-test` service remains unchanged. After verification the
phone test service follows the same tested commit through its deployment branch.

## Implemented

- Compact writing excludes uncertain pattern, secondary colour, model and tag
  evidence; a deterministic check removes uncertain pattern claims even when
  the writer ignores the instruction. Review fields/warnings remain available.
- Known size and high-confidence material percentages are preserved in buyer
  copy even if the writer omits them. The supplied condition grade is retained.
- Condition appears once in buyer-facing copy. Mixed condition/product
  paragraphs retain the product sentence. Storage causes and absolute absence
  of holes/tears/stains are not inferred in generated condition summaries.
- Haiku extraction caches the exact unchanged static instructions before the
  item-specific hints/images. Same OCR model, image resolutions and label
  rules. Five-minute cache hits are cheaper; first writes have a premium;
  expiry/short prefixes do not produce a hit. Actual cache token usage is
  recorded. Rollback: `ENABLE_PROMPT_CACHE=0`.
- eBay uses confirmed brand/type/size and high-confidence model names, plus
  useful materials including percentage-prefixed compositions. Strict title
  matching excludes other brands/sizes and repair/lots. Unknown size/model
  narrows neither search nor matching. UK used fixed-price candidates only.
- A 24-hour cache stores credential-free comparison summaries. Mean/median,
  sample counts, representative links, known/unknown postage and timestamps
  are shown. Asking prices remain separate from sold prices; listing price is
  never overwritten. Insufficient results stay unavailable.
- Phone UI exposes matching active/sold/Product Research links, on-demand
  API comparisons, and seller-entered research counts/average sold price.
  Automatic Browse calls need `EBAY_APP_ID` and `EBAY_CERT_ID` in hosting.
- Manual research records a 1–90 day sold period. Sales ÷ current active ×100
  is a demand proxy (can exceed 100%). Active ÷ sold and sold ÷ (sold+active)
  are also recorded. These are not a verified cohort sell-through rate or an
  automatically fetched eBay Product Research metric. Zero denominators stay
  unknown; invalid/non-finite/negative inputs are rejected.
- Private export/restore backs up saved upload folders/photos/accounting,
  excludes auth/configuration, validates paths/files/listings, bounds archive
  size and refuses overwriting seller edits. Export link is available after
  generation. Restore itself is protected by the hosted app's password gate.

## Cost target and draft boundary

Goal: £0.005–£0.01 AI cost per verified Vinted draft, including rereads and
failed/repeated attempts. Hosting and marketplace charges must be tracked
separately; the current UI reports estimated generation cost, not complete
end-to-end cost per successfully saved marketplace draft.

The morning leggings run cost £0.013494 across two Haiku calls. Prompt caching
can reduce the repeated instruction component without changing OCR quality,
but 0.5p is not established. A cheaper writer/model or smaller evaluated prompt
may still be needed. OpenAI is not configured on the phone test service; no
unverified model switch was made.

Vinted browser operations remain deliberately blocked in the hosted app.
Local draft automation uses existing generated copy, but verified remote login,
positive draft save, idempotency and cost per successfully saved draft remain
acceptance gates. No claim of a Vinted draft/publication is made by this change.

## Real storage incident

The morning item `upload_a58f2f04` was present at 08:03 London and absent on the
later authenticated backup read. Free hosting has ephemeral items; persistence
is still a blocker. The previously read full listing and two usage events were
recovered into `Vinted-Listings-Backup-20261003.zip` and saved durably. Original
photos were unavailable and are explicitly marked missing; they were not
fabricated. Durable service/disk or external storage is needed before a beta.
No paid infrastructure was provisioned.

## Verification

801 Python tests pass; Node checks cover upload, measurements and eBay safe
links/rendering/form submission; inline JavaScript syntax and whitespace
checks pass. Provider, eBay and browser tests are mocked unless the live
verification below states otherwise. Real market API access and original-photo
OCR quality still require their own evidence; a deterministic synthetic OCR
fixture is not a clothing-photo accuracy benchmark.

Live deployment, recovered-item restore, missing-credential handling and
first-write/cache-hit measurements are recorded in
[QUALITY_MARKET_LIVE_VERIFICATION_20261003.md](QUALITY_MARKET_LIVE_VERIFICATION_20261003.md).
Final runs: 1.52p cold / 0.97p warm; pair average 1.25p. Verified Vinted draft
completion and a consistent sub-1p cost remain acceptance gates.

## Sources checked

- https://platform.claude.com/docs/en/build-with-claude/prompt-caching
  Haiku 4.5: 4,096-token minimum; five-minute writes 1.25× input and hits 0.1×.
- https://developer.ebay.com/api-docs/buy/static/api-browse.html
- https://developer.ebay.com/api-docs/buy/static/buy-requirements.html
- https://www.ebay.co.uk/help/selling/selling-tools/product-research?id=4853
  Product Research exposes sold prices and sell-through within a selected period;
  this UI does not assert automated access to it.
- Marketplace Insights documentation redirected to developer sign-in. Approved
  sold-data/API access is not configured or verified by this implementation.
