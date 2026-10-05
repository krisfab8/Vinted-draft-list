# UI-05: Stockroom design

5 October 2026. Original UI preserved on GitHub branch `backup/ui-before-redesign-2026-10-05`, commit `6d024dfcd111a146ef4cd5fa9ad61b89251090aa`.

## Design
Warm off-white, charcoal and deep teal; one shared stylesheet loaded after screen-specific CSS. Less chrome and explanatory text, compact monthly sales summary, photograph-first cards. Three mobile bottom tabs remain; desktop navigation moves into the header. Responsive inventory uses two columns on mobile, three on tablet, four on desktop. Upload becomes a two-column form on wider screens.

Private-test model details are expandable. Important error, confidence and known-cost information remains available. Month/year selection and sale calculations retain existing backend behavior. Sold keeps its red label and no duplicate card status text.

Deletion moves inside the item sheet, with existing confirmation. Deleted items are tombstoned in the in-page array rather than spliced: surviving cards retain their original index and cannot open another item. Sheet supports keyboard opening, Escape, focus containment and return focus. Page zoom is permitted. Safe-area spacing supports phone navigation.

## Verification
- 885 Python tests passed; two existing mocked Anthropic cleanup warnings.
- Nine existing Node checks passed; draft refresh check extended to cover deletion identity.
- Actual Flask Upload/Drafts/Sold responses returned 200 and inline JavaScript passed Node syntax checks.
- Chromium fixture renders at 320, 390, 768 and 1440px passed horizontal overflow checks across all three screens.
- Phone Upload primary action sits above bottom navigation at 390x844.
- Browser checks passed keyboard opening/dismissal/focus, sale amount and purchase-cost entry, search, confirmed deletion and subsequent correct item opening.
- Screenshots inspected for phone Upload, Sold, sale form, desktop Upload and Drafts.
- QA used isolated backup-based fixtures with sample sale values; nothing was written to live inventory/history, and no paid generation was invoked. Browser font checks used system fallback fonts because external font loading was disabled during fixture testing.

Actual Android/iOS camera, software keyboard and installed-app safe areas still require device validation. Existing provider and marketplace restrictions remain. Render live status is recorded separately; local checks alone do not prove deployment.
