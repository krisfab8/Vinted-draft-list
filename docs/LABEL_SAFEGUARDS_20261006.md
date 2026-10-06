# ACC-02: label safeguards — 6 October 2026

## Incident evidence

Reviewed the user's saved Galvin Green and M&S items and their assigned label photos. Originals and seller edits remain unchanged. Both material photos were correctly assigned. Saved photos are soft-focused; composition percentages on the M&S shell are not reliably readable. No exact M&S shell percentages are claimed here.

Galvin Green: medium-confidence 100% polyester was not rechecked because the former gate excluded basic synthetics. Seller confirms 97% polyester / 3% elastane. M&S: extraction guessed size 8 despite marking size uncertain; printed L is visible. Seller confirms UK 18 as an equivalent. An unquoted material recheck replaced the original uncertainty with 68% wool / 32% polyamide and promoted confidence. A later size correction left an explicit Size: 8 line in manually saved copy.

## Changed behavior

- Material and size photos retain up to 1536 pixels instead of 1024 through the existing preprocessing path. This preserves available detail; it cannot restore blur.
- Medium/unknown material confidence now qualifies for a bounded label recheck, including synthetic garments. An uncertain size shares that call; there is no separate size retry loop.
- Every accepted material replacement needs quoted label text containing each matching percentage/fibre pair. Printed size needs a matching token; 8 cannot match 18 or L. Recheck prompts keep shell and lining separate and prohibit invented numeric size conversions.
- Unsupported, unresolved low/medium material and size readings are kept as candidates and flagged for review, while withheld from generated facts. Generated copy also strips reintroduced candidate sizes and inferred fibres when those facts were withheld.
- Verified rechecks clear relevant uncertainty flags and retain quoted evidence. Logs report actual confidence instead of the previous hardcoded high-confidence skip message.
- Size edits synchronize the explicit Size detail, preserve the rest of manual description text, and distinguish a known printed L from an entered numeric equivalent. An uncertain 8 is not retained as a genuine printed label.

## Validation and limitations

Local full Python suite: 897 tests passed; nine Node checks passed. Existing mocked Anthropic client destructor warnings remain. Regression tests cover the two failure patterns, percentage transposition, token boundaries, copy reintroduction, the actual PATCH persistence route, and regeneration with a manual description. The M&S 70/30 fixture is illustrative mocked data, not a verified reading of the real garment.

No paid model rerun was performed. Model-provided quotes can still be wrong; these checks reduce unsupported substitutions, not guarantee perfect OCR. Uncertain items may use more tokens/time due to higher resolution and a recheck. Existing saved listings are not bulk rewritten, and the seller's confirmed corrections remain authoritative. Actual paid-photo accuracy and the live authenticated interface remain to be checked separately. Live browser access is blocked in this environment.

Source deployment pending at commit time; record the resulting commit/deploy separately after Render confirms live.
