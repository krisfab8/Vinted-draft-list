# Beta Roadmap

## Must do before Beta
- Create a single pipeline/orchestration service for listing creation flow
- Reduce orchestration duplication in `app/web.py`
- Add persistent item state tracking
- Introduce clear item lifecycle statuses
- Route low-confidence items into review
- Harden draft creation logging and failure visibility
- Strengthen business-rule validation beyond schema
- Stabilise regeneration so confirmed edits are preserved
- Add focused tests for core deterministic logic
- Run a real multi-item beta rehearsal

## Should do before broader testing
- Add deterministic pricing service
- Centralise category mapping
- Improve draft failure recovery
- Add screenshot/log capture on browser failure
- Improve review queue UX
- Add lightweight analytics on pipeline failures and review frequency

## Later / post-Beta
- Google Sheets sync improvements
- Price-drop automation
- Sold tracking
- Comps-based pricing
- Multi-platform listing support
- Rich analytics dashboard
