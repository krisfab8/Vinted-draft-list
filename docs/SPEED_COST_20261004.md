# Speed and cost — 4 October 2026

Target: `work/vinted-cost-measurements`, starting at `fb40b2e`;
phone test service `vinted-measurements-test`. Original app branch unchanged.

## Implemented behavior

- Selected photos start preparing immediately in a serialized queue, bounding
  phone memory. Create Listing awaits/reuses those same promises. Errors do not
  stall later photos. Original selection, order, roles and 2048px upload cap stay.
- Hosted startup defaults ENABLE_SINGLE_PASS=1; set 0 to restore the two-stage
  pipeline. Other local startup defaults remain the existing two-stage path.
- Compatible Haiku/Haiku or OpenAI/OpenAI settings use compact extraction with
  category and tentative price, then deterministic title/bullets from corrected
  evidence. No separate copy-writing model request. Mixed providers use legacy.
- Shared finalizer retains schema validation, size conversion, premium mill,
  condition, uncertainty, measurements and purchase-cost rules.
- Targeted brand/material rereads remain, including their billable usage. The
  fast path does not silently escalate the entire item to Sonnet. Truncated
  Claude responses fail visibly; missing price/category fails validation without
  a hidden paid writer fallback. Difficult/ruler items may take longer.
- eBay lookup remains on demand and cached from the previous patch; it was not
  blocking the generation path and needs no new background job for this patch.
- Password-protected provider status includes the selected single_pass flag.

## Evidence and limits

808 Python checks passed in 17.49s; upload and photo queue Node checks passed.
Mocks test the actual extract/assemble/price pipeline, one billable response,
unchanged cost attribution, authoritative hints, unclear copy filtering, size
conversion and invalid required fields. This is not a paid OCR benchmark.

Example Barbour prompt characters: old extraction 18,935 plus old compact writer
9,992; new single-pass prompt 4,654 (seller hints vary). These are character
counts, not token/cost measurements. The shortened prompt may need adjustment
after real garment testing, especially difficult labels and unusual categories.

Before deploying, authenticated backup returned HTTP 200 with an empty archive
(134 bytes); no saved original garment photos were available. The existing
recovered listing backup has no original photos. A meaningful 20-item paired
accuracy/cost/latency benchmark therefore cannot be completed from these files.
No 5–10 second or sub-penny result is claimed from automated tests.

## Phone verification

Use the same original photos for a representative clear item and difficult
labels. Check exact brand, tagged/normalized size, each composition percentage,
condition/flaws and category. Inspect the saved per-call ledger and Server-Timing.
Measure from pressing Create Listing to the editable result as well as the full
selection/preparation/upload interval; pre-preparation shifts work earlier.
Do not call a synthetic label test a real clothing accuracy comparison.

Deployment and live checks are recorded separately once observed.
