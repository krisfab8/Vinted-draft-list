# ACC-05: automatic composition-label preparation and independent checking

6 October 2026. Implemented locally; deployment and paid app retest tracked separately.

## Evidence motivating this change

The user supplied the original Peter Millar material photo: visibly 92% POLYESTER / 8% SPANDEX, whereas the generated listing said 88% Nylon / 12% Spandex. The 08:51 hosted log showed a high-confidence material result skipped the recheck. The actual Galvin saved-photo rerun at 08:47 did perform the recheck but still returned invented Shell/Lining 100% Polyester. A same-model quote and self-confidence are insufficient verification.

## Implemented behavior

- Local image preparation detects a supported light rectangular material tag, rectifies its angle, then selects a readable orientation. If detection is unsupported, retain the original view. Original photos are untouched. Existing brand/size preparation remains in place.
- Packaged RapidOCR/ONNX runs locally with one inference thread, two perpendicular views, and no network/model API requests. Models are distributed in the Python package. Results are cached by file path, modification time and size (eight entries).
- Numeric compositions from the named material photo must agree with an independent, complete local transcription. At least 95% line recognition confidence and a complete 100% sum for every section are required. These are conservative checks, not a guarantee of OCR correctness.
- A disagreement or unavailable/unreadable independent reading downgrades numeric material confidence and triggers the existing single bounded Claude recheck. No new paid-model stage or paid provider fallback is introduced. OpenAI/Gemini results are checked too, without an Anthropic fallback.
- The final answer must still match independent transcription. Self-certified quotes cannot bypass this gate. Unresolved percentages are withheld from buyer-facing material facts and retained as review candidates.
- Quoted verification compares the complete percentage/fibre set and section assignments. A single unsectioned composition cannot establish both shell and lining; minority fibres cannot be omitted. Printed synonyms (Spandex/Elastane, Nylon/Polyamide) are accepted without changing percentages.
- Recheck prompt asks for transcription before derivation, avoids anchoring with a sample blend, and forbids invented shell/lining headings.
- The writer carries verification/review evidence and authoritative extracted material facts through both compact and legacy paths; generated prose cannot restore a rejected blend.
- Snapshot/extraction logs store `label_preparation_version=local-composition-v1`, independent reading status, text, pairs and local latency. Existing model usage ledger records any conditional AI recheck.
- Hosted startup smoke-tests the packaged OCR engine on a blank image before accepting uploads. No paid call or customer photo is used.

## Local real-photo checks (not paid app generation)

| Original | Independent local result | Preparation / measured latency |
| --- | --- | --- |
| User-supplied Peter Millar | 92% Polyester / 8% Spandex; readable, minimum line confidence 0.993 | Rectified and rotated 90 degrees, 589 x 472 output; about 1.01 s including first initialization |
| Saved Galvin Green material photo | No independently verified composition | Rectified; about 1.75 s; uncertain numeric predictions will go to review |
| Saved M&S material photo | No independently verified composition | Original view retained; about 3.63 s; uncertain numeric predictions will go to review |

No personal photos are added to GitHub as new fixtures. The real-photo checks used the existing local originals. Automated OCR coverage uses a synthetic rotated tag; model integration tests use mocks and do not prove live AI accuracy.

## Checks and cost limits

917 Python tests and ten Node checks passed. Two nonfatal SDK client-destructor warnings occurred in mocked parallel-recheck tests. Existing provider-mechanics tests with blank photographs explicitly isolate independent evidence; separate tests exercise conflicts, unreadable labels, quoted section errors, omitted fibres, actual local OCR and writer suppression.

Cropping, orientation and local OCR use zero AI tokens. The smaller crop may reduce image tokens; that reduction has not been measured in a paid request. A conditional recheck sends the existing core-photo set and permits up to 450 output tokens. It can increase cost versus the previously skipped check. Agreement can avoid that check. Do not promise a fixed token saving or sub-penny result before observing actual usage. CPU latency and memory are additional costs; broader multilingual/dark/curved labels may require seller review.

Next: verify deployed commit and OCR startup log, then user-run Analyse photos again on Peter Millar / Galvin / M&S. Compare fresh facts, false claims, review rate, latency and full model ledger. Original drafts and seller corrections remain intact. This environment cannot access the authenticated live app (ERR_BLOCKED_BY_CLIENT), and has no local provider key, so paid app retests have not been executed by Codex.
