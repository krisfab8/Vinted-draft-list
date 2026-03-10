# System Overview

## Daily Workflow
1. User drops item photos into `items/<item-name>/` folder.
2. User opens the local web app and selects the item folder.
3. User optionally adds a flaw note and buy price.
4. System analyzes 3–4 core photos only (front, tag, material, back).
5. System generates compact listing JSON.
6. Browser automation uploads all photos and saves Vinted draft.
7. Sheet row is appended for tracking.

## Components
| Component             | File                    | Status   |
|-----------------------|-------------------------|----------|
| Vision extractor      | app/extractor.py        | Phase 3  |
| Listing writer        | app/listing_writer.py   | Phase 4  |
| JSON validator        | app/validate_listing.py | Phase 2  |
| Browser draft creator | app/draft_creator.py    | Phase 5  |
| Google Sheets sync    | app/sheets_sync.py      | Phase 6  |
| Price-drop job        | app/price_drop.py       | Phase 7  |
| Analytics             | app/analytics.py        | Phase 8  |
| Web UI                | app/web.py              | Phase 2  |

## Cost Strategy
- Analyze only 4 core photos per item (not all uploads)
- Keep prompts short — no padding
- Avoid agentic browser screenshot loops — use deterministic Playwright scripts
- Use Claude Haiku 4.5 by default (~£0.003/item); Gemini Flash if cost needs reducing further

## MCP Servers
- `playwright` — @playwright/mcp (official), browser automation
- `filesystem` — @modelcontextprotocol/server-filesystem, reads `./items/`
- `sheets` — custom Python MCP (`mcp/sheets_server.py`), built in Phase 6

## Google Sheets Column Layout (planned)
| # | Column           | Source              |
|---|------------------|---------------------|
| A | Date Listed      | auto                |
| B | Brand            | extractor           |
| C | Item Type        | extractor           |
| D | Size             | extractor           |
| E | Colour           | extractor           |
| F | Category         | listing writer      |
| G | Buy Price (£)    | user input          |
| H | List Price (£)   | listing writer      |
| I | Current Price(£) | auto-updated        |
| J | Status           | active/sold/draft   |
| K | Date Sold        | manual              |
| L | Sell Price (£)   | manual              |
| M | Profit (£)       | formula             |
| N | ROI %            | formula             |
| O | Days to Sale     | formula             |
| P | Photos Folder    | extractor           |
| Q | Notes            | user                |

## Future Additions
- confidence-based extra image read (already in extractor design)
- multi-platform listing (eBay, Depop)
- Telegram/email alerts on sale
- dashboard charts from analytics data
