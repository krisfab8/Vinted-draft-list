# Device draft backup and compact feedback — 4 October 2026

Tasks HOST-03a / REVIEW-02 / UI-02. Current free Render instance is ephemeral. No paid plan or disk provisioned.

## Behavior

Private hosted pages save per-item ZIP archives in IndexedDB in the current browser/origin. Archives contain prepared upload photos (not full-resolution camera originals), listing.json, role assignments, usage events and, when available, analysis.json and feedback.json. Startup restores missing server items, never overwrites existing ones, and refreshes the Drafts page after restoration. Successful uploads and edits queue a backup without delaying the generation result. In-app navigation waits for queued work. A restored back-navigation Drafts page reloads to avoid a stale browser-history snapshot. Deletion records a device tombstone. Errors show an actionable backup warning rather than claiming success.

This is a device safety net, not shared durable cloud storage. Clearing site data, private browsing, browser eviction, closing before saving finishes or another phone can lose/access a different archive. A download link remains under a folded backup section. Open the app in the same browser and wait for “Backed up on this device” before closing. Operator review can read the restored server copies without paid generation. Cross-device server persistence still needs storage outside the free instance. Avoid testing automatic restart recovery by destructively deleting actual user data.

New generations snapshot initial listing, costs and extraction/write metadata before edits. Existing items capture their available saved result on first feedback/edit, not a recovered historical raw response. Feedback stays separate from listing.json and preserves issue categories and notes. It does not change price/copy, train a model, or make AI calls. Existing Reprice/Regenerate actions still use their prior AI behavior; this change does not make them free.

Measurements and eBay research are collapsed by default. Feedback uses one collapsed pencil-labelled section. Draft cards link to the existing edit flow. Broader UI work is intentionally deferred to the user's separate UI chat.

## Verification

820 Python tests passed (26.35 s), including real Flask feedback roundtrip/validation and archive restore preserving photos, original evidence and corrected current listing. Node archive checks use a simulated IndexedDB/fetch environment to verify restoration, server-copy precedence, tombstones, and quota/download failures. Existing upload/measurement/preparation checks and inline JS syntax pass. Real Android IndexedDB/navigation behavior still needs phone verification. No AI calls used for these checks.

Live deploy and existing-item restoration evidence will be recorded in the task tracker after verification.


Live verification: Render deployment dep-db15ab3tqb8s738ve8tg served commit 6063dd33bee26dbf3ef77fa13566276ad7685de1 at https://vinted-measurements-test.onrender.com/. Authenticated HTTP checks verified latest archive script, folded controls, draft/edit link, feedback read, invalid-feedback 422, and ZIP export containing listing/evidence/feedback and both label photos. Pre-deploy server backup was already empty: recovered upload_5a206d59 from previously retrieved listing/run ledger and the two user-attached label photos; front/model-size photos remain missing and flagged. Restore returned 200. Original price/copy kept unchanged; feedback records the fabric/price regression. Usage ledger retained exactly the original one call; no new paid generation. Real Android IndexedDB and back-navigation validation remains pending. Live evidence is recorded on a separate documentation branch so another documentation deploy cannot clear the restored free-host data.
