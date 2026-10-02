# Vinted / Dodis task tracker

Updated 2 October 2026. Canonical task list. Read `OPERATING_GUIDE.md` before changing statuses.

Priority order: private usable test → reliable state/costs → labeled model evaluation → eBay seller workflow → controlled multi-user beta → further platforms.

## Next action

**Replace the exposed Claude API key privately in Render, then retry a phone upload after the whitespace/error-redaction patch deploys.** Hosted vision and listing providers now select `claude-haiku`; OpenAI remains an optional comparison configuration. The private test is live at https://vinted-private-test.onrender.com (service srv-davmdce7bikc73eknv00). It uses free native Python hosting with temporary storage at /tmp/vinted-test-data; uploads/state can be lost on restart or redeploy. The paid disk blueprint remains an optional future configuration, not the deployed setup. Compare Luna against labeled photos before selecting it as the production default.

## Foundation and testing

| ID | Priority | Task | Status | Acceptance / dependency |
|---|---|---|---|---|
| DOC-01 | P0 | Operating guide and stable task list | implemented_local | Documents checked in with statuses, dependencies and handoff process |
| DOC-02 | P0 | eBay/multi-platform product roadmap | implemented_local | Shared inventory, platform boundaries and phased acceptance criteria documented |
| HOST-01 | P0 | Prepare private test deployment | implemented_local | Password gate; containment checks; browser actions disabled; persistent-state bootstrap; tests pass |
| HOST-02 | P0 | Deploy and verify private HTTPS URL | in_progress | HTTPS/authenticated UI verified live on free hosting; provider key, real upload and durable storage remain outstanding |
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
| HOST-02b | P0 | Private provider configuration diagnostics | implemented_local | Password-gated /api/provider-status reports readiness without key values; upload errors name missing key or unsupported provider setting; 768 tests passed; live diagnosis pending |
| SEC-02 | P1 | Multi-user identity and ownership | todo | Before inviting unrelated sellers: independent items, credentials, memory and requests; CSRF/rate limits/security review |
| HOST-03 | P2 | Remote Vinted session architecture | todo | Supported login, isolated session, recoverable expiry and verified save; no assumption headless alone is enough |
| HOST-04 | P1 | Persisted job queue and progress | todo | Bounded background jobs; truthful progress; restart recovery; avoid blocking all users |

## Images and recognition

| ID | Priority | Task | Status | Acceptance / dependency |
|---|---|---|---|---|
| IMG-01 | P1 | Apply phone EXIF orientation | todo | Portrait/landscape orientation corrected before stripping EXIF; real rotated fixture |
| IMG-02 | P1 | Explicit photo roles and correct manifest | todo | User roles transmitted/preserved; missing size photo cannot silently shift material role |
| IMG-03 | P1 | Preserve OCR originals and crop review | todo | Lossless/original source retained; crop edits; retry can use uncropped source |
| IMG-04 | P1 | Analyze supplied damage/back evidence | todo | Explicit cost policy; checked-photo provenance; flaws visible only there reach review |
| IMG-05 | P1 | Validate actual upload bytes | todo | Corrupt/oversized/decompression-risk images rejected without broken folders; useful errors |

## Costs and pricing

| ID | Priority | Task | Status | Acceptance / dependency |
|---|---|---|---|---|
| COST-00 | P0 | Correct test rates and persist upload costs | implemented_local | Haiku 4.5 rates corrected; Luna/Sol rates added; upload costs saved; not a full ledger |
| COST-01 | P0 | Complete per-call usage ledger | todo | Initial calls, escalation, rereads, regeneration and incomplete billable responses retained; provider reconciliation |
| COST-02 | P0 | Correct lifetime spend totals | todo | Sum every event; separate latest run/item lifetime/account totals; no per-folder deduplication |
| COST-03 | P1 | Enforce cost budgets before calls | todo | COST-01; bounded output/attempts + estimated image cost; explicit over-budget review; rate/FX/version recorded |
| PRICE-01 | P0 | Correct seller proceeds calculation | todo | Vinted buyer fee not deducted from seller; seller expenses explicit; stats use same service |
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

## Update rules

Keep IDs stable. Do not rename an open task to hide scope. Split partial work into a subtask rather than marking the parent complete. Record the commit, test and live outcome when relevant. After each session, replace “Next action” with the actual next dependency. Preserve blockers and known regressions.
