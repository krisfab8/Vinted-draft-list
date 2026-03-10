---
name: vinted-price-drop
description: Apply scheduled markdown rules to Vinted listings and sync updates to the sheet.
---

# Purpose
Update listing prices based on age and pricing rules.

# Rules
- Day 7: reduce by 10% from original list price
- Day 14: reduce by 15% from original list price
- Day 21: reduce by 20% from original list price

# Workflow
1. Read active listings from the sheet.
2. Calculate listing age from `listed_date`.
3. Determine whether a markdown threshold has been reached.
4. Use browser automation to update the live listing price on Vinted.
5. Write the new price back to the sheet.

# Notes
- Use `listed_date` from the sheet as the markdown baseline.
- Skip items marked as `premium` or `hold` unless explicitly allowed.
- Log every markdown event with timestamp and old/new price.
- Prefer original list price as markdown baseline (not previous reduced price).
