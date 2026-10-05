# MVP priority implementation — 5 October 2026

Status: implemented locally and regression checked; not deployed.
Base: 49bb1fdf5d27f1b802554be7cd3470388454e3e6 on work/vinted-cost-measurements.
Working branch: work/vinted-mvp-priorities. The source-of-truth item remains listing.json.

## Resulting behavior

- Listing writes use unique temporary files, fsync and atomic replacement. Per-item thread/process locks cover reads and mutations; a stale If-Match revision returns 409 before writing or invoking paid generation. Browser saves queue per item and retain unsaved text on conflicts. Revision includes sale state. Inventory/listing responses use no-store.
- PATCH accepts only editable facts, validates values and the assembled listing, protects changed manual fields, records asking-price changes, and recalculates informational profit. Internal state and arbitrary cost/draft fields cannot be edited. Existing original analysis is retained.
- Regeneration preserves manually edited facts, wording, purchase cost, confirmation flags, measurements and market evidence. Older manual edits are inferred from original analysis. An explicit checkbox permits replacing edited title/description. Saved price stays unchanged; a price proposal is separate. Failed generation does not save partial changes. Regeneration uses the existing model usage context and adds costs to the item record.
- Check price is a deterministic saved-facts/reference/confirmed-sales operation with no AI call. It changes neither chosen price nor approved copy. Use this price explicitly accepts a proposal. This does not perform a new market lookup.
- Drafts exposes inventory search and filters for draft/live/sold/withdrawn/returned. Sale saves update the card and reload the sheet. Sold status survives subsequent listing corrections.
- Matching sale evidence shows recent examples, sample count, range and median time to sell. Composition percentages and recorded flaws must match; low-confidence brand/material/model/cloth evidence is excluded. Existing match indexes are rebuilt at signature version 2 without changing sale payloads.
- Missing publication/purchase/selling-cost values are preserved on partial lifecycle updates; explicit blank remains unknown. Sale snapshots include confirmed measurements.
- The eBay summary exposes not checked/checked/unavailable/previous result states and disables duplicate lookup clicks. Asking-price evidence remains separate from seller-entered sold research.

## Verification

880 Python checks passed. Nine Node UI checks cover archive recovery, fresh-sheet races, camera/gallery, measurements, photo preparation, uploads, market safety and the new queued-save/stale-tab protocol. Providers are mocked: no paid generation, fabricated live sales, or Vinted publication was performed. Browser-rendered/live verification is still pending.

## Deployment boundary

Render test service srv-db02nhmgekts73fuv4bg still uses the free plan with disposable files. Current live records/photos must be backed up before restarting/deploying; device backups are helpful but are not shared permanent storage. The browser could not access the authenticated test app for backup retrieval. Do not advance the auto-deploy branch until a current backup is available. This change does not provision paid storage, introduce multi-user pooling or change model recognition.

Saved style preferences and background/batch listing are deferred to a subsequent change. Cross-user pooling needs account isolation and contributor controls.
