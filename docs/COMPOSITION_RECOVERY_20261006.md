# ACC-06: recover readable material facts instead of only rejecting guesses

6 October 2026. Implemented locally; rollout and paid retest tracked separately.

## Actual live regression

User's Peter Millar rerun at 09:36:53 UTC used deployed ACC-05 commit 9b47b45. Hosted logs: material crop 2048 x 1536 -> 609 x 749; AI extraction `62% Polyester, 26% Polyester, 8% Spandex`; material reread rejected by quote validation; final materials blank. Actual reported cost £0.0170 with 17,056 input / 889 output tokens. This is a failed accuracy/usability check, not evidence that ACC-05 solved transcription. The complete saved-photo snapshot is not accessible in this session; the separately supplied original is 1536 x 1152. Do not claim its exact bytes equal the hosted 2048 x 1536 photo.

## Changes

1. Complete, agreeing local OCR reads can supply the literal material facts. Require two >=95%-confidence complete reads and no conflicting >=90%-confidence complete reading. Each explicit garment section must total 100%. Preserve the rejected AI interpretation as `material_model_candidate`, keep exact label text, and mark source `label_ocr_consensus`. This is repeated-view corroboration from one OCR engine, not two independent OCR models and not an accuracy guarantee.
2. One good local reading alone cannot override a disagreeing AI answer. A >=90%-confidence complete local candidate can corroborate an exactly matching AI composition. Conflicting local results remain review-only. Unknown digits, missing fibres, invented sections and incomplete totals never get repaired to 100%.
3. At most four local views. When needed, try contrast/downsampling; if the crop finds no complete candidate, also try the original view. Choose useful orientation even if composition requires review. Save all attempts, confidence, backend, version and latency in snapshots and authenticated operator diagnostics.
4. Composition-only AI fallback sees the prepared label and original material photo, without brand/marketing/front-photo distraction. One bounded call, existing usage ledger stage and 450-token cap. Shared size recovery/cloth-mill checks retain the existing cross-photo path. Agreeing local readings avoid the paid material recheck. No additional model provider fallback.
5. Backup filename validation now accepts exact `upload_retest_<32 hex>` identifiers and `reanalysis.json`. The old eight-hex-only backup pattern caused the observed 422 and excluded fresh reruns from export. Client backup/edit/delete tracking uses the same permitted retest form, retaining path and symlink restrictions.
6. Hosted startup runs a synthetic composition-recovery probe through the actual OCR/preparation/check path, with a wrong 62/26/8 starting answer. No customer photo or paid call. Its log is distinct from real paid app validation.

## Verification

- 930 Python tests and ten Node checks pass. Mocked SDK-destructor warnings remain nonfatal. Tests cover direct recovery, non-consensus withholding, conflicting views, moderate OCR plus exact AI agreement, bounded focused image set, skipped material retry, writer carry-through, retest ZIP export/restore and fresh-item device tombstones.
- Actual user-supplied original through Flask `POST /reanalyze/...`: real local OCR recovered 92% Polyester / 8% Spandex; description retained the Material bullet; original record byte-unchanged; fresh ZIP exported/restored with analysis and source metadata. Extraction/writing AI responses were mocked, including the known wrong 62/26/8 result. This proves the app's recovery path locally, not real provider performance.
- Separate original local OCR: agreeing correct 92/8, about 1.01 s. A generated 2048 x 1536 JPEG scale/compression variant also recovered 92/8 (~0.68 s). This variant is not the actual hosted file.
- Old Galvin/M&S originals still lack independently supported numeric compositions (~2.82 / 4.54 s with bounded fallback). Their guessed percentages remain withheld; existing seller records are unchanged.
- Local hosted-style synthetic recovery probe passes. Deployment log verification follows.

## Limits / next action

No new paid provider run has been executed by Codex. Live authenticated browser access remains blocked; no local API key is available. After source rollout and hosted recovery smoke verification, user should run one fresh Peter Millar analysis. Inspect `material_verification.attempts`, source facts, description and actual model ledger. Fresh backup now works if exact-photo diagnosis is still needed. Do not promise cost or latency improvement from mocked billing: local preparation uses zero AI tokens; conditional focused rechecks still cost tokens, and extra local views add CPU time. Broader real labels remain necessary before calling the OCR reliable.
