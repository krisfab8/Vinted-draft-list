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


## Controlled live result

Deployment c9628c3446ed42d9ed3093a5c3523b5296208e35 / dep-db15q4o473hc738noqn0 verified live; provider status single_pass=false. Restored both saved drafts and deterministic recheck returned Loro Piana / Zelander Dream, with provisional earlier AI proposals £110 / £95, no new calls for these checks.

One paid generation of the exact four saved photos, retaining their mismatched slots: upload_13d99297, HTTP 200; title “Boggi Milano Navy Wool Blazer 44R Loro Piana”; maker Loro Piana, line Zelander Dream; 100% New Zealand Merino Wool. £85 is a new unverified model proposal, not validated comparable-sales value. Cost estimated £0.0154095425 (1.54p), two Haiku 4.5 calls. 7,337 uncached input + 5,703 cache-creation input = 13,040 total input, 1,008 output. Provider latencies 6.299 + 4.860 = 11.159 s; server 16.228 s, full request 16.50 s. One case demonstrates recovered fabric recognition; not a general accuracy benchmark or under-ten-second result.

This live test also exposed writer-copy assurances (“Immaculate condition”) and replacement of printed tagged_size=54 by normalized_size=44R. Follow-up restores extracted tag separately from conversion, creates a clear label/conversion size line, and strips generated strong condition assurances. Original paid result remains in analysis.json; corrections can run without more AI. No second paid test planned. Cost/speed improvements remain secondary to accuracy.

Initial post-test backup contains all three saved versions and photos, persisted separately before the follow-up deploy. Device backup on Android still requires phone validation.

Follow-up verification: 830 Python tests passed in 19.85s; archive Node regression checks pass. Printed tag/converted size separation and generated condition-assurance removal are verified locally, including idempotent copy normalization. Three dependency-client destructor warnings occurred in mocked-provider tests; no test failures. Final follow-up deployment and saved-result checks pending.


Final live follow-up: commit 249c10287753fd097d225bedca21a8ceb1cf973b / deployment dep-db15vanf3r2c73blh6n0 verified live. Restored all three saved versions, confirmed full two-stage mode, corrected controlled-test printed tag to photographed 54 while preserving UK 44R, and used deterministic saved-copy checks to remove immaculate wording and create one label/conversion line. Original generated snapshot retains 44R/immaculate wording for comparison. The upload XHR archive trigger is served. Usage ledger has exactly four events: two original compact-run calls plus two paid full-baseline-test calls. No further AI generation occurred. Final ZIP preserves three drafts, photos, original evidence and feedback; persisted backup updated. Real phone IndexedDB behavior remains pending. Documentation evidence recorded on separate branch to avoid wiping the recovered free-host data with another documentation deployment. Next: test varied items once each, review stored outcomes, retain accuracy baseline until cost changes pass comparisons.
