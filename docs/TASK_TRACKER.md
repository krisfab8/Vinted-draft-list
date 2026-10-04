# Vinted / Dodis task tracker

Updated 2 October 2026. Canonical task list. Read `OPERATING_GUIDE.md` before changing statuses.

Priority order: private usable test → reliable state/costs → labeled model evaluation → eBay seller workflow → controlled multi-user beta → further platforms.

## Next action

**Verify single-pass generation on representative phone photos.**
Read `SPEED_COST_20261004.md`; 808 automated checks passed. The normal path
uses one vision response plus deterministic copy; real latency/cost and quality
comparison remain required. No twenty-item labeled photo set is available.

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

- UI-03b live deployment: c2d3dbf / dep-db18i1lg1s2s739cvceg live 17:13:57 UTC. Authenticated HTTPS serves the new camera dialog and getUserMedia script. Existing one-item server backup retained and restored (upload_5a206d59); independent saved ZIP retained. No AI calls. Physical phone preview/capture/switch/gallery and visual QA remain to be confirmed; cloud browser blocked by client policy.
