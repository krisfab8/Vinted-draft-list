Audit the current pipeline for this Vinted project.

Read:
- CLAUDE.md
- app/web.py
- app/extractor.py
- app/listing_writer.py
- app/validate_listing.py
- app/draft_creator.py
- any current services modules if they exist

Focus on:
1. Actual flow from upload/photos to generated listing to validation to draft creation
2. Duplication across routes or modules
3. Hidden coupling
4. Risks before Beta
5. Best next refactor with smallest safe change

Output format:
- Current flow
- Problems
- Recommended next step
- Files to change
- Test plan

Do NOT write code unless I explicitly ask.
Do NOT suggest broad rewrites unless clearly justified.
Keep recommendations practical and production-minded.
