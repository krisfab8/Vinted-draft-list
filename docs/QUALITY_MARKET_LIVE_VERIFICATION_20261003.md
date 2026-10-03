# Live verification — 3 October 2026

Runtime commit: `d217b312227a4bfde0bbf1014eae6bf5de49ef62`.
Render deployment `dep-db0bad8473hc73807ks0` was confirmed live at 07:57:51 UTC.
Phone app: https://vinted-measurements-test.onrender.com

Rollback branch: `backup/vinted-before-quality-ebay-2026-10-03`, commit
`5c0e53d2a226185f80c93ac75cb8497aace04287`. Original private-test service unchanged.
This verification branch does not trigger another app deployment.

## Tests and live checks

- 801 Python tests passed in 12.99 seconds; upload, measurement and eBay UI Node
  checks passed. JavaScript syntax and git whitespace checks passed.
- Real authenticated deployment checked: new UI, private backup export, restored
  listing retaining £18 seller price and an explicit missing-photo marker.
- eBay comparison route returned `no credentials`; matching research links were
  available. No production eBay API result or sold-data access was tested.
- Four paid Anthropic generations were exercised across two runtime versions.
  No Vinted browser login, remote draft save or publication was attempted.
- Final two existing runs passed brand, size, material percentages and one
  condition-line assertions. The first verification assertion mistakenly required
  capitalised material names; the valid lower-case output was rechecked using
  case-insensitive comparisons without purchasing another generation.
- Synthetic test listings were deleted after verification; cost events remain
  accounted for. The recovered seller listing was retained.

## Final runtime: measured cost and time

Both stages used `claude-haiku-4-5-20251001`; no cheaper OCR model was substituted.
Costs are estimates from actual token counters using the application's recorded
rate table and USD→GBP rate of 0.79, not an invoice reconciliation.

| Stage | Cold request | Cache-hit request |
|---|---:|---:|
| Extraction cost | 1.1430p | 0.6088p |
| Writing cost | 0.3766p | 0.3645p |
| Total generation | 1.5196p | 0.9733p |
| Extraction provider latency | 6.794s | 5.690s |
| Writing provider latency | 3.111s | 2.649s |
| Server total | 15.277s | 12.940s |
| Workspace HTTP round trip | 21.40s | 23.62s |

Extraction: 4,906 uncached input tokens each time. First request created a
5,698-token cache prefix; second read those 5,698 tokens from cache. Outputs
were 488/446 tokens. Writer input/output counts were 3,147/324 and 3,114/300.
The whole request includes other pipeline work and upload handling; provider
latencies alone do not explain every second. These are two samples, not p95.
The fixture uploaded approximately 6 MB; a phone's network and prepared images
will change timing. This is not an under-ten-second acceptance result.

Cold→warm saving: approximately 36%. Average of this pair: **1.2464p**.
Earlier runtime checks measured 1.4837p cold / 0.9543p warm. All four paid
verification generations together cost approximately **4.93p**; fixture cleanup
must not erase this expenditure from accounting.

## Quality limits

Four synthetic images contained an ambiguous drawn garment and clear Sweaty
Betty / size S / 81% Polyester / 19% Elastane / Made in Taiwan labels. Both
final runs read those labels correctly and preserved size and composition in
buyer copy. One called the drawing leggings; the other called it joggers.
Condition grades also varied with extraction. Generic activewear/performance
wording still appeared despite the tighter writer instruction. This fixture
therefore demonstrates token accounting and label reading, not real-garment,
condition, ruler-reading or market-price accuracy. Do not present it as a full
quality benchmark.

## Remaining acceptance gates

1. Evaluate real garments and ruler photos with seller-verified truth; record
   extraction, condition and measurement errors before narrowing prompts/images.
2. Benchmark a smaller writer or deterministic evidence-based template against
   current listing quality. Writing currently costs about 0.36p; avoiding that
   paid call could bring warm generation near 0.61p, but cold extraction alone
   is above 1p. Do not switch solely on advertised token rates.
3. Reduce and evaluate extraction instruction/image costs for sporadic uploads;
   five-minute cache expiry means warm-only pricing is not a sustainable promise.
4. Add `EBAY_APP_ID` and `EBAY_CERT_ID` to hosting and verify approved Browse
   access with real matched results. Confirm sold-data licensing/access separately;
   manual research and asking-price samples must not be labelled automated sales.
5. Replace ephemeral item storage with durable storage. A real item and its
   photos disappeared before this change; only previously captured text and
   usage could be recovered. Download backups in the meantime.
6. Verify safe remote Vinted login and a positive draft-save result with
   duplicate prevention. Include failed/retried calls in cost per confirmed draft.

The user's **0.5–1p per successful Vinted draft** goal remains unverified.
The app's current cost badge measures generation, not marketplace completion,
hosting, or seller actions. No paid infrastructure was provisioned.
