# UI-06: Resale studio redesign

6 October 2026. Previous stockroom design preserved remotely at `backup/stockroom-ui-2026-10-05`, commit `5bae260a1373add40644efda575e44b5320b331f`. Original UI remains at `backup/ui-before-redesign-2026-10-05`.

## Result
Cobalt, coral and white visual identity, native SVG resale-tag logo and illustrated photo upload. Tactile primary buttons and compact photo-first inventory retain three mobile bottom tabs and desktop header navigation. Red draft count and SOLD labels remain. Sales and profit are switchable cumulative monthly line charts; a ring shows profit versus purchase cost. Short metric labels replace the large text-heavy panel; accessible daily values and calculation explanations sit under Details.

Charts use confirmed history only, with no forecasts or sample live transactions. Current-month series stops at the UK current day; past months include the complete calendar month. Profit remains before fees and seller-paid postage. Unknown purchase costs are excluded rather than invented as zero. Margin is gross profit / known-cost revenue; return on cost is gross profit / purchase cost. Losses and unknown costs have separate ring states. Existing sale dates, purchase costs and seller edits are preserved.

Thumbnail selection ignores stale saved URLs and tries an existing front, back or brand photo. An unavailable-photo illustration handles missing files and browser image failures. No generation or paid model calls were added.

## Evidence
- Full suite rerun 6 October: 888 Python tests passed, with two existing mocked Anthropic destructor warnings.
- All nine Node UI checks passed; chart JavaScript syntax and git whitespace checks passed.
- Earlier isolated Chromium fixtures covered Upload, Drafts and Sold at 320/390/768/1440px without horizontal overflow. Chart toggle, missing-photo fallback, keyboard sheet handling, sale input, search and deletion identity passed. Fixtures did not modify live inventory or create live transactions.
- Final chart axis metadata and mobile spacing were subsequently refined. Toggle targets are at least 44px high. Final templates and inline JavaScript rendered and checked again 6 October. Final Chromium checks passed all 12 layouts and chart switching at all four widths; phone Upload/Sold and desktop Sold screenshots inspected.
- Actual phone camera, keyboard and installed-app safe areas remain device validation. Render deployment status must be checked against the new commit separately; local checks do not establish live success.
