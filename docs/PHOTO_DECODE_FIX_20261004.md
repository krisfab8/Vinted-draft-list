# Android photo decode failure — 4 October 2026

User screenshot: correct Upload/Create Listing screen; error `The source image
cannot be decoded.` Father was using Android. The exact original photo and
browser are unavailable, so its specific codec/corruption cause is unconfirmed.

The client Image.decode rejection was surfaced verbatim before /upload. Add
fallback /prepare-photo: decode original bytes with Pillow plus HEIF support,
apply orientation, resize to 2048px, return JPEG. This makes no model request
and saves no listing. Auth remains the existing hosted password gate.

Valid photos still use the existing phone preparation path. Converted previews
display the prepared image while roles/order remain tied to the selected file.
Failed promises are evicted so retries are possible. Errors identify photo
number and role, explain replacement/sign-in/connection actions and remain escaped.

Fallback caps bytes and decoded pixels, checks image format and rejects corrupt
files before AI work. No new paid model retry is introduced. Exception handling
does not promise recovery of a file whose original bytes are unavailable/corrupt.

Automated evidence: real Flask conversion tests for JPEG, PNG, WebP, HEIF;
EXIF/resize, corruption, missing/oversized files and no AI work. Node checks
cover browser decode failure, fallback JPEG, actionable error/auth failure,
prepared-image reuse and retry after rejection. Live conversion and deployment
must be verified separately. Father's exact phone file still needs a retest.

Full suite: 818 passed in 18.16s; both Node upload checks and inline JS syntax pass.
Pre-deploy authenticated backup returned HTTP 200 with an empty item archive.
