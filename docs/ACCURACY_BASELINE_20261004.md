# Restore accuracy baseline — 4 October 2026

ACC-01 / PRICE-05 / HOST-03b. User explicitly prioritises accurate item recognition over API savings and accepts the previous approximately 1.6p baseline. The compact single-pass experiment is not accepted as the hosted default.

## Evidence

Saved upload_bfd87d3e at 13:44:20 UTC: Haiku 4.5, 5,578 input / 492 output, one call, estimated £0.00635002, provider 5.990 s, recorded pipeline 10.385 s. AI proposal £110 was overwritten with £50 from generic wool-blazer £20–£80 memory. Incorrect mill “Pey Lino Panavot”, cloth line “Zelander Dream”, self-confidence .95/high. No rereads triggered.

Inspected all saved photos: front.jpg is the Boggi label; brand.jpg is the Loro Piana fabric label; model_size.jpg is size 54 / garment made in Italy; material.jpg is the full jacket. These are usable photos. Users should not need to distinguish maker/brand labels or correctly order slots for recognition.

## Change

Hosted start defaults ENABLE_SINGLE_PASS=0: restore full extraction instructions and separate writer. Flag remains an explicit experimental opt-in. Full extraction wording no longer asserts Photo 2 is the garment brand or Photo 1 determines item shape. Each of four core slots gets 1024px analysis resolution. Brand/material rereads inspect all core photos, with no slot-dependent evidence assumptions. Unknown-maker rereads are bounded, accounted, and independent of high self-confidence.

Known unique cloth line ownership (Zelander Dream, with explicitly recorded spelling variants) can correct a noisy maker using the photographed Loro Piana label as reference evidence, without another model call. Generic cloth lines do not infer ownership. Unsupported names remain raw evidence, become low-confidence and are omitted from confident keywords/copy. Garment brand is preserved. This is a curated check, not an exhaustive supplier registry or authentication system.

For tailoring with a known premium maker or explicit full-canvas evidence, a brandless generic memory entry no longer replaces the AI price. Price remains a provisional model suggestion needing comparable-sales review. No live eBay sold-price research is implied. No invented flat premium multiplier is added. Brand-specific bands keep existing behavior.

POST /listing/<folder>/check-evidence performs deterministic checks on saved evidence, preserving original snapshots and manually changed prices. It makes no AI call and does not infer new composition. Existing drafts can be corrected from their saved cloth-line evidence without another upload/generation. Initial API costs stay original.

The previous archive patch intercepted fetch, but uploads use XHR. Successful XHR upload now explicitly queues the public archive save hook. Initial analysis snapshot is now written on the actual upload route, as well as create-listing. Both are regression checked. This does not make device backup shared cloud storage.

## Validation

Full Python/Node results and the one controlled live test will be recorded after completion. Automated provider responses are mocked; real garment accuracy must be judged from the saved-photo test. Original data backed up before deployment; existing drafts will be restored without overwriting any server copy. No repeated paid attempts are planned.
