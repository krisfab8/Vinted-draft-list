# First cost reduction from the accuracy baseline

The canonical project is krisfab8/Vinted-APP; the saved baseline is main commit ccebf1e117b821dc66838958b5912226659d0548. The existing Render test still deploys the original repository's work/vinted-cost-measurements branch. Tested code changes are mirrored there for deployment, without changing hosting accounts or credentials.

## Order

1. Remove repeated evidence and outputs from the writer. It returns six copy/proposal fields; extracted brand, sizes, composition, mill, confidence and condition remain authoritative. Retain all price-reference bands and core writing safeguards. No change to photo resolution, full extraction instructions or reread gates.
2. Avoid cold-cache writes for isolated testing (ENABLE_PROMPT_CACHE=0). The static text still precedes images in the same order. Caching remains opt-in for batch use; do not claim this is cheaper for high-throughput use with repeated hits.
3. Next: target rereads to confidently located physical labels/crops, independent of user slots, with full-photo fallback. Log absent versus unreadable evidence. Not implemented in this step.
4. Only after broader accuracy examples: trim redundant extraction prose and assess alternatives. Do not restore the cheaper one-pass path that missed premium labels.

## Stats

GBP estimates always display four decimal places (e.g. £0.0100 = 1p). Totals and recent per-run input include uncached, cache-write and cache-read tokens. Recent runs come from the usage ledger, including paid responses that failed to create a listing; legacy CSV rows are included only when their run is not already represented. Unknown call costs are marked; stored estimates remain more precise than their display.

## Verification

844 Python tests passed in 15.26 seconds; two existing mocked SDK cleanup warnings. Node camera lifecycle/picker/upload/preparation checks and git whitespace check passed. Tests verify extraction facts cannot be overwritten by writer output, a missing price cannot reuse an old price, and cache usage is counted without duplicate CSV entries. Real provider performance is pending deployment and bounded saved-photo reruns.

Cold baseline Boggi: 1.5342p, 12.444s pipeline, 21.72s total request. Toast: 1.9028p including 0.4053p material reread. Target is around 1p while preserving premium detail accuracy; no measured saving is claimed before actual calls.
