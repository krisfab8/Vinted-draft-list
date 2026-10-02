# Cost and measurement branch: implementation and verification

2 October 2026. Branch: `work/vinted-cost-measurements`.
Backup branch: `backup/vinted-working-2026-10-02`. Original working live code: `c6ce0f76b154e1385ca7f775eff9750ea9425517` on `work/vinted-revival-plan`. That branch and the running Render service are unchanged. Documentation review parent: `6d9daf47413fa2643dc9ab76b4cfc20f360460cb`.

## Separate checkpoints

1. `d910172`: per-call usage ledger, observed error accounting, bounded Anthropic requests without SDK retries, restricted fabric-mill checks. 69 targeted tests; full suite 773 passed.
2. `d3f369c`: compact writer with `ENABLE_COMPACT_WRITER=0` rollback; price evidence disclosure. 55 targeted tests; full suite 776 passed.
3. `ddfa946`: explicit photo roles, EXIF orientation, optional joint ruler call, seller confirmation and regeneration preservation. Full suite 784 passed; route/UI and negative-input checks passed.
4. Final checkpoint: ledger/CSV totals including unsuccessful runs, legacy CSV migration, seller-proceeds correction, documentation and final regression checks.

These identifiers refer to the published GitHub checkpoints. The final checkpoint appears after them in the branch history. Each checkpoint can be reverted separately. To return to the working app, continue using the original deployment branch; do not merge this branch until model quality and data preservation have been checked.

## Changed behavior

### Cost accounting and cheaper extraction

- Each actual Anthropic/OpenAI response records token usage before JSON parsing, plus requested model, stage, run/item identity, stop reason, latency (Anthropic), rates/FX and estimated cost. Failed requests record exception class only; missing billable usage is unknown, never zero-cost evidence.
- Initial extraction, Sonnet escalation, brand/material rereads, writer and optional measurements are aggregated. Parallel rereads carry the same run context. All paid responses are retained if later processing fails.
- Records are private runtime data in `data/model_calls.jsonl`, gitignored, available through authenticated hosted `/api/model-calls`. Item results show a model/stage/cost breakdown and an incomplete-cost label if needed.
- Lifetime estimates sum ledger events and historical CSV rows, deduplicating only rows already represented by run IDs. Repeated runs are not discarded. Existing CSV headers migrate without losing historical rows.
- Confident leather/suede and ordinary tops skip irrelevant mill-only searches. Woven tailoring and explicit cloth-line evidence retain them; uncertain material composition still receives the existing full reread.
- No key, response text or provider exception message is included in the ledger. Unobservable charges and provider invoices cannot be reconstructed; historic estimates remain incomplete. Gemini is not hosted-supported and its legacy usage is not fixed by this branch.

### Writer and pricing

- Compact writing is enabled on this development branch; `ENABLE_COMPACT_WRITER=0` restores the previous full prompt. Both paths retain existing validation, size/category normalization and condition post-processing.
- Representative leather-jacket prompt measured 19,825 legacy characters versus 7,651 compact characters (61.4% reduction). This is a character measurement, not a measured token/billing reduction or a quality benchmark.
- Suggested price now states its evidence. With no memory match, no range or market verification is fabricated. Stored ranges are explicitly reference bands, not freshly researched sales.
- £68 is not hardcoded or automatically lowered. No eBay API credentials, new comps lookup, sale-history model or verified market valuation was added. Existing on-demand eBay functionality remains separate; matching/caching upgrades need actual credentials and data.
- Corrected standard UK Vinted seller proceeds: buyer protection is not deducted from the seller. Profit uses sale minus acquisition cost and is labeled before other seller expenses; optional promotion/packing/tax are not invented.
- Vinted primary source checked: https://www.vinted.co.uk/how_it_works — standard selling has zero selling fees; buyer protection is paid by buyers.

### Ruler measurements

- Phone photo-role dropdowns travel with the photo. Server validates unique named roles, retains gaps, writes the correct renamed-file manifest and accepts up to 20 photos. Legacy callers without role metadata still use the scorer.
- Optional roles: flat pit-to-pit, back length, sleeve. One photo per dimension, up to three in one extra model call. Unselected extras/back still do not enter analysis automatically. The UI warns that ruler references must be visible.
- EXIF orientation is applied before resize/conversion. Measurements use a 1568px maximum image dimension. The existing upload resize still caps saved images at 2048px; preserving lossless original uploads and interactive crop editing are not implemented.
- Proposals require visible start/end, alignment, high confidence and an unambiguous cm/in scale. Hidden zero, ambiguous/duplicate readings, invalid numbers and implausible values yield unknown. Nonzero starts are subtracted; inches convert in code; candidates round to half-centimetres and await review.
- Values must be explicitly confirmed through the dedicated route. The generic PATCH route cannot bypass it. The save is atomic, adds an approximate measurement block, preserves keywords and tag size, and synchronizes the index.
- Regeneration retains confirmed values; model output cannot self-confirm or overwrite them. A failed optional call leaves unknown proposals and records unknown usage where necessary instead of failing the listing.
- Ruler evidence is a model proposal, not a guarantee. Real ruler-photo accuracy and calibration remain pending. The earlier live images lack a visible start; they must not be treated as independently proven complete dimensions.

## Verification

**Final automated result: 788 tests passed.** Node measurement UI checks, inline JavaScript syntax and git whitespace checks passed. A full multipart upload integration test exercised the real extraction → measurement → writer → pricing → persistence route with three mocked provider responses, verified complete cost aggregation, rejected model self-confirmation and confirmed that saving measurements makes no model call. Targeted tests exercise real multipart Flask upload, explicit manifest filenames, dedicated confirmation save, rejection without mutation, confirmed regeneration state, EXIF rotation, unit conversion, hidden/invalid readings, parallel call accounting, incomplete paid responses, legacy CSV migration and matching seller-profit calculations. Node checks exercise actual UI rendering and confirmation success/error handling. Inline JavaScript syntax and whitespace checks also run.

Model SDK/HTTP replies in these tests are mocked. No new paid calls, fresh deployment, live phone interaction, image-reading accuracy claim or invoice reconciliation is made. A browser engine is unavailable in the execution environment, so visual browser testing was not performed.

## Before a phone trial

1. Preserve the current hosted item/photos: its Render storage is temporary and a redeploy can lose them.
2. Deploy this branch to a separate private test service with Claude credentials configured privately, or explicitly select it after backing up current data. Never copy keys into git.
3. Compare compact and legacy prompts on the same labeled images. Check copy, tag size, materials, price evidence, latency and complete call cost. Use the rollback switch if copy worsens.
4. Test ruler photos with both endpoints and dimension identity visible; inspect each proposal and confirm/correct it. Include hidden-start cases that must remain unknown.
5. Keep the original service/branch as rollback. Choose a default and advertise savings only after the paid comparison; no sub-penny guarantee is supported today.
