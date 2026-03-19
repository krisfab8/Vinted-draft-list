# Test Plan

## Goals
- Ensure the core listing pipeline works reliably
- Catch regressions in deterministic business logic
- Make browser failures easier to diagnose
- Verify review routing for uncertain items

## Automated tests
Focus on:
- validation logic
- category mapping
- size normalization
- pricing logic
- item state transitions
- regeneration preserving confirmed values

## Integration tests
Focus on:
- extraction -> listing -> validation flow
- create listing route
- regen route
- draft creation entry points where practical without full browser run

## Manual smoke tests
For every meaningful backend/UI change:
1. Upload an item
2. Generate listing
3. Edit one or more fields
4. Regenerate where relevant
5. Create draft
6. Confirm status and saved data are correct

## Manual browser tests
Check:
- login/session reuse
- category selection
- form field fill
- image upload
- save draft success
- failure visibility if a page element changes

## Success criteria
- No existing core flow is broken
- Relevant automated tests pass
- Manual smoke test passes
- Any known failures are clearly logged and reproducible

## Priority test data
Always test with:
- easy branded item
- ambiguous item
- damaged item
- tailored/formal item
- awkward size/category item
