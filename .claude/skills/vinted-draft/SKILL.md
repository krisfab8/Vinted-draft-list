---
name: vinted-draft
description: Create a Vinted draft from clothing photos, notes, and pricing rules.
---

# Purpose
Turn a folder of item photos into:
1. structured extraction
2. a Vinted-ready listing
3. a saved draft
4. a spreadsheet row

# Inputs
- item folder path (inside `items/`)
- optional flaws note
- optional buy price (£)

# Default Photo Assumptions
- front.jpg
- tag.jpg
- material.jpg
- back.jpg
- extra photos may also exist and should still be uploaded to Vinted

# Workflow
1. Read the item folder.
2. Extract structured fields from the analyzed photos:
   - brand
   - tagged size
   - normalized size
   - materials
   - colour
   - item type
   - gender (men's / women's / unisex)
   - notable visible features
3. Generate listing data:
   - title
   - description
   - price suggestion
   - category mapping (see `prompts/category_rules.md`)
   - condition summary
4. Validate listing JSON against `schemas/listing.schema.json`.
5. Use browser automation to:
   - open Vinted sell page
   - upload all photos in folder
   - fill required fields
   - save draft
6. Append tracking row to Google Sheets.

# Listing Rules
- Keep title concise and searchable.
- Do not over-hype condition.
- Mention flaws briefly and clearly.
- End description with:
  - Measurements in photos.
  - Fast postage.

# Escalation
If confidence is low for brand, material, size, or category:
- inspect one extra photo if available
- otherwise mark field as `null` and flag for manual review
