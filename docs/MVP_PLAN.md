# MVP plan — what's left before inviting testers

Short, living checklist. Read this instead of old chats. Tick items as they ship.
Status: [ ] to do · [~] in progress · [x] done · [!] waiting on owner/outside

## 1. Protect the wallet (before anyone else uses it)
- [x] Monthly AI spend cap for the whole app (owner sets £/month in Settings; new listings pause when reached)
- [x] Free listings per seller per month (owner sets the number; owner is unlimited)
- [x] Usage shown in Settings: owner sees spend + each seller; sellers see "12 of 30 this month"

## 2. Finish accounts
- [x] Owner can remove a seller (stops sign-in; data kept until deleted)
- [x] Password reset: owner makes a one-time reset link for a seller; sellers can change their password
- [x] Privacy note: accounts, passwords (add price pooling when that starts)

## 3. Prove the core loop on a real phone
- [!] Vinted fill on a real draft in the app (owner to test with app 0.1.21+)
- [ ] "Report a problem" button (sends the item + what went wrong to the logs)

## 4. Ready for testers on Android
- [ ] App name + icon final, version shown in Settings (done: 0.1.x)
- [ ] Play Store internal testing track: private release signing key (not the test key), privacy URL
- [ ] Own web address (optional) instead of onrender.com

## 5. eBay (blocked on eBay developer approval)
- [!] eBay developer account approved (owner appealing/reapplying)
- [ ] eBay setup pages (account-deletion notices, /ebay/callback) → "Connect eBay"
- [ ] List an item on eBay from the app; auto-end on eBay when it sells on Vinted
- [ ] Plan B if eBay says no: "Export for eBay" CSV for Seller Hub bulk upload

## After MVP (ideas, not blocking)
- Scout / "Should I buy it?" checker (separate icon, shares the backend; see chat notes in docs/COMPETITORS.md)
- Anonymous price pooling (start collecting early so Scout has data)
- One-tap price drop and Vinted take-down; price per platform; tax export; weekly leaderboard
- Cheaper storage (Cloudflare R2); Depop partner email

## Done recently
- Limits (budget + free listings per seller), remove seller, reset links, change password, UK-day dates fix
- Seller accounts with separate data (invite links) · Insights page (visual, sell-through)
- Vinted/eBay login helper in the app · fixed app signing so updates install over the top
