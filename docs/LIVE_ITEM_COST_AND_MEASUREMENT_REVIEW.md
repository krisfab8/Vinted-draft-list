# Live item: model, cost, pricing and ruler review

Reviewed 2 October 2026. Deployed source: `c6ce0f76b154e1385ca7f775eff9750ea9425517`. Item: `upload_9fa524f0`, Avia Trix leather jacket, tagged 2XL. This report and tracker update are on `work/vinted-live-item-review`, separately from the auto-deployed branch, to avoid restarting the temporary-storage app during testing. No runtime behavior or provider selection changed for this review.

## Evidence and limits

The phone upload completed successfully at 21:22:40 UTC (22:22:40 London). Read-only authenticated inspection of `/api/run-logs`, `/listing/upload_9fa524f0`, the review page and the saved back/extra photographs corroborated the screenshots. No additional paid inference was run. Total recorded pipeline latency was 24.45 seconds; extraction 4.51 seconds and writing 4.45 seconds. The residual includes rereading and other work; it is not an exact timing measurement of the reread alone.

This is one successful example, not a model benchmark. Brand/material confidence is the model's assessment, not independent ground truth. A provider invoice was not inspected.

## Models and actual recorded usage

| Stage | Model | Input tokens | Output tokens | Recorded estimate |
|---|---|---:|---:|---:|
| Initial photo extraction | `claude-haiku-4-5-20251001` | 9,410 | 517 | £0.00948 / 0.948p |
| Material-label mill check | Haiku 4.5, same model ID | Not retained | Not retained | Omitted |
| Listing copy and initial price | `claude-haiku-4-5-20251001` | 6,580 | 426 | £0.00688 / 0.688p |
| Deterministic pricing | Python code | — | — | No model call |
| Recorded total, excluding mill check | — | 15,990 | 943 | £0.01636 / 1.636p |

The log explicitly reports `escalated=false`, no brand reread, no full material reread, and one mill-only reread. No Sonnet or OpenAI inference was used in this successful pipeline. The eBay enrichment service is on-demand and was not invoked by this pipeline.

The UI stores £0.0164 and rounds to `~2p`; it is an estimate, not evidence of an exact 2p debit. Current calculation uses $1/million input and $5/million output, multiplied by a fixed USD-to-GBP factor of 0.79. Those Haiku standard token rates match the official pricing documentation checked today. FX, tax, account discounts and provider billing reconciliation are outside this estimate.

### Cost-accounting defects

`app/extractor.py::_reread_material_photo` and `_reread_brand_photo` return parsed fields but discard response usage. `extract` overwrites initial usage when escalating to Sonnet. Consequently the current total can miss paid rereads and the first extraction on an escalated run. Failures, SDK retries and regeneration also need complete event accounting. The live mill-check cost cannot be reconstructed exactly from retained data. Do not describe 1.636p as the complete bill.

## Why this item was priced at £68

The saved `ai_price_gbp` is 68, final `price_gbp` is 68, `price_memory_match` is null, and the adjustment is `no memory match — using AI price`. It has a `no_price_memory` warning. No discount or memory ceiling changed that figure.

The writer receives a general pricing prompt; its men's outerwear table lacks a specific leather-jacket band. The result is therefore an unverified model suggestion, without dated comparable listings or verified sale evidence. The prompt also recommends higher coat prices in October–November; that could influence output, but its exact effect on this item cannot be established from the final JSON.

Recommended change: present a suggested range with evidence/confidence and allow a seller's quick-sale versus patient-sale preference. Retrieve relevant cached comps only when needed. Match material, brand, garment type, size and condition; distinguish active asking prices from completed transactions. Do not create a learned market band solely from this generated £68 or one seller opinion. No fresh market valuation was performed in this review.

## Where cost can be reduced

1. **Record every call before optimizing (COST-01).** Store stage, exact model, attempt, token/cache usage, stop reason, latency and rate/FX version. Preserve usage even if parsing fails. Display estimated versus reconciled costs clearly. Never retain credential-bearing errors.
2. **Avoid irrelevant mill checks (COST-04).** Currently any confident material result without `fabric_mill` triggers another paid label read, including this leather jacket. Restrict this to relevant woven tailoring or actual cloth-label evidence; retain full material rereads when composition is uncertain. Include fixtures for premium cloth-only labels so savings do not remove useful recognition.
3. **Shrink the writer (COST-05).** This stage contributed 42% of the recorded estimate. A representative rebuilt prompt contains roughly 6.2k characters of style instructions, 3.9k pricing instructions and 7.7k task instructions, plus category rules/item data; this is not the recovered exact paid request. Many stable normalization/title/category rules already run in Python. Remove duplicated instructions, use a smaller output contract, and evaluate a template-based writer. Halving this run's writer input alone would save about 0.260p, leaving approximately 1.376p before the untracked reread. Eliminating the writer call would leave approximately 0.948p before the reread, but copy quality must be evaluated first.
4. **Compact extraction selectively.** The current extraction prompt is 18,935 characters. Retain uncertainty and premium-label protections, but make item-specific branches smaller. Do not lower label resolution indiscriminately: it can damage the OCR that worked here. Output limits are ceilings; lowering a ceiling does not save money unless actual output falls, and truncation can create expensive retries.
5. **Compare a cheaper writer before replacing vision (MODEL-04).** Keep successful Haiku extraction as the baseline. Compare the existing Luna adapter on the same structured data, or deterministic copy, before changing image recognition. OpenAI key/access and real output quality remain unverified. Cross-provider token counts may differ; no measured Luna cost or accuracy is claimed. Prompt caching may help repeated stable instructions, but first-call cache creation costs and reuse windows must enter the ledger. Batch discounts are a separate queued workflow, not an immediate interactive-upload saving.

## Ruler findings and proposed feature

The actual saved `back.jpg` and `extra_01.jpg` contain readable metric and imperial ruler markings adjacent to garment edges. `_load_photos` reads only `CORE_PHOTOS`: front, brand, model_size and material. The ruler photos were never analyzed. The current extraction contract also lacks general chest/length/sleeve measurement fields. `Measurements in photos` is listing copy, not proof of measurement extraction. Existing manual W/L inputs are restricted to trousers/activewear.

Reading printed numbers is feasible; measuring the garment additionally requires the correct starting point, endpoint, unit, ruler alignment and measurement identity. In these close-ups the ruler's zero/start reference is outside the frame. They support endpoint reading, but do not independently prove where the ruler started or which garment dimension was measured. Do not automatically turn an endpoint reading into a confirmed full garment length.

**IMG-06: smallest useful measurement flow**

- Add explicit optional roles: pit-to-pit, back length, sleeve and other. Preserve roles from the phone instead of inferring them from brightness/order.
- Use a straight overhead photo of the garment laid flat, ruler alongside the intended measurement, both reference points visible. An overview plus endpoint close-up can work if their relationship is clear.
- Apply EXIF orientation and retain originals. Prepare a focused ruler/edge crop with enough context, rather than automatically analyzing all 20 photos at full resolution.
- Extract start/end readings, units, dimension name, source photo, uncertainty and reason. Return unknown for hidden starts/ends, ambiguous scales, slanted ruler or unclear garment boundary.
- Calculate end minus start and cm/in conversion in code. Keep flat pit-to-pit width separate from inferred chest circumference; never replace tagged 2XL with a guessed clothing size.
- Show a proposed measurement beside the crop, editable and awaiting seller confirmation. Only confirmed values enter listing copy; use approximate precision supported by the image, not arbitrary decimals.
- Start with Haiku on a small labeled ruler set. Any stronger-model retry must be bounded, costed and visible. Provider documentation warns coordinate/localization outputs are approximate, so model confidence alone is insufficient.

Acceptance: labeled examples with both scales, nonzero starts, hidden zero, diagonal photos, sleeves/hems and ambiguous measurement type; unknown where evidence is insufficient; a tolerable error threshold agreed for garment listings; phone correction flow; every extra call recorded. No automatic measurement feature or accuracy benchmark is claimed today.

## Recommended implementation order

1. COST-01 + COST-04: honest totals and targeted rereads.
2. COST-05: smaller/template writer, evaluated against approved copy.
3. IMG-01 + IMG-02 + IMG-06: oriented, explicitly labeled measurement photos with seller confirmation.
4. PRICE-03 + PRICE-04: ranges and relevant cached comparisons.

The hosted app still uses temporary storage. Preserve the tested item/photos before any future redeploy; this documentation commit intentionally does not redeploy the app.

## Official references checked 2 October 2026

- https://platform.claude.com/docs/en/about-claude/pricing — Haiku standard token rates and batch/cache pricing.
- https://platform.claude.com/docs/en/build-with-claude/vision — image handling, cost and spatial-reasoning limits.

Source inspection: `app/config.py`, `app/extractor.py`, `app/listing_writer.py`, `app/services/pipeline.py`, `app/services/pricing.py`, `app/web.py`, `app/templates/index.html`, `prompts/pricing_rules.md`.
