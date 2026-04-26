# Vinted App Prompt Library For Codex And Claude

Use these prompts when working on the Vinted app frontend, UI, workflow, or audits.

## 1. Frontend Audit

```text
You are working in my Vinted Draft Listing App repo.

First read `AGENTS.md` and `docs/FRONTEND_DESIGN_BRIEF.md`. Then inspect the current frontend files before making recommendations.

Audit the frontend/UI for:
- review queue clarity
- item review speed
- pricing/profit visibility
- confidence and warning visibility
- Vinted draft/auth error visibility
- mobile upload/review usability
- visual quality and hierarchy

Return findings first, ordered by severity, with file references. Then propose the smallest useful implementation patch.
Do not make generic design comments. Tie every finding to a real workflow problem in this app.
```

## 2. Review Queue Redesign

```text
You are working in my Vinted Draft Listing App repo.

Read `AGENTS.md` and `docs/FRONTEND_DESIGN_BRIEF.md` first.

Improve the review queue so it feels like a reseller listing cockpit.

Requirements:
- Product-photo-first card layout.
- Filter chips for Needs review, Ready, Draft failed, Draft created, Low confidence, Low margin.
- Each card shows title, brand, price, estimated profit, confidence, warning/error chips, and next action.
- Draft failures and auth issues must be visible without opening the item.
- Mobile layout must be usable.
- Preserve existing backend contracts and route response shapes.
- Reuse existing data fields from `listing.json` and item status service.
- Add or update tests/checks where practical.

Implement the change and summarise changed files.
```

## 3. Item Review Page Redesign

```text
You are working in my Vinted Draft Listing App repo.

Read `AGENTS.md` and `docs/FRONTEND_DESIGN_BRIEF.md` first.

Improve the item review page.

Goal:
Make it faster to check, correct, price, and create a Vinted draft.

Requirements:
- Product photos are prominent.
- Editable listing fields are grouped clearly.
- Confidence badges sit near relevant fields.
- Warnings and error tags are visible and actionable.
- Pricing/profit panel shows current price, suggested price, estimated profit, and warning state.
- Draft state shows draft URL, draft error, or auth required.
- Regenerate/reprice must preserve user-edited fields and respect locks.
- Mobile layout must stack cleanly.
- Preserve current backend behaviour.

Implement the smallest complete improvement and run relevant checks.
```

## 4. Pricing UI Patch

```text
You are working in my Vinted Draft Listing App repo.

Read `AGENTS.md` first.

Improve the pricing/profit UI only.

Requirements:
- Show current price, suggested price, estimated profit, buy price, profit multiple, and eBay range if available.
- Show a clear warning for low margin or thin margin.
- Explain why the suggested price exists.
- Do not silently overwrite user price.
- Make accepting a suggested price explicit.
- Keep current pricing backend behaviour unless a bug is found.
- Add a narrow test/check if behaviour changes.

Implement and summarise.
```

## 5. Upload Flow Mobile Fix

```text
You are working in my Vinted Draft Listing App repo.

Read `AGENTS.md` first.

Fix/improve the mobile upload flow.

Problem:
On mobile, the photo upload should allow choosing from the photo library as well as taking a new photo, similar to Vinted.

Requirements:
- Inspect current upload input/component.
- Ensure mobile users can choose existing photos and/or camera where browser support allows.
- Preserve multiple photo selection.
- Keep resizing/compression pipeline intact.
- Improve helper text/error states if needed.
- Test the narrowest relevant path.

Implement and summarise changed files.
```

## 6. Codex Implementation Prompt

```text
You are working in my Vinted Draft Listing App repo.

Use `AGENTS.md` as the main project context and `docs/FRONTEND_DESIGN_BRIEF.md` for UI direction.

Task:
[insert exact task]

Rules:
- Deliver working code, not just a plan.
- Read relevant files before editing.
- Preserve existing response shapes unless necessary.
- Preserve user-edited listing fields during regen/reprice.
- Surface confidence, warnings, profit flags, draft errors, and auth state clearly.
- Avoid generic purple SaaS styling.
- Add/update tests where behaviour changes.
- Run the narrowest relevant checks available.
- Do not revert unrelated changes.

Final response:
- What changed.
- Files changed.
- What checks ran.
- Any risks or follow-up.
```

## 7. Claude Design/Planning Prompt

```text
You are helping redesign my Vinted Draft Listing App frontend.

Use this context:
- `AGENTS.md`
- `docs/FRONTEND_DESIGN_BRIEF.md`
- Current screenshots or files I provide

Act as a senior product designer and frontend engineer.

Task:
[insert screen or workflow]

Return:
- The main UX problems.
- A better layout concept.
- Specific component changes.
- What data should be shown where.
- A concise implementation prompt I can give to Codex.

Avoid generic design advice. Make it specific to Vinted draft review, pricing confidence, errors, and fast reseller workflow.
```
