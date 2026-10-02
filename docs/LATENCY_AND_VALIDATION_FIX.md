# Phone upload latency and numeric validation

2 October 2026; isolated branch `work/vinted-cost-measurements`.

## Observed failure

Failed live item `upload_daf6ddb5` reported `None is not of type number`.
Its model ledger recorded Haiku 4.5 extraction (5.404 s), material reread
(1.852 s), and writing (3.468 s): 10.724 s total provider latency, estimated
£0.01480223. No Sonnet escalation or ruler call occurred. Raw provider output
was not retained, so the exact offending numeric field cannot be established.
The compact prompt allowed unknown facts to be null, conflicting with optional
numeric purchase cost/confidence in the listing schema.

Original phone images were approximately 28 MB combined. This is a likely
transfer bottleneck; the original upload start time was not recorded, so the
reported three-to-five-minute wait cannot be apportioned conclusively. Server
CPU/memory metrics did not show exhaustion. This request followed a live
service startup; there is no evidence that a cold start caused this particular
wait.

## Changes

- Omit unknown purchase cost. Preserve supplied purchase cost, including zero,
  independently of generated text. Restore extracted confidence or omit it
  when unknown. Required numeric prices still fail validation rather than being
  invented. Validation errors now identify the field.
- Correct compact prompt's optional numeric contract.
- Prepare photos sequentially on the phone at maximum 2048 px and JPEG quality
  85 before network transfer; preserve role order. This matches existing saved
  image resolution. Revoke preview URLs; retain small JPEG originals when a
  re-encode would increase size. Browser decoding supplies image orientation.
- Show actual preparation/upload progress followed by the real analysis phase.
  Remove simulated Vinted-draft creation progress. Stop waiting after 90 seconds
  with uncertain-completion guidance and no automatic paid retry. A browser
  timeout does not cancel an already running server/model operation.
- Add Server-Timing and flushed safe logs for multipart reception, preparation,
  pipeline and overall request duration. No credentials or image content logged.

## Verification and limits

793 Python tests pass (13.09 s after schema-formatting fixes). Node checks cover resize dimensions, encoding contract,
resource cleanup, actual upload progress, error response and timeout behavior;
existing measurement UI checks pass. Browser canvas/EXIF behavior on the actual
phone still requires phone verification; these are simulated browser API checks.
The full pipeline/route is tested with mocked responses, including measurement
confirmation and all cost stages. Paid live verification is recorded separately
once completed. Neither consistent sub-ten-second performance nor comparative
Luna OCR accuracy is established. Six retrieved server-resized photos total
approximately 4.55 MB rather than 28 MB; phone output sizes will vary.

Free Render services sleep after inactivity and can take about a minute to wake.
Always-on hosting would address that separate startup delay; no paid hosting
change is made here. Reference: https://render.com/docs/free

Rollback: return the test branch to `2c79937473dfee30abf1daba5e44483d6ed96a84`
for the pre-fix implementation. Original service/backup branch are untouched.

## First paid retest

The first real six-photo retest reached the writer but failed on a different
field: `tag_keywords_confidence: 0.9 is not of type string, null`. This verifies
why field-specific errors are needed. Extraction confidence labels are now
carried authoritatively to the listing, with unknown labels marked low; the
writer cannot replace these with numeric scores. Regression coverage includes
invalid generated brand/material/tag-keyword confidence types. No success or
latency claim is made for this failed test.

The first retest's measured server time was 32.869 s: receive 0.616 s,
image preparation 5.999 s, pipeline 26.254 s. Provider calls inside that
pipeline totaled 11.648 s, exposing substantial local image-processing cost
on the free instance. Further fixes replace a Python per-pixel count with an
equivalent Pillow histogram count, and avoid redundant server JPEG encoding
for already prepared images after format, size and metadata verification.
Raw/oversized/metadata-bearing uploads still undergo normal preparation.

Label cropping also computes the maximum-filter bounding box directly, avoiding
a full-image 5x5 filter whose pixels were never otherwise used. Seeded masks
cover empty, sparse, edge-touching and small images and compare exactly with
Pillow's original maximum-filter bounds. Crop confidence uses the same source
mask and histogram; no OCR threshold or image resolution is relaxed.

## Second paid retest

After the image optimizations, the real six-photo request took 26.25 s from
the workspace, with 19.227 s on the server: receive 0.742 s, preparation
0.530 s, pipeline 17.955 s. It failed on writer gender capitalisation
(`Women's` versus schema `women's`). The compact prompt now includes the
exact minified listing schema, gender formatting is canonicalized, and null
unknown optional non-nullable fields are omitted. Required missing/invalid
prices still fail; unknown gender is not silently guessed. Another real
successful retest remains necessary. The sub-ten-second goal remains unmet.
