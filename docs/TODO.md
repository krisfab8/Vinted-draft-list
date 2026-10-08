# To-do (owner's list)

Newest at the top. Move items to TASK_TRACKER.md when done.

## Main route to launch: phone app that fills Vinted drafts (no computer needed)
- [~] **Vinted prototype (Android)** — app with a built-in Vinted window: log in once on the phone, tap
  "Fill Vinted for me", it fills the sell form (photos, category, title, description, brand, size, condition,
  colour, material, price, parcel); seller checks and taps Save draft. Built from `android/` by GitHub Actions
  (release "android-prototype"). NEXT: install on a real phone and read the fill report (Render logs /
  data/vinted_fill_reports.jsonl) to see which fields Vinted's mobile site accepts.
- **eBay connect + listing** via eBay's official API (works from any phone, no robot).
- **Publish Android app** to Google Play ($25 one-off); iPhone later ($99/year, stricter review).

## Next up
- **Run the app on your own computer for free testing** — one-command start + free Cloudflare Tunnel
  (secure web address for the phone), photos stored on your own disk, Vinted draft robot switched back on
  (it fills the Vinted listing form and saves a draft using your own login). Needs: Mac or Windows?
- **eBay cross-listing** — use eBay's official selling API (not a robot): same item → eBay listing with
  photos, category, item specifics (brand, size, colour, department), price; when it sells on one platform,
  end it on the other. Needs a free eBay developer account and one-time "connect eBay" sign-in.

## From competitor research (see docs/COMPETITORS.md)
- [~] **Auto-delist when sold** — DONE: "Listed on" chips per item, "Sold on" picker, and after a sale a
  "Take it down" checklist plus a "⚠ Still on …" badge until ticked (`app/services/crosslist.py`).
  NEXT: register an eBay delister in `crosslist.DELISTERS` once eBay is connected (ends it automatically),
  and listen for eBay sale notices so selling on eBay marks it sold here.
- **Depop via its official partner API** — invitation only: email Depop's partner team (Vendoo got in in 2026).
  Safest second platform for clothing.
- **Price per platform** — show each platform's fees and suggest a price for each (eBay vs Vinted buyers differ).
- **Refresh stale listings + import existing listings** (Vendoo charges $4.99/month for each).
- **Our pricing** — free tier of ~10 items/month, then cheaper than rivals' $29 entry plans.
- Keep Vinted human-tapped only: no bulk or background posting (Vinted is suspending automated accounts).

## Later
- Separate data per person (before inviting other sellers).
- Switch cloud photo storage to Cloudflare R2 (free downloads, 10 GB free).
- Chrome extension that fills Vinted drafts in each user's own browser (multi-user Vinted drafting).
- Free bigger server for testers: Oracle Cloud "Always Free" (or ~£4/month VPS).
- Installable web app (home-screen icon, no browser bar); logo; natural palette; gamification phase 2.
