# Agent map — read this instead of exploring

## Run things
- Tests: `python -m pytest -q` (≈1 min) + `for f in tests/check_*.cjs; do node $f; done`
  (fresh session: `pip install -r requirements.txt pytest` first if pytest is missing).
- Only changed area: `python -m pytest -q tests/test_<area>.py`.
- QA in a browser: Playwright with `executable_path='/opt/pw-browsers/chromium'`, viewport 375×740,
  serve with `python -c "from app.web import app; app.run(port=5055)"` on a copy of the repo.
- Deploy: push `HEAD:claude/friendly-goodall-hqvukz HEAD:work/vinted-cost-measurements`.
  Render auto-deploys `work/vinted-cost-measurements` (service srv-db02nhmgekts73fuv4bg,
  workspace tea-d9m7o3flk1mc739tlcsg), ~2 min. Check with Render `list_deploys` before saying "live".
- Never push to krisfab8/vinted-app (different repo). Never ask for or paste API keys.

## Where things are
| Area | Files |
|---|---|
| Upload page + camera UI | `app/templates/index.html`, `app/static/camera_capture.js`, `photo_quality.js` |
| Drafts + Sold pages | `app/templates/drafts.html` (one template, `sold_mode`) |
| Review page | `app/templates/review.html` (scripts) + `review_body.html` (markup) |
| Settings / onboarding | `settings.html`, `onboarding.html`, `app/services/user_profile.py` |
| Progress (streaks/XP) | `app/services/progress.py`, `app/templates/progress.html` |
| Theme / styles | `app/static/studio.css` (loaded last; tokens `--sn-*` at top) |
| Pricing + dial | `app/services/pricing.py` (style = band edge), `app/static/price_gauge.js` |
| Routes | `app/web.py` (high sensitivity) |
| Re-analysis | `/reanalyze` in `web.py` + `app/services/photo_reanalysis.py` |
| Sign-in, removals, delete-my-data | `app/hosted.py`, `app/services/removed_items.py`, `account_data.py`, `signin.html`, `privacy.html` |
| Cloud backup + light restore | `app/services/cloud_store.py` (hydrate), `item_backup.py` (summary, stub helpers) |
| Draft automation | `app/draft_creator.py` (fragile — minimal edits only) |
| Change log | `docs/TASK_TRACKER.md` (append one short entry per change) |

## House rules learned
- Static files are auto-versioned (`url_defaults` in web.py) — no manual `?v=`.
- No Jinja inside `<script>` in index.html (tests/check_market_ui.cjs fails).
- Cards: 2 wide on phones. Upload page must not scroll. Few words, Studio look.
- The item request lock is taken in `serialize_item_requests`; don't lock the same folder again.
