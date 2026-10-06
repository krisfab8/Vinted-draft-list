# ACC-03: readable garment markings — 6 October 2026

User requested exterior words/logos, including unfamiliar club/company names, in descriptions. Brand-label keywords alone previously did not explicitly require these words, and the writer could omit them.

Extraction now explicitly asks for exact exterior embroidery/logo/badge/print/slogan wording and its location with confidence per entry. Unfamiliar wording is not corrected via a known-name dictionary, promoted to the maker/model, or used to claim affiliation. The existing vision call performs this scan; no additional model call or image upload is introduced.

A separate garment_text evidence field survives both compact and legacy writers. High-confidence words are deterministically included in a Logo / print description detail, independent of the writer remembering them. Unicode, multiple markings and duplicate suppression are supported. Uncertain transcriptions stay in saved evidence with a review flag and are excluded from writer input/copy; exact uncertain candidates reintroduced by the writer are stripped. Seller-written description preservation remains authoritative.

903 Python tests and nine Node checks passed. Tests exercise the real writer service under both modes with mocked responses deliberately omitting the marking, repeatable description formatting, multiple/unfamiliar/Unicode words and uncertainty withholding. Dunbarney Golf Club is illustrative test wording from the user's tentative example, not a verified transcription of the original shirt. No paid photo reread or accuracy/cost measurement was performed. Small logo text still needs a sharp photo; this change cannot guarantee the model reads every marking.

Existing listings are not automatically changed. Source deployment follows; actual source SHA/live status will be recorded separately. Authenticated live browser access remains blocked in this environment.

Render confirmed source e49d6808adbb7eac4fd26389e68d788b66e1578c live on dep-db2agruq1p3s73ef2g8g at 07:52:20 UTC on 6 October, https://vinted-measurements-test.onrender.com. This verifies deployed source/status only; no paid-photo rerun or authenticated live UI verification occurred.
