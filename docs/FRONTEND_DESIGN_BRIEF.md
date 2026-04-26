# Vinted App Frontend Design Brief

This file is intended to live at `docs/FRONTEND_DESIGN_BRIEF.md`.

Use it with Codex, Claude Code, or ChatGPT when redesigning or auditing the Vinted app frontend.

## Design Mission

The Vinted app should feel like a premium, fast, practical listing cockpit for a clothing reseller.

It should help the user rapidly decide:

- Is this listing good enough?
- Is the price worth it?
- What needs fixing?
- Can I create the Vinted draft now?
- Did anything fail?

The interface should reduce thinking load, not add more admin.

## Product Personality

The app is not a generic dashboard. It should feel:

- Practical
- Confident
- Reseller-focused
- Slightly tactile
- Fast to scan
- Built around clothing photos
- Optimised for review decisions

Good metaphors:

- Curated stockroom
- Reseller command centre
- Listing cockpit
- Product card sorting table
- Thrift intelligence layer

Avoid:

- Plain Bootstrap/admin templates
- Generic blue SaaS dashboards
- Purple AI gradients
- Overly dark cyber dashboards
- Tiny spreadsheet-like tables as the main UX

## Visual Direction

Recommended direction:

- Background: warm off-white, cream, stone, or very light grey.
- Text: deep charcoal/ink.
- Cards: white or warm paper with subtle borders/shadows.
- Success: muted green.
- Warning/review: amber or ochre.
- Error/blocking: restrained red.
- Accent: teal/green/ink, not loud blue or purple.
- Product photos should be visually dominant.

Possible texture motifs:

- Listing tags
- Stockroom labels
- Garment labels
- Paper cards
- Charity shop rails
- Soft shadows like stacked cards

## Typography

Prefer expressive but readable typography.

Guidance:

- Use a distinctive heading font if available.
- Use a very readable body font.
- Avoid default-feeling combinations unless the existing app already uses them.
- Strong hierarchy matters more than decorative styling.

Suggested pairings:

- Headings: `Fraunces`, `DM Serif Display`, `Space Grotesk`, `Sora`, `Manrope`
- Body: `Inter`, `IBM Plex Sans`, `Source Sans 3`, `Manrope`

If adding external fonts is too much for the task, preserve existing font setup and improve hierarchy through size, weight, spacing, and layout.

## Core Components

### 1. Review Queue Card

Each item card should show:

- Main product photo.
- Title.
- Brand.
- Category/item type.
- Price.
- Estimated profit.
- Draft status.
- Confidence status.
- Warning/error chips.
- Primary next action.

Card states:

- Ready
- Needs review
- Draft created
- Draft failed
- Auth required
- Low margin
- Low confidence
- Category conflict

The card should make the next action obvious.

### 2. Status Chips

Use compact, readable chips for:

- Ready
- Needs review
- Draft created
- Draft failed
- Low brand confidence
- Low material confidence
- Low margin
- Thin margin
- Category locked
- eBay comps available
- Vinted auth expired

Chips should be meaningful, not decorative.

### 3. Pricing Panel

Show:

- Current price.
- Suggested price.
- eBay suggested range if available.
- Estimated profit.
- Profit multiple.
- Buy price if known.
- Reason for warning or suggestion.

Rules:

- Suggested price should not silently replace user price.
- Make “accept suggestion” explicit.
- Use warnings when margin is weak.
- Price changes should explain why.

### 4. Confidence Panel

Show confidence near the field it relates to.

Examples:

- Brand field shows brand confidence and candidates.
- Material field shows material confidence and reason.
- Category field shows conflict warnings.
- Size field shows normalised size and raw detected size where useful.

### 5. Draft/Auth Panel

Show:

- Connected/disconnected Vinted status.
- Draft URL if created.
- Draft failure message if present.
- Clear action to reconnect when needed.

Expired auth should feel like a fixable setup issue, not a mysterious crash.

### 6. Upload Flow

Mobile matters.

Upload should:

- Allow photo library and camera.
- Clearly show selected photos.
- Warn if photo quality/count may cause issues.
- Resize/compress behind the scenes.
- Show progress in friendly language.
- Avoid technical error dumps.

## Page-Level UX

### Review Queue

Best layout:

- Header with counts: total, needs review, ready, draft failed.
- Filter chips.
- Sort by urgency.
- Card grid/list hybrid.
- Product photo leading each card.
- Bulk actions only if genuinely useful.

Priority order:

1. Draft failed
2. Auth required
3. Low confidence key fields
4. Low margin
5. Needs review warnings
6. Ready
7. Draft created

### Item Review Page

Best layout:

- Left/top: photos.
- Main column: editable listing fields.
- Side/sticky panel: price/profit/draft status.
- Warnings attached to fields.
- Save/regenerate/create draft actions easy to find.
- Mobile layout stacks photos, status, then fields.

### Connect Page

Should explain:

- Vinted session is needed to create drafts.
- User opens login.
- User saves session.
- App confirms connected state.

Keep it simple and calm.

## Interaction Principles

- Reduce clicks for common fixes.
- Put warnings next to the field/action they affect.
- Show the consequence of an issue.
- Make destructive or overwrite actions explicit.
- Preserve user edits.
- Make regenerate/reprice feel controlled, not random.
- Use optimistic UI only where backend state is reliable.
- Provide compact explanations instead of raw logs.

## Motion

Use motion sparingly:

- Page/card entrance animation.
- Warning chip reveal.
- Status transition after draft creation.
- Loading state for upload/draft creation.

Avoid:

- Constant bouncing.
- Decorative animation that slows review.
- Motion that hides information.

## Accessibility

Must-haves:

- Good contrast.
- Click targets large enough on mobile.
- Keyboard-friendly forms/actions where practical.
- Do not rely only on colour for status.
- Error text should be readable and specific.

## Implementation Guidance For Agents

When asked to improve frontend:

- Inspect existing frontend files first.
- Preserve current data contracts.
- Improve one complete surface at a time.
- Avoid adding a new design system unless justified.
- Prefer reusable components for chips, cards, price panels, and confidence indicators.
- Make empty/error/loading states polished.
- Test mobile layout.
- Do not create pretty mock UI disconnected from real data.

## Suggested Design Prompt

```text
Using `AGENTS.md` and `docs/FRONTEND_DESIGN_BRIEF.md`, improve this Vinted app screen.

Screen:
[review queue / item review / upload / connect]

Goal:
Make it feel like a polished reseller listing cockpit.

Must include:
- Product-photo-first hierarchy.
- Clear status chips.
- Pricing/profit visibility.
- Confidence/warning visibility.
- Mobile-friendly layout.
- Real data wiring using existing backend contracts.
- No generic purple AI/SaaS styling.

Implement the change in the existing codebase, preserve current behaviour, and run the narrowest relevant check.
```

## Suggested UI Audit Prompt

```text
Audit the current Vinted frontend against `docs/FRONTEND_DESIGN_BRIEF.md`.

Find:
- UX blockers
- unclear states
- weak visual hierarchy
- missing confidence/warning visibility
- mobile issues
- places where pricing/profit is hidden
- places where draft/auth errors are unclear

Return findings first with file references, then suggest the smallest useful patch.
```
