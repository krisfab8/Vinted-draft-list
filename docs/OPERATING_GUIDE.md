# Vinted / Dodis operating guide

Updated 2 October 2026. This is the working contract for continuing the project with Codex, Claude Code or another developer.

## Purpose

Turn clothing photos into accurate, editable listings, with low running cost and clear seller control. Begin with Vinted review/drafts; add eBay publishing through its official seller APIs; extend to other platforms only through verified integrations or clear manual export.

Target users: Kristian first, then a small UK clothing-reseller beta. Target economics: complete automated analysis and copy below £0.01 per successful item where possible, measured from actual calls. Accuracy and correction time matter alongside cost. Never advertise that target as guaranteed until measured, including failed calls and retries.

## Read order and source of truth

1. Root `AGENTS.md` and `CLAUDE.md`: existing project constraints.
2. This guide: working process and current direction.
3. `docs/TASK_TRACKER.md`: current status and exact next task.
4. Relevant source and tests: actual behavior overrides descriptions of old behavior.
5. `docs/CROSS_PLATFORM_ROADMAP.md`: future product direction.
6. `docs/PRIVATE_TEST_DEPLOYMENT.md`: hosted/local capabilities and deployment steps.

`listing.json` remains item truth for the existing single-operator app; SQLite is an index/tracker. Do not introduce a second authoritative item representation accidentally. Multi-user inventory needs a deliberate migration later.

## Current state

- Reviewed base: `c160b70afa60176d15357922232f0bc22c8b0602` (26 April 2026).
- Existing baseline suite: 760 passing tests during the review.
- Original hosted branch: `work/vinted-revival-plan`. Cost/measurement development is isolated on `work/vinted-cost-measurements`; see `COST_MEASUREMENT_IMPLEMENTATION.md` for checkpoints, tests and limitations.
- Added opt-in OpenAI image extraction and listing writing. Defaults remain Haiku for local users; current hosted configuration selects Claude Haiku for both stages.
- Added private, password-protected single-operator hosting entry point, durable-storage bootstrap and Render blueprint.
- Vinted browser actions are blocked in this hosted test. Continue those in the local app until a real remote session architecture exists.
- Quality/cache/eBay research, cost target and storage incident: `QUALITY_COST_AND_EBAY_20261003.md`.
- Phone latency/validation diagnostics and rollback: `LATENCY_AND_VALIDATION_FIX.md`.
- Model calls are mocked in automated checks. No claim of real Luna OCR performance, sub-penny cost, successful deployment or live Vinted/eBay integration follows from those checks.
- Prior review bugs remain open unless the tracker states the specific acceptance criteria were met. A hosting guard is not a complete app-wide security fix.

## Workflow for each change

1. Choose one stable task ID from the tracker. Confirm dependencies and read affected code.
2. Reproduce the problem or define the observable outcome.
3. Make the smallest complete change that achieves that outcome. Preserve unrelated work.
4. Test the behavior through the real service/route where interaction matters; avoid tests that merely repeat the implementation.
5. Run the relevant existing checks. Run the whole suite before handoff of a behavior change.
6. Update the task row with status, evidence, limitations and the next action. Record decisions only when they change a future choice.
7. Commit to the working branch and keep the change reviewable. Do not mark deployed until the actual URL and deployed commit are verified.

Statuses: `todo`, `in_progress`, `implemented_local`, `verified_live`, `blocked`, `deferred`. “Implemented locally” is different from live verification or completion of a whole phase.

## Invariants

- Keep user corrections, purchase cost, locks and confirmed values authoritative in code.
- Reprice proposes price changes; it must not rewrite unrelated approved copy.
- Validate the fully assembled listing before persistence and browser/API writes.
- A draft is successful only with positive platform save evidence and a stored platform identity.
- Never equate active asking prices with accepted transaction prices.
- Keep seller proceeds separate from buyer checkout fees; use platform-specific actual fees.
- Every model response and paid tool call belongs in a usage ledger, including failure/retry accounting where observable.
- No paid model fallback happens silently. Bound attempts and route unresolved evidence to review.
- Credentials remain server-side/local secrets, never repository content or browser bundles.
- Existing single-user state must never become shared multi-user state by adding a sign-up page alone.
- Cross-platform writes require confirmed seller account and explicit publication intent. Uploading photos is not authorization to publish.
- Do not publish onto multiple platforms before sell-through reconciliation and duplicate/oversell protections are ready.

## Model testing policy

Start Luna with `reasoning=none` and controlled output limits. Preserve Haiku as a comparison baseline. Use the same originals and ground truth; log preprocessing/model/prompt versions. Compare brand/size/material accuracy, false claims, correction time, latency, cost per successful item and fallback rate. A cheaper model is accepted only if it meets the agreed accuracy/correction threshold.

Current Luna adapter is a single pass; Claude rereads/escalation are not invoked in the OpenAI path. Missing evidence needs operator review. JSON-object output is not schema-constrained output; existing validators still apply. Whole-account spending and provider invoices remain authoritative until the complete ledger is implemented.

## Handoff format

For each session, record: task IDs, changed behavior, checks and results, deployed commit/URL if any, unresolved blockers and the next task. Never claim API or browser success from a mock.

Starter prompt:

```text
Read AGENTS.md, CLAUDE.md, docs/OPERATING_GUIDE.md and docs/TASK_TRACKER.md.
Work on task [ID]. Inspect the relevant source and reproduce the issue first.
Preserve confirmed edits and existing response shapes. Implement a focused change.
Run relevant tests, update the tracker with evidence and limitations, and commit
to a reviewable branch. Do not claim live verification unless it actually ran.
```
