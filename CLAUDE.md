# Project: Vinted Listing Automation

## Goal
Build a low-cost clothing listing workflow that:
1. reads a small set of clothing photos
2. extracts structured item data
3. writes a concise Vinted listing
4. saves the listing as a draft via browser automation
5. logs the item to Google Sheets for ROI and sell-through tracking
6. later supports automatic markdown rules and analytics

## Constraints
- Target cost: under £0.02 per item (typical cost ~£0.003 with Claude Haiku 4.5)
- Prefer deterministic scripts over agentic browser loops
- Use AI only where it adds value:
  - tag/material/size extraction
  - listing generation
  - edge-case reasoning
- Use normal code for:
  - browser filling
  - spreadsheet updates
  - date logic
  - markdown scheduling
- Keep prompts concise and reusable
- Default analyzed photos:
  1. front
  2. tag/size
  3. material
  4. back
- Upload all photos to Vinted, but do not analyze extras unless confidence is low

## Vision Provider
Set `VISION_PROVIDER` in `.env` to swap models without rewriting logic:
- `claude-haiku` — default, single Anthropic API key, ~£0.003/item
- `gemini-flash` — cheapest per image, needs separate Google AI key
- `grok-vision` — currently more expensive, not recommended for cost targets

## Build Order
1. Vision extraction
2. Listing writer
3. Playwright draft creator
4. Google Sheets sync
5. Price-drop automation
6. Analytics dashboard

## Coding Preferences
- Python for backend scripts
- Playwright for browser automation
- Small local web app for daily use (Flask)
- JSON outputs for model steps
- Validate outputs against `schemas/listing.schema.json`
- Keep functions small and testable

## Model Strategy
- `VISION_PROVIDER` env var controls image extraction model
- Claude Haiku 4.5 for listing writing/orchestration
- Escalate only difficult cases to stronger models

## Success Criteria
- One-click draft creation from item photos
- Reliable spreadsheet logging
- Clear separation between AI and deterministic logic
- Easy for a non-developer to operate daily
