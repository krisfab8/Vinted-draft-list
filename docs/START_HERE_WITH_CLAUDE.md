# Start Here With Claude

Build this project in phases. Start each phase only after the previous one is working.

## Phase 1: Scaffold (done)
- project structure created
- CLAUDE.md, .env.example, .gitignore, .mcp.json in place
- skills, agents, prompts, schemas all defined
- Copy `.env.example` to `.env` and fill in your keys before Phase 2

## Phase 2: Python App Foundation
- create `app/` directory with Flask web app
- config loading from `.env` (use `python-dotenv`)
- item-folder reader: list photos in `items/<item_name>/`
- listing JSON validation against `schemas/listing.schema.json` (use `jsonschema`)
- simple web UI: item folder picker + optional flaw note + buy price field

## Phase 3: Vision Extraction
- implement `app/extractor.py` with provider abstraction
- support `claude-haiku` first (cheapest, single API key)
- analyze only front.jpg, tag.jpg, material.jpg, back.jpg
- return compact JSON matching tag-reader agent output
- escalate to extra photo only if confidence < 0.7

## Phase 4: Listing Writer
- implement `app/listing_writer.py`
- takes extractor output + prompts/listing_style.md + prompts/category_rules.md
- uses Claude Haiku 4.5 to generate listing JSON
- outputs schema-compliant JSON
- validates before saving

## Phase 5: Playwright Draft Creator
- implement `app/draft_creator.py`
- log in to Vinted via stored credentials
- open sell page
- upload all photos from item folder
- fill form from listing JSON
- save as draft (do not publish)

## Phase 6: Google Sheets Sync
- implement `app/sheets_sync.py`
- append one row per item after successful draft creation
- columns: date, brand, item_type, size, colour, buy_price, list_price, category, photos_folder, vinted_draft_url

## Phase 7: Price-Drop Automation
- implement `app/price_drop.py`
- read active listings from sheet
- calculate age
- apply markdown schedule
- update Vinted listing via Playwright
- write new price back to sheet

## Phase 8: Analytics
- implement `app/analytics.py`
- read full inventory + sold data
- output summary metrics to terminal or web UI

---

## Important Constraints (repeat)
- prefer deterministic code over freeform agent loops
- keep total per-item model cost under £0.02 (target ~£0.003)
- use AI only where needed
- keep browser actions scriptable and robust
