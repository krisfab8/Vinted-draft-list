# Vinted / Dodis task tracker

Updated 4 October 2026. Canonical task list. Read `OPERATING_GUIDE.md` before changing statuses.

Priority order: private usable test → reliable state/costs → labeled model evaluation → eBay seller workflow → controlled multi-user beta → further platforms.

## Next action

**Measure compact-v2 against the saved accuracy-first baseline, then broaden the labeled test set.**
Read `COST_ONE_PENNY_20261004.md`. The current path uses full vision extraction
plus a compact writer; single-pass remains disabled after premium-label regressions.
849 automated checks passed. Preserve the independent baseline on Vinted-APP main.
No twenty-item labeled photo set is available.

## Foundation and testing

| ID | Priority | Task | Status | Acceptance / dependency |
|---|---|---|---|---|
| DOC-01 | P0 | Operating guide and stable task list | implemented_local | Documents checked in with statuses, dependencies and handoff process |
| DOC-02 | P0 | eBay/multi-platform product roadmap | implemented_local | Shared inventory, platform boundaries and phased acceptance criteria documented |
| HOST-01 | P0 | Prepare private test deployment | implemented_local | Password gate; containment checks; browser actions disabled; persistent-state bootstrap; tests pass |
| HOST-02 | P0 | Deploy and verify private HTTPS URL | in_progress | HTTPS/auth, Claude configuration and one phone upload verified live; durable storage and wider evaluation outstanding |
| HOST-02a | P0 | Free private mobile preview | verified_live | 2 Oct: deployed 7dd7c8b; /health 200, unauthenticated / 401, authenticated / 200; temporary storage only |
| MODEL-01 | P0 | Opt-in Luna image + writer adapters | implemented_local | Both stages selectable; no hidden Anthropic fallback; usage returned; incomplete/error responses rejected; mocked tests pass |
| MODEL-02 | P0 | Live Luna smoke test | blocked | HOST-02; real label output, billed usage and correction quality checked; provider access verified |
| MODEL-03 | P1 | Label 50–100 representative items | todo | Original photos and exact visible brand/size/material truth, including unknown/unreadable fields |
| MODEL-04 | P1 | Compare Luna/Haiku and difficult-case Sol | todo | MODEL-03; same test set; correctness, false claims, latency, correction time and actual spend |
| MODEL-05 | P1 | Choose measured default + field retry policy | todo | MODEL-04 + COST-01; cheapest configuration meeting accepted quality; bounded retry/review gate |
| MODEL-06 | P2 | Upgrade optional Gemini path | todo | Current supported model + timeout/error/schema handling + real usage; compare only if useful |

## Reliability and data

| ID | Priority | Task | Status | Acceptance / dependency |
|---|---|---|---|---|
| REL-01 | P0 | Positive draft-save verification | todo | Save timeout stays failed; valid identity stored; real route tests; live browser smoke |
| REL-02 | P0 | Idempotent draft creation / retry | todo | REL-01; double-click/retry cannot create duplicates; reconciliation after uncertain save |
| REL-03 | P0 | Preserve edits and confirmed fields | todo | Purchase cost, brand confirmation, condition and field locks survive generation in code |
| REL-04 | P0 | Price-only reprice through common rules | todo | REL-03; approved title/description untouched; all paths use final authoritative fields |
| REL-05 | P1 | Validate final edited object | todo | Reject invalid types/negative/non-finite prices before write; validate before draft/API actions |
| REL-06 | P1 | Atomic/versioned item saves | todo | Concurrent changes cannot clobber each other; safe failure leaves previous file intact |
| REL-07 | P1 | Keep index/tracker synchronized | todo | PATCH/regen/reprice/delete update indexes; stale/deleted items absent; status tests |
| REL-08 | P1 | Propagate extraction failures to review | todo | Reread/truncation/missing-field evidence survives log removal; unknown confidence is not trusted high |
| REL-09 | P1 | Retry from extraction checkpoint | todo | Writer failure does not repeat paid vision; hash/model/prompt/hints invalidate stale cache |
| SEC-01 | P0 | App-wide safe paths and field permissions | todo | All local and hosted read/write/delete paths contain resolved paths; symlinks and dot segments tested; HOST-01 is only a hosting guard |
| SEC-01a | P0 | Hosted credential-safe errors and copied-key whitespace | implemented_local | Trim surrounding API-key whitespace; suppress caught route tracebacks and credential-bearing client errors; safe unhandled-error logs; 768 tests passed; live deployment verification pending |
| HOST-02c | P0 | Handle non-JSON upload failures | implemented_local | Upload preserves JSON errors and reports HTTP status for HTML/proxy failures; no HTML body exposed, no automatic paid retry; Node response checks passed; live upload diagnosis pending |
| HOST-02b | P0 | Private provider configuration diagnostics | implemented_local | Password-gated /api/provider-status reports readiness without key values; upload errors name missing key or unsupported provider setting; 768 tests passed; live diagnosis pending |
| SEC-02 | P1 | Multi-user identity and ownership | todo | Before inviting unrelated sellers: independent items, credentials, memory and requests; CSRF/rate limits/security review |
| HOST-03 | P2 | Remote Vinted session architecture | todo | Supported login, isolated session, recoverable expiry and verified save; no assumption headless alone is enough |
| HOST-04 | P1 | Persisted job queue and progress | todo | Bounded background jobs; truthful progress; restart recovery; avoid blocking all users |

## Images and recognition

| ID | Priority | Task | Status | Acceptance / dependency |
|---|---|---|---|---|
| IMG-01 | P1 | Apply phone EXIF orientation | implemented_local | Portrait/landscape orientation corrected before stripping EXIF; real rotated fixture |
| IMG-02 | P1 | Explicit photo roles and correct manifest | implemented_local | User roles transmitted/preserved; missing size photo cannot silently shift material role |
| IMG-03 | P1 | Preserve OCR originals and crop review | todo | Lossless/original source retained; crop edits; retry can use uncropped source |
| IMG-04 | P1 | Analyze supplied damage/back evidence | todo | Explicit cost policy; checked-photo provenance; flaws visible only there reach review |
| IMG-06 | P1 | Read explicitly labeled ruler measurement photos | in_progress | IMG-01–02 + COST-01; start/end/unit/source evidence, unknown for ambiguity, seller confirmation, tagged size retained; real labeled ruler evaluation |
| IMG-08 | P0 | Browser photo decode fallback and actionable errors | implemented_local | Server-only conversion of JPEG/PNG/WebP/HEIC; no AI call; corrupt/large images rejected; retry clears failed cache; father’s original photo unavailable |
| IMG-05 | P1 | Validate actual upload bytes | todo | Corrupt/oversized/decompression-risk images rejected without broken folders; useful errors |

## Costs and pricing

| ID | Priority | Task | Status | Acceptance / dependency |
|---|---|---|---|---|
| COST-00 | P0 | Correct test rates and persist upload costs | implemented_local | Haiku 4.5 rates corrected; Luna/Sol rates added; upload costs saved; not a full ledger |
| COST-01 | P0 | Complete per-call usage ledger | in_progress | Initial calls, escalation, rereads, regeneration and incomplete billable responses retained; provider reconciliation |
| COST-02 | P0 | Correct lifetime spend totals | implemented_local | Sum every event; separate latest run/item lifetime/account totals; no per-folder deduplication |
| COST-04 | P1 | Restrict irrelevant mill-only rereads | implemented_local | Preserve cloth-label/tailoring recognition; avoid leather/no-evidence checks; each attempted call recorded |
| COST-05 | P1 | Reduce writer prompt / compare template copy | implemented_local | COST-01; approved copy accuracy retained; actual token/cost/correction comparison on same inputs |
| COST-06 | P0 | Single-pass vision and deterministic copy | implemented_local | 808 tests; normal path one billable response; shared finalizer; targeted unclear-label rereads retained; real cost/latency/quality pending |
| IMG-07 | P0 | Prepare selected photos before submit | implemented_local | Serialized preparation starts at selection; reuse on submit; roles/order preserved; Node checks pass |
| COST-03 | P1 | Enforce cost budgets before calls | todo | COST-01; bounded output/attempts + estimated image cost; explicit over-budget review; rate/FX/version recorded |
| PRICE-01 | P0 | Correct seller proceeds calculation | implemented_local | Vinted buyer fee not deducted from seller; seller expenses explicit; stats use same service |
| PRICE-02 | P1 | Unify material/memory normalization | todo | Writer/pricing match the same attributes; mixed-fibre cases tested |
| PRICE-03 | P1 | Evidence-based confidence/feature pricing | todo | Dated memory, sample count; generated words do not create premiums; no blind low-confidence overrides |
| PRICE-04 | P1 | Relevant cached eBay comps | todo | Size/model/category/condition matches; shipping context; links/timestamps; stale/failure policy |
| PRICE-05 | P1 | Verified sale outcomes and publication date | todo | Accepted price separate from public price; days live start at publish; unknown stays unknown |
| PRICE-06 | P2 | Calibrated dynamic suggestions | todo | PRICE-03–05; actual sale price/time; range/reasons/confidence; explicit acceptance |

## eBay and other platforms

| ID | Priority | Task | Status | Acceptance / dependency |
|---|---|---|---|---|
| EBAY-01 | P1 | Seller OAuth and account readiness | todo | User consent/token refresh/revoke; sandbox + production separated; seller policies/location verified |
| EBAY-02 | P1 | Shared item + eBay adapter | todo | Stable SKU; category/item specifics, condition, delivery and fees mapped; source fields remain independent |
| EBAY-03 | P1 | Create unpublished inventory offer | todo | EBAY-01–02; official API; offer ID persisted; validation before save; retries deduplicated |
| EBAY-04 | P1 | Review and explicitly publish on eBay | todo | EBAY-03; preview actual fields/price/fees; seller confirmation; sandbox first then one production smoke |
| EBAY-05 | P1 | Track eBay status/orders | todo | Poll/webhook evidence as supported; token expiry; cancellation; status reconciliation |
| XPLAT-01 | P1 | Prevent cross-platform overselling | todo | EBAY-05; single quantity state; sale reservation; withdraw others; uncertain failures flagged |
| XPLAT-02 | P2 | Platform exports before integrations | todo | Copy/export packs; clear manual steps; never fake automated publication |
| BETA-01 | P1 | Small invited-user beta | todo | Reliability/cost/account-isolation gates met; quotas, privacy/deletion/backup/support; measured 5–10 users |
| ENG-01 | P1 | Tested dependency lock + CI | todo | Reproducible install and suite on PR; direct dependencies declared |
| ENG-02 | P2 | Focused code/UI cleanup | todo | Shared logic extracted without broad browser rewrite; mobile flow; truthful status/messages |

## Verification log

- Review baseline: 760 tests passed; real calls and live draft save not exercised.
- Revival patch: **767 tests passed in 13.94 seconds**, including real hosted Flask route guards in an isolated process, persistent-storage bootstrap behavior, provider payload/usage/error handling and absence of hidden Anthropic calls on the Luna extraction path. Live model calls and a Docker image build were not performed.
- 2 October 2026: Render free service `srv-davmdce7bikc73eknv00`, deploy `dep-davmdd67bikc73eko260`, commit `7dd7c8bb3224e063544ab958181e71b80b206a63` reported live. HTTPS checks: `/health` 200; unauthenticated `/` 401; authenticated `/` 200 HTML with no-store; authenticated `/upload` 503 with explicit missing-provider-key message. No live model call or phone upload claimed. Narrow hosted/provider suite rerun: 7 passed in 1.79 seconds. Storage is ephemeral, not a mounted disk. Password is held in Render environment settings, not this repository.
- No eBay seller OAuth or publishing implementation is claimed by this roadmap.

- 2 October evening: hosted configuration switched to Claude Haiku. A copied API key with a trailing newline caused an illegal HTTP header, and a route returned the SDK traceback to the browser. Key rotation is required; no credential value is stored in this tracker. Patch trims API-key outer whitespace and sanitizes hosted route errors, including internally caught exceptions. Full suite: 768 passed in 14.67 seconds; targeted tests include real upload/create-listing failure responses and copied-key normalization. This does not verify provider billing/access or OCR accuracy.

- Added private provider diagnostics after a subsequent phone upload again reported missing configuration despite the key variable appearing in Render. Response exposes only supported provider names, key-variable names and readiness booleans; unknown provider values are not echoed. Full suite: 768 passed in 14.94 seconds.

- Phone reported an HTML response parsed as JSON. Logs contained no completed upload in the reported interval; memory remained approximately 112 MB against 512 MB, so no memory-exhaustion conclusion is supported. Frontend now reports HTTP status for non-JSON responses, including specific 413/401 guidance and uncertain completion/retry advice. Node checks covered JSON success/error, HTML 413/401/502/504/200, and null JSON.

## Update rules

Keep IDs stable. Do not rename an open task to hide scope. Split partial work into a subtask rather than marking the parent complete. Record the commit, test and live outcome when relevant. After each session, replace “Next action” with the actual next dependency. Preserve blockers and known regressions.

- 2 October 22:25 London follow-up: authenticated live run log/listing confirms successful Avia Trix upload `upload_9fa524f0` at 21:22:40 UTC. Haiku 4.5 initial extraction 9,410/517 tokens; writer 6,580/426; no Sonnet escalation; one mill-only reread with discarded usage. Recorded £0.01636 excludes that reread. £68 is unchanged model output with no memory match. Saved back/extra ruler photos inspected: readable scales, start/zero outside close-up; neither photo enters core extraction. Added evidence-based review and COST-04/05, IMG-06. Documentation stored on separate `work/vinted-live-item-review` branch; no runtime changes, redeploy or additional paid calls.

- 2 October implementation branch: COST-01 observed-call ledger and COST-02/04/05, IMG-01/02, IMG-06 confirmation flow, PRICE-01 seller fee correction implemented. Checkpoints and limitations: `docs/COST_MEASUREMENT_IMPLEMENTATION.md`. Complete provider invoice reconciliation, paid compact-prompt evaluation, real ruler calibration, eBay matching/caching and durable hosting remain outstanding. Original deployment branch/service untouched.

- Final implementation verification: **788 tests passed**; Node measurement UI checks and inline script syntax passed; git whitespace check passed. Full real Flask upload/pipeline test used mocked provider responses and verified exactly three accounted calls, correct totals, no irrelevant mill reread, seller-confirmed measurement persistence and no paid confirmation call. No additional paid model call or redeploy performed.

- LAT-01 / VAL-01: phone latency and optional numeric regression fixed on isolated cost/measurement branch. See `LATENCY_AND_VALIDATION_FIX.md`. Pre-transfer 2048px preparation, actual upload progress, no automatic paid retry, safe phase timings, authoritative purchase cost and field-specific validation. 790 Python tests plus Node upload/measurement checks pass. Live test pending; no sub-ten-second guarantee or phone browser validation claimed.

- LAT-01 follow-up: first paid retest exposed a numeric tag-keyword confidence label and measured 32.869 s server total (0.616 s receive, 5.999 s preparation, 26.254 s pipeline; 11.648 s provider calls). Confidence labels now come from extraction. Verified prepared JPEGs skip redundant server encoding; equivalent histogram and bounding-box operations replace slow pixel loops/full-image filtering. 792 tests pass in 12.80 s; Node upload/measurement checks pass. Second live verification pending.

- VAL-01 / LAT-01 second retest: preparation fell to 0.530 s and server total to 19.227 s, but the model returned capitalized gender. Exact minified schema added to compact prompt; harmless gender formatting canonicalized and unknown optional non-nullable fields omitted. Required invalid data still fail rather than being invented. 793 tests pass in 13.09 s; final real success verification pending.

- 3 October: COPY-01 confidence-aware copy/condition deduplication and COST-06 exact-prefix Haiku caching implemented; PRICE-04 matched cached asking-price summaries, links and seller-entered sold research implemented locally. No automatic sold-data or Vinted draft save claimed. Private backup/export/restore added after confirmed free-host item loss; morning listing/accounting recovered, photos explicitly missing. 800 Python tests and three Node UI checks pass. Details and pending live evidence: `QUALITY_COST_AND_EBAY_20261003.md`.

- HOST-02d (3 October): user-requested memorable app password support; minimum length lowered to six characters, missing/short passwords still reject startup, HTTP Basic gate preserved. 802 tests passed in 14.33 seconds, including correct/incorrect six-character login and startup rejection of missing/undersized passwords. Live deployment verification pending. Password remains in Render environment settings only.

- HOST-03a / REVIEW-02 / UI-02 (4 October): device ZIP archives, missing-item restoration, original-result snapshots and compact feedback implemented on cost/measurement branch. Measurements/eBay/backup/feedback panels folded; small draft edit link. 820 Python tests plus simulated IndexedDB recovery/error/deletion checks and existing Node/syntax checks passed. No new AI calls or paid hosting. Device-only safety net; shared durable cloud storage and Android browser validation remain outstanding. Details: `DRAFT_ARCHIVE_FEEDBACK_20261004.md`. Live deploy pending.

- ACC-01 / PRICE-05 / HOST-03b (4 October): accuracy priority confirmed by user. Restored hosted full extraction + writer default, role-independent core-photo/reread checks and 1024px front resolution; unique cloth-line maker validation; generic premium-tailoring pricing override removed; deterministic saved-evidence recheck; fixed actual XHR-upload archive trigger and upload snapshot route. Latest regression saved/inspected at 0.635p, provider 5.99s, pipeline 10.385s; £110 proposal was wrongly replaced by £50. Details: `ACCURACY_BASELINE_20261004.md`. Full verification and one controlled saved-photo generation pending; no new accuracy/cost target claimed.

- ACC-01 controlled live check (4 October): c9628c3 / dep-db15q4o473hc738noqn0 live; full two-stage provider mode verified. Same four saved photos in mismatched slots correctly produced Boggi / Loro Piana / Zelander Dream / 100% NZ Merino. One paid generation 1.54p, 16.50s request, two calls (11.159s provider total). £85 remains unverified. Saved earlier drafts rechecked without AI to recover correct fabric; original £95/£110 proposals preserved. Follow-up fixes printed size preservation and unsupported immaculate-copy assurances exposed by this test; no second paid run. Latest full checks/deploy status follow after completion.

- UI-03 (4 October): compact Add photos dialog offers Take photo (native rear-camera file capture) and Choose photos (multi-select gallery). Both use existing role assignment, preparation queue, preview and 20-photo limit; cancellation keeps selections. Add tile supports keyboard activation. Camera/gallery simulated Node checks and existing upload checks pass; full suite 830 passed in 14.11s (two existing mocked SDK cleanup warnings). Actual Android/iOS camera handoff needs phone validation; desktop capture support depends on browser. No paid AI calls. Deployment pending.

- UI-03b (4 October): user rejected the source-choice popup and requested a familiar camera screen. Replaced it with a viewport camera dialog: live rear-camera preview, shutter, gallery, camera switch, selected-photo strip/removal, Done count; torch control only when supported. Uses browser getUserMedia without audio; frame JPEG uses up to 2048px and the existing preparation pipeline. Permission/unavailable errors retain native-camera/gallery fallback; closing/navigation/backgrounding stops tracks; late permission/encoding results are discarded. 830 Python tests passed in 13.96s, Node capture lifecycle and picker/upload checks passed. Cloud visual QA blocked by ERR_BLOCKED_BY_CLIENT; local Chromium download unavailable. Real Android camera, layout and label clarity remain phone validation steps. No paid analysis. Deployment pending.

- PRICE-07 (4 October): confirmed premium features enforced deterministically in generated titles (mill with cloth context, natural fibre, Super grade and Full Canvas; cashmere blends labelled separately); premium features shared with eBay queries and required comparison matching. Size/colour now soft comparison bonuses rather than mandatory filters. Existing seller titles/prices preserved during saved-evidence checks/research saves. Fresh research links returned when opening saved drafts. New folded seller-entered sold title/GBP price comparison tool needs three unique relevant rows for average/median and retains evidence, excluded count, examples and source; no automatic sold API or price overwrite claimed. Asking-price refresh retains saved sold comparisons. Latest actual Boggi run upload_3a7a8924: extraction 4,159 input + 5,703 cache creation, 532 output, £0.0110187225; writer 3,176 input, 382 output, £0.00401794. Total 13,038 input including creation, 914 output, estimated £0.0150366625 (1.50p); 14.305s pipeline, 10.349s provider. Titles/search improvements no AI calls. Regression checks and live deployment follow. Next cost step: trim copy-writer prompt with full extraction unchanged; compare saved evidence before any vision reduction.

- PRICE-07 local verification: 842 Python tests passed in 18.16s (existing mocked SDK cleanup warnings), Node camera/picker/upload/preparation checks and inline script syntax passed. Includes writer finalization, long-title preservation, uncertainty, cashmere blend distinction, premium query/size variation, invalid comparison input, duplicate samples and price/title preservation.

- BASE-01 (4 October): prepared independent repository snapshot of 3f037e8 with all four current saved drafts/photos and fresh Boggi rerun accounting; accuracy-first baseline documented in BASELINE.md. New private repository krisfab8/Vinted-APP populated on main through GitHub tools; no app changes/deployment or additional paid analysis.

- COST-08 / STATS-02 (4 October): compact-v2 delta writer keeps extracted facts authoritative, removes full-schema echo and repeated pricing prose; cold prompt caching off by default for sparse tests (batch opt-in retained). Stats shows input/output totals including cached input, recent ledger runs and four-decimal GBP estimates. 844 tests + Node checks pass. See COST_ONE_PENNY_20261004.md. Deployment and controlled paid comparisons pending; full image analysis unchanged.

- COST-09 / BRAND-02 (4 October): first live cost test exposed an existing unnecessary Sonnet escalation and Toast→Coast fuzzy correction. Missing optional fields no longer trigger full escalation; dedicated label rereads retained, confidently read brands bypass fuzzy replacement. 848 tests pass. Fresh corrected Toast measurement pending.

- COST-09 / BRAND-02 measured: corrected Toast 1.5668p (previous 1.9028p), no Sonnet, Toast retained; Boggi 1.2160p (previous 1.5342p), Loro Piana/merino/Full Canvas retained. New material-source guard prevents unsupported Cotton reread from overturning explicit absent-label evidence; 849 tests pass. Sparse ~1p target remains outstanding. All paid failures retained in ledger/evidence; original baseline main untouched.

- COPY-01 (4 October): standard generated description uses short opening then dash details in Size, Made in, Fabric mill, Fabric line, Fit, Model, Material order. Known EU tag and validated UK conversion appear together on the first size line (UK 44R / EU 54); unsupported size systems remain label/equivalent and missing sizes stay absent. Saved edits are not automatically rewritten. Shared finalizer and compact title ordering updated; no recognition/model changes or new AI calls. Full suite/deployment verification below.

- COPY-01 verified_live: 852 tests passed. Render commit 42d88e7ffbf5f5348e92d91e6414b383983b4a83 live; three drafts restored after restart. Both Boggi descriptions patched/read back with paired UK/EU sizes, unchanged £72/£95 prices, no model calls. Original analysis snapshots preserved. See test-evidence/Description-Layout-20261004.json.

- UI-REFRESH-01 / PRICE-05 / PRICE-06 (5 October): fresh-on-open drafts and restored-layout migration; indexed seller-confirmed lifecycle database, tracked cohort sell-through, actual-sale price learning with >=3 strict platform-specific matches, separate device history backup and optional CSV export. 865 Python checks + Node refresh/archive/camera and template syntax checks pass. Details/limitations: SALES_HISTORY_20261005.md. No AI/Jev calls, no pooled-user pricing or new hosting provisioned. Deployment verification pending.

- MVP-01 (5 October, implemented_local): atomic/revision-protected edits, deterministic price proposals and explicit acceptance, authoritative manual fields through regeneration, inventory lifecycle filters and richer confirmed-sale evidence. 880 Python tests and nine Node UI checks pass. See MVP_PRIORITIES_20261005.md. Live deployment pending a current backup of disposable-host data; no paid storage or multi-user pooling added.

- UI-04 (5 October): red foreground navigation count; styled quick Sold form with actual price and optional purchase cost; UK current date default, existing publication/sale dates retained; full calendar corrections under More details, month/year card display. Sold page reuses draft cards with red SOLD tags and actual proceeds, separate from developer AI-cost stats. Sold items leave Drafts; backup queue flushed before sale reload and Sold navigation. 883 Python tests, nine Node checks and rendered-page JavaScript syntax passed. Existing mocked SDK destructor warnings remain. Render deployment follows; phone appearance and device recovery require user validation.

- UI-04 retry verified 5 October: e844bc4 live on dep-db1mrpp42hec73deb700 after first Render attempt timed out without app-start logs or a bound port. Same-source retry succeeded; no port/code fix was necessary. User screenshot confirms Sold page and one seller-recorded sale.
- UI-04c (5 October): monthly Sold overview with native month picker, sales, gross profit before fees, average known-cost item profit, and aggregate return on purchase cost. Unknown purchase costs excluded from profit/ROI; explicit zero costs included, zero denominator displays unknown. Sales metrics use confirmed history even when an item folder is unavailable. Sold cards omit review/error dots. Distinct sale-tag navigation icon, sale controls before description and no draft-connect controls on sold items. 885 Python tests, nine Node checks and rendered monthly-route/JS checks pass; existing mocked SDK cleanup warnings remain. Deployment follows; no paid analysis or invented live transactions.

- UI-05 (5 October, implemented_local): premium mobile-first stockroom theme shared across Upload, Drafts and Sold. Shorter photo-first upload, deep-teal monthly metrics, folded explanations, safer deletion inside the item view, keyboard/focus handling, two/three/four-column inventory and desktop header navigation. Original UI saved remotely on backup/ui-before-redesign-2026-10-05 at 6d024df. 885 Python checks and nine Node checks pass; deletion identity regression added. Real Chromium rendered 12 fixture layouts at 320/390/768/1440px without horizontal overflow; search, sale-form entry, keyboard dismissal/focus and surviving-card identity passed. Fixtures are isolated and do not create real sales. No paid analysis. See UI_STOCKROOM_20261005.md. Render deployment verification follows; actual phone camera/keyboard remains device validation.

- UI-06 (6 October, verified_live): expressive cobalt/coral resale studio, SVG logo and upload illustration; switchable recorded sales/profit timeline, known-cost profit ring, folded accessible chart values and compact metrics. Stale thumbnail recovery uses existing front/back/brand photos with designed missing-image fallback. Previous UI saved remotely at backup/stockroom-ui-2026-10-05 (5bae260). 888 Python tests and nine Node checks pass; existing mocked SDK destructor warnings remain. Four-width isolated browser evidence and limitations in UI_RESALE_STUDIO_20261006.md. No paid analysis or live sample transactions. Render d8f6378 / dep-db29p36gekts739p0ml0 reported live at 07:02:19 UTC, 6 October; https://vinted-measurements-test.onrender.com. Local fixture UI verified; authenticated live UI and real phone remain user validation.

- ACC-02 (6 October, implemented_local): safer uncertain tag handling, 1536px size/material inputs, shared quoted-evidence recheck, withheld unsupported material/size candidates, and synchronized explicit Size detail on edits/regeneration. 897 Python tests and nine Node checks pass. Incident evidence, mocked-fixture limits and deployment follow-up: LABEL_SAFEGUARDS_20261006.md. No paid OCR rerun or automatic rewrite of existing seller listings.

- ACC-02 deployment evidence (6 October): 850d1f9 / dep-db2ad6egekts739pn2lg reported live at 07:44:37 UTC on https://vinted-measurements-test.onrender.com. Source deployment verified; authenticated UI and paid OCR accuracy remain unverified. Saved Galvin data replay confirms medium-confidence synthetic recheck/withholding. Existing M&S/Galvin records remain unchanged.

- ACC-03 (6 October, implemented_local): readable exterior logo/embroidery/print wording retained separately from manufacturer and deterministically included in description, even unfamiliar names. Uncertain wording retained for review and withheld from generated copy. 903 Python tests and nine Node checks pass. No new model-call stage or paid-photo test; existing items unchanged. GARMENT_TEXT_20261006.md records scope and verification limits. Deployment follows.

- ACC-03 deployment evidence (6 October): e49d680 / dep-db2agruq1p3s73ef2g8g confirmed live at 07:52:20 UTC on https://vinted-measurements-test.onrender.com. Deployed source/status verified; real-photo transcription accuracy and authenticated UI remain unverified. Existing listing records unchanged.

- ACC-04 (6 October, implemented_local): independent saved-photo retest in draft sheet, byte-preserving photo copies, no previous size/material hints, original draft unchanged, idempotent paid request, cost/snapshot records and previous-versus-fresh comparison. 907 Python tests and ten Node checks pass. Actual Galvin/M&S paid reruns blocked by live browser ERR_BLOCKED_BY_CLIENT and no local provider key; user-run in-app test is next. PHOTO_REANALYSIS_20261006.md distinguishes prepared capability from actual OCR results. Deployment follows.

- ACC-04 deployment evidence (6 October): 9d27d09 / dep-db2b2enavr4c73afgad0 confirmed live at 08:29:53 UTC on https://vinted-measurements-test.onrender.com. Saved-photo retest capability deployed; actual Galvin/M&S paid analyses and phone UI remain user execution/verification. No original records changed.

- ACC-05 (6 October, implemented_local): automatic material-label rectification/orientation, packaged independent local OCR, complete percentage/section matching, confidence-independent conflict recheck and final withholding, writer evidence preservation, local-latency/snapshot diagnostics and hosted OCR smoke test. 917 Python tests and ten Node checks pass. Actual original Peter Millar photo independently reads 92% Polyester / 8% Spandex (~1.01 s); saved Galvin/M&S photos remain independently unreadable and require review. No paid AI retest yet; deployment follows. AUTO_LABEL_VERIFICATION_20261006.md records real-photo evidence, conditional token impact and limitations.

- ACC-05 deployment evidence (6 October): 9b47b45 / dep-db2c0a6q1p3s73egnte0 confirmed live at 09:34:09 UTC. Hosted local OCR initialization/inference smoke passed at 09:33:42 UTC. Source deployment and dependency readiness verified; actual paid Peter/Galvin/M&S listing generation and authenticated phone UI remain user-run checks. Existing seller records were not rewritten.

- ACC-05 live regression (6 October, 09:36 UTC): latest deployed source confirmed; real Peter Millar rerun read 62/26/8, rejected recheck, final material blank. Reported 17,056 in / 889 out, £0.0170. ACC-05 did not solve transcription/recovery. Fresh retest backup also returned 422 due to identifier validation. See COMPOSITION_RECOVERY_20261006.md.

- ACC-06 (6 October, implemented_local): recover complete agreeing literal OCR facts, bounded contrast/original fallback, focused composition-only AI recheck, retained raw diagnostics, fresh-item ZIP/device backup support and hosted synthetic recovery probe. 930 Python tests and ten Node checks pass. Actual supplied photo through real Flask rerun route recovers 92% Polyester / 8% Spandex in final copy with mocked wrong extraction/writing calls; source unchanged and backup roundtrip succeeds. Actual hosted-photo paid provider success remains unverified; deployment follows.

- COND-01 / TAGTEXT-01 (6 October, implemented_local): retail/hang/swing tags attached now always mean "New with tags" (deterministic `condition.has_retail_tags`, with "no tags / tags removed" exclusions; extraction and writer prompts told the same). Every tag_keywords term, any confidence, plus high-confidence logo/print text is guaranteed in the description Keywords line (`description_layout.ensure_keywords`); uncertain logo readings stay withheld. Extraction now asks for product-line/colourway names on hang tags (e.g. "Color Wave"). Triggered by the user's new-with-tags shirt read as Excellent with "Color Wave" missing. 955 Python tests pass; real re-read on that shirt pending.

- TAGTEXT-02 (7 October, implemented_local): live re-read of the Peter Millar shirt got New with tags but still missed "Color Wave"; its tag colour/model name were low-confidence, so the hang-tag name most likely landed in colour_from_tag/model_name. Those readings now also reach the Keywords line. Clearly read tag names (e.g. "Summer Comfort") are inserted into generated titles after the brand, up to two, skipping care wording and never exceeding 120 characters. 958 Python tests pass; real re-read pending.

- UX-DEL-01 / PRICE-RANGE-01 / REPRICE-01 (7 October, implemented_local): Drafts long-press (0.5 s) enters jiggle edit mode with a ✕ per unsold card, a Yes/No confirm dialog and Done; the sheet's Delete listing uses the same dialog. Every price now carries `price_range` (small suggested range ±8/10/15% by evidence, min ±£2, plus a gauge scale); review page shows a green→red dial with the reasons. Reprice now accounts for condition: a bare AI price is scaled by condition factors (NWT 1.30, NWOT 1.15, Excellent 1.05, Very good 1.00, Good 0.85, Satisfactory 0.65) relative to `ai_price_condition`; reference bands keep their own condition positioning. Review page has a Reprice button with Use/Keep and a nudge after condition/flaws/brand/size edits. 966 Python tests and ten Node checks pass; headless Chromium check of long-press/cancel/delete/Done and condition→reprice→accept passed locally.

- PRICE-WEB-01 / STATS-01 (7 October, implemented_local): new listings and "Analyse photos again" now run one Claude Haiku call with Anthropic's server web search (max 3 searches, GB location; `ENABLE_WEB_PRICE=0` turns it off, `WEB_PRICE_MAX_SEARCHES` caps it). Medium/high confidence with >=2 sold examples sets the price (above AI guess and generic reference bands, below the seller's own matching sales); later condition changes rescale it. Ledger records web searches at $0.01 each. Each run stores `run_stats` (time, cost, calls, tokens, searches per stage) shown on the review page with the web examples. Manual calibration search for the Peter Millar Summer Comfort polo found used sales around £15–£25 and NWT Peter Millar polos selling roughly $36–$76 (eBay US). 973 Python tests and ten Node checks pass; not yet run against the live API.

- COST-02 (7 October, implemented_local): first live web-price run cost 5.71p / 39.8 s in total. Web search alone was 4.43p / 9.0 s (22,505 input tokens of search results + 3 searches), returned low confidence because the item was misread as women's, and did not change the price. It is now off by default (`ENABLE_WEB_PRICE=1` re-enables; code and tests kept). Prompt caching of the ~5k-token extraction instructions is now on by default (`ENABLE_PROMPT_CACHE=0` disables); the stats table shows cached tokens so cache hits can be confirmed live. Local material OCR took 17.2 s for four views although the first read was 99% clear; a clear upright read confirmed by a contrast read now stops after two views, and unclear reads still try all four. An unsupported women's guess (no women's wording on any tag, no seller hint) is flagged low-confidence for review. 976 Python tests pass.

- MEM-01 (7 October, implemented_local): live "Analyse photos again" on the VBC blazer got the server OOM-killed (Render event server_failed, oomKilled, 512Mi) at 12:24 UTC; during the restart every request returned Render's HTML page ("Unexpected token '<'" and "Could not load the latest draft"). Measured locally on Python 3.12 with the production OCR stack: app 82 MB, OCR engine 193 MB, one 2000px material-label read peaked at 815 MB because RapidOCR detects at full size above 1500px. OCR input is now capped at 1024px (peak ~420 MB), prepared-image cache cut from 8 to 2 entries, prepared images 1600px. Real-OCR label tests (previously skipped on 3.13) and the composition smoke test pass. Client now says the server is busy/restarting instead of a JSON parse error. 977 Python tests and ten Node checks pass.

- MEM-02 / PRICE-POLO-01 (7 October, implemented_local): server OOM-killed again at 12:38 UTC (polo reanalysis then blazer). Full-analysis harness on Python 3.12 with real image prep, autocrop and OCR (AI stubbed): resident memory crept ~40 MB/item and OCR detection still peaked ~220 MB above resident. Detection now capped with RapidOCR `det_limit_type=max`, `det_limit_side_len=800` (default "min 736" scaled images up), and each analysis ends with gc + malloc_trim: resident flat ~220 MB, peak ~380 MB over six items (was 540+). Real-OCR tests and smoke test pass at 800px. Polos priced £18 every time: no polo/golf rows in pricing_rules.md and no polo price memory; item type also varies ("striped shirt"). Added estimated golf-polo memory entries (Peter Millar, Galvin Green, Greyson, G/FORE, J.Lindeberg, Kjus, RLX, Castore, FootJoy, generic) with a `new_band` used for new with/without tags; brands with a polo band now match any shirt/top wording; price-guide rows added. Peter Millar NWT → £35, very good used → £25. All-caps tag names title-cased in titles. 984 Python tests, ten Node checks pass.

- SPEED-01 (7 October, implemented_local): checkpoint branch `backup/before-parallel-ocr-2026-10-07` = live f7b4622. Live Peter Millar run: 21.5 s, of which local material OCR 8.0 s ran before the ~8–9 s AI photo call although the AI only needs the label crop. The crop is now made without OCR (`label_reader.crop_only`, same thumbnail + rectification) and OCR runs in a background thread during the AI call; its result still gates composition exactly as before. Only difference: a sideways label reaches the AI unrotated (OCR orientation is no longer known in time); the existing composition gate and focused recheck still use the OCR-oriented crop. `PARALLEL_LABEL_OCR=0` restores the old order without a deploy. Harness with a 6 s stand-in AI call: 8.2–9.3 s → 7.6–7.9 s per item locally (OCR ~1 s here vs ~8 s on Render), peak memory within ~15 MB of before. 996 Python tests pass.

## 2026-10-07 — Plain listing wording
- Description Size line: no "(equivalent)" / "(label)"; "Large" label + "L" saved reads "L / Large"; other pairs "10 / 38", "UK 44R / EU 54".
- Logo / print line: no quotes or brackets ("DUNBARNIE LINKS, chest embroidery").
- Generated titles spell letter sizes as "Size Large" / "Size Small" (W32 L30, 44R, UK 9 unchanged). Seller-edited titles untouched; a size edit swaps either form.
- Existing drafts change only when regenerated.

## 2026-10-07 — Guided / Pro photo capture
- Upload page: Guided | Pro switch (remembered on the device). First camera open asks "How do you list?".
- Guided: "What is it?" (9 shapes) → "5 photos + flaws" → camera with a stitched ghost per step (Front, Back, Brand, Size, Care label),
  "Like this" example, step dots, Skip (not on Front). Shoots itself after ~0.75 s of sharp, steady, well-lit frames; blurry/dark/glare
  stills go to a Retake / Use anyway screen. Each photo gets its step's role. "All set" screen: + Flaws, Analyse (starts the listing).
- Pro: stitched frame, live quality dots, manual shots, amber "!" on weak thumbnails.
- Gallery photos are checked too; weak ones get a Blurry / Dark / Glare badge in the grid.
- All checks run on the phone (app/static/photo_quality.js): no server or AI cost. Thresholds are first guesses;
  open the app with ?camdebug=1 to see live sharp/light/glare/move values for tuning.
- Not yet: Pro multi-item batch queue ("Next item" / "Analyse N items").

## 2026-10-07 — Studio look across the app
- New shared theme `app/static/studio.css` (loaded last): light grey page, white rounded cards, one lime accent, Manrope.
- Bottom bar: floating, icon-only standard controls (no sliding pill), red counts on Drafts and Sold (sold this month).
  Counts come from a context processor in web.py (route values still win).
- Upload fits one screen: "Snap it. List it." hero with today's count, one photo stage (stitched border, deal-in animation,
  Blurry/Dark/Glare shake), one row for Guided|Pro, £ Buy and a Details button (pop-up sheet with the same fields/ids),
  lime Create listing (sheen when ready, fills while writing, burst + count +1 on success).
- Drafts/Sold: fewer words (count is just a number, "Search", short empty states, "Vinted not connected").
- Camera intro panels use the same colours.

## 2026-10-07 — No-scroll upload, onboarding
- Upload never scrolls (until a result is showing): device-backup status moved under the app name, preview note hidden on Upload,
  layout fits 667–915px tall phones.
- Onboarding at /welcome (first visit redirects there): welcome → name → how you sell → items a week → Vinted experience →
  pricing style → email (+ optional tips opt-in) → "Your plan" (daily goal, camera mode, pricing). Saved via POST /api/onboarding
  (validated) into data/user_profile.json; reseller → Pro camera, others → Guided. PATCH /api/profile can no longer set name/email.
- Profile is backed up to B2 (profile/user_profile.json) and restored after restarts; the phone also keeps a copy and restores it quietly.
- Upload count shows today / daily goal; chip turns lime when met. Animation placeholders marked "ANIM" for the gamification pass.
- Colours are tokens at the top of studio.css (--sn-*) so a natural palette can be swapped in one place.

## 2026-10-07 — Onboarding answers drive the app
- Pricing style (onboarding "What matters most?", or Details → Pricing style) now moves every price: Sell fast −10%,
  Balanced = fair price, Best price +10% — for reference bands, AI prices, web prices and own-sales medians alike
  (previously only reference bands, ±10% of band width). Upload, Reprice, Analyse again and evidence re-checks all use it.
- The price dial is centred on the item's fair price (listing.fair_price_gbp): Balanced sits in the middle, Sell fast left,
  Best price right. Condition and flaws change the £ values, not the needle.
- Camera mode comes from the profile (reseller → Pro) on every device; toggling it saves to the profile; the camera no
  longer asks "How do you list?" after onboarding. PATCH /api/profile validates choice values.
- Daily goal from items-a-week; "new to Vinted" keeps the review-page guidance.

## 2026-10-07 — Review restyle, Settings page
- Review page restyled to Studio look (review_body.html): photos first (front, back, brand, size, material order), title,
  price dial card, tap-to-edit Details rows, description, one lime "Create Vinted draft" button. Stats, confidence, eBay comps,
  tracker and error tags moved under "More". Edits auto-save on change (PATCH /listing, logged as corrections, marked manual).
- Gender ("For") and Category are now editable selects; category list comes from CATEGORY_NAV, filtered by gender.
- /settings: name, email, tips opt-in (POST /api/profile/identity, validated), pricing style, items a week (daily goal),
  camera mode, help notes, Vinted connection, redo welcome. Header avatar (initial) links there.

## 2026-10-07 — Drafts & Sold match Upload
- Upload: sized to the real visible height (in-app browser tabs report 100dvh too tall, hiding Create under the nav).
  Chip reads "15 today ✓" once the daily goal is met.
- Drafts/Sold use the Upload hero: "Drafts. 12 to check." with a count chip; "Sold. £54 so far." with a month chip.
  Removed refresh icons (pages reload when revisited), grey counts, the "Vinted not connected" banner (header pill covers it)
  and "Private preview" on every page.
- Drafts: one search pill with a filter icon (lime when filtering); cards show brand, then "type · size · age";
  premium is a small black star, needs-a-check is a red dot.
- Sold: white chart card (black line, lime fill); profit/margin/return as one row of three numbers.

## 2026-10-07 — Guided camera: manual shots, fading outline
- Guided camera never shoots by itself (it used to fire after 3 steady ticks, photographing anything).
- Each step shows the stitched outline + "Photograph the top about this size" (labels: "Care label, in focus")
  for 2s, then fades so the item is visible. Outline is stitch only: no solid edge, no shaded middle.
- The last photo pops into the bottom-left (in place of the gallery button) as the camera moves to the next step.
- Label steps: tapping the shutter waits up to 2.5s for a sharp frame ("Focusing…"); still blurry → Retake / Use anyway.
  Garment shots are kept and flagged rather than interrupting. Continuous autofocus requested where supported.

## 2026-10-07 — Small fixes
- Reprice shows one dial: the proposal replaces the current dial until Use/Keep.
- Drafts chip reads "14 drafts"; red needs-a-check dots removed from cards (premium star stays).
- Upload "Details" is a labelled pill (pencil + Details) instead of a bare sliders icon; the sheet closes on swipe-down.

## 2026-10-07 — Camera item groups
- "What is it?" is 7 groups (Tops, Coats, Bottoms, Dresses, Shoes, Hats, Other) with a short subtitle; one tap picks (no Next).
- Each group has its own 5 shots: clothes = front, back, brand, size, care label; shoes = left, right, sole, size tag, logo;
  hats = front, back, brim, inside, logo; other = front, back, side, logo, tag. Sole/brim/side use the extra photo slot.

## 2026-10-07 — Fresh CSS/JS after every deploy
- Static URLs are versioned automatically by file modified time (url_defaults), replacing hand-written ?v= tags.
  Phones were keeping the old camera script (no version) and old studio.css (?v=1 never changed).

## 2026-10-07 — "Analyse photos again" replaces the listing
- Re-analysis runs on a temporary copy (a failure leaves the listing untouched), then the result replaces the
  original listing in the same folder and the copy is deleted. No second listing is left behind.
- Kept from the original: draft link, listed date, buy price; sales history is keyed by folder so it stays.
- Same request twice (double tap/retry) returns the applied result without paying again; a failed run can be retried.
- Review shows the "Fresh photo analysis" before/after table; the drafts sheet note reads "Fresh AI read · replaces this listing".

## 2026-10-07 — Pricing style sets the needle on the band edge
- The recommended band (dial's coloured range) is centred on the fair price; Best price asks at its top edge,
  Sell fast at its bottom edge, Balanced in the middle. Band width follows evidence (±8% sales history,
  ±10% web/reference, ±15% AI-only). Previously a flat ±10% with the band centred on the asking price,
  so the needle always looked central.

## 2026-10-07 — Gamification phase 1: streaks, XP, levels, Progress page
- app/services/progress.py works out streak, best streak, XP, level and premium/hot counts from listings + sales
  (no storage, no AI). XP: list +10, full 5-photo set +5, ★ premium +15, 🔥 hot (premium and £40+) +25,
  sold +20 plus £1 profit = 1 XP. Premium = writer flag, premium brand list, or premium material.
- Streak = days in a row meeting the daily goal; stays alive until today ends (Duolingo-style).
  Levels: Rookie 0 → Trader 300 → Pro Seller 1200 → Top Seller 4000.
- /progress page (Upload style): "Day N." hero, week of flames, level bar, today/best/premium/hot tiles, how to earn.
- Drafts chip is now "🔥 streak · XP" linking to /progress; Upload's today chip links there too.
  Cards show ★ +15 or 🔥 +25.
- Fixes: today's count used file times (a backup restore made everything "today" → "17 today"); now uses saved
  creation time. Deleting a draft updates the bottom-bar count. Re-analysis keeps the original creation day.

## 2026-10-07 — MVP hardening: memory, duplicates, sign-in & privacy
- Memory (Render 512 MB; hourly peaks were 360–410 MB): the phone backup re-downloaded a zip of every
  listing on every page load — now only changed items (listings carry `backup_revision`). Backup zips are
  streamed from a temp file (not built twice in memory) and photos are stored, not re-compressed.
  Server: gunicorn.conf.py (Render runs gunicorn directly) sets max_requests=400 and malloc arena max 2.
- Duplicates: deliberate removals are recorded (data/removed_items.json, also kept in B2) so phone backups
  and cloud copies can't bring them back (restore answers 410; the phone then forgets the item).
  On startup, copies left by the old "Analyse photos again" are merged: the fresh read replaces the original
  unless the original had seller edits, a Vinted draft or a sale (then the original stays).
- Sign-in: a proper sign-in page with a 30-day session cookie replaces the browser password pop-up
  (Basic auth still accepted). Sign-in attempts are rate-limited. Settings has Sign out.
- Privacy: /privacy note; Settings → Delete my data (type DELETE) removes listings, photos, sales, profile
  and logs from the server, cloud backup and the phone. /favicon.ico no longer errors.
- Not yet: separate data per person (needed before inviting other sellers) — planned as its own job.

## 2026-10-08 — Post on Vinted hand-off; light restores on wake-up
- Hosted review page: main button is "Post on Vinted" (drafts sheet links to it). Sheet: 1 Save photos
  (phone share sheet — save or send to Vinted; downloads on desktop), 2 Open Vinted, 3 one-tap copy of
  title/description/price, plus brand/size/condition/category to pick, and "I've posted it" → marked Live.
- Cloud backup now also keeps a small summary per item (meta/<folder>.json: listing, roles, file sizes, 360px
  preview). On wake-up only summaries are downloaded; full photos are fetched the first time an item is opened
  (review, edit, reprice, analyse, photo or backup request). Summary-only items are never uploaded, and a backup
  of one is refused until its photos arrive, so nothing incomplete can overwrite a full copy.
  Item fingerprints are content-based, so phones don't re-download unchanged items after a wake-up.

## 2026-10-08 — Vinted phone-app prototype (Android)
- `android/`: minimal Java app — our site in a WebView plus a built-in Vinted window (login stays on the phone),
  "← Lister" button, JS bridge (startFill / getPayload / report / openVinted; each checks the calling site).
- `app/static/vinted_filler.js`: ports the desktop robot's steps and Vinted form IDs to in-page JS; fills, shows
  a ✓/✗ panel, and only saves when the seller taps Save draft. Tested against a mock form (11/11 steps).
- Server: `/api/vinted-fill/<folder>` (payload incl. photos as data URLs, same mappings as the robot via
  `app/services/vinted_payload.py`); `/api/vinted-fill-report` logs reports and stores a saved draft's Vinted link.
- Review page shows "Fill Vinted for me" + "Log in to Vinted" only inside the app.
- `.github/workflows/android-prototype.yml` builds the APK and attaches it to the "android-prototype" release.

## Brand: bottle green & cream + 3D XP coin
- Palette tokens in `studio.css` (bottle green #2F4A3A, cream #F3EDE0, brass #C9A45C); lime removed everywhere.
- New logo (hanger + upside-down shoe) in `brand-mark.svg`, `app-icon.svg`, PNG icons, manifest; Android adaptive icon.
- `app/static/coin.js` + `.coin*` CSS: real 3D brass coin (two faces, stacked rim, moving light/sheen, floor shadow).
  Sways and flips every ~5s; `Coin.earn(el)` fast spin + sparkles; `Coin.fly(x, y, text)` for "+10 XP".
  Used on Progress (tap to spin), the Drafts XP chip, and the upload celebration.

## Auto-delist when sold (phase 1)
- `app/services/crosslist.py`: where each item is listed (stored in listing.json "crosslist"; a Vinted draft counts
  as listed on Vinted). On a sale, `after_sale()` ends it automatically where a delister exists (eBay later) and
  returns a checklist for the rest. Vinted removal is always a manual tap.
- `POST /listing/<folder>/crosslist` {platform, action: listed|unlisted|removed}; outcome POST returns `delist`.
- Drafts sheet: "Listed on" chips, "Sold on" picker; after a sale, opens on Sold with "Take it down so it can't sell
  twice"; sold cards show "⚠ Still on …" until ticked. Tests: tests/test_crosslist.py.

## How it works tour
- `/tour` (app/templates/tour.html): 5 story-style cards animated from the app's screens (Snap it, It writes the
  listing, Into your Vinted drafts, Sold? We tidy up, Keep your streak). Auto-advance 6.5s, tap left/right, swipe,
  hold to pause, Skip. Last card "List your first item" opens the camera (`/?camera=1`).
- Welcome finishes on the tour; Settings → How it works rewatches it. Tests: tests/test_tour.py.
