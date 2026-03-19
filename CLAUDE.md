# CLAUDE.md

## Project
Vinted Draft List is a production-minded clothing listing automation system for Vinted.

It is designed to:
1. take structured clothing photos from an item folder
2. extract item data with vision models
3. generate a Vinted-ready listing
4. validate and preserve important fields
5. create or manage Vinted drafts through Playwright
6. support review, repricing, corrections, and operational tracking
7. improve over time through logs, corrections, and price memory

This is not a toy demo. Priorities are:
- reliability
- resale usefulness
- low token cost
- fast operator workflow
- minimal manual correction

---

## Current Repo Reality

The repo already contains working or partial implementations for:

- `app/extractor.py`
  Vision extraction with confidence-aware behavior and rereads

- `app/listing_writer.py`
  Listing generation, normalization, title/description shaping, pricing-related logic

- `app/validate_listing.py`
  Schema validation and listing checks

- `app/draft_creator.py`
  Playwright-based Vinted draft creation and editing behavior

- `app/web.py`
  Flask app, upload flow, listing creation, review/drafts/stats routes, repricing/regeneration logic

- `app/run_logger.py`
  Structured run logging and correction logging

- `app/templates/review.html`
  Review workflow for uncertain or operator-checked items

- `app/templates/connect.html`
  Login/connect flow for Vinted auth/session handling

- `data/price_memory.json`
  Local pricing memory / pricing recall layer

- `mcp/sheets_server.py`
  Google Sheets or sheet-related integration support

- `tests/`
  Real test suite for pipeline, auth/session, category rules, material/brand confidence, image policy, draft robustness, price memory, etc.

This means the system is already beyond MVP and should be treated like a real app under active hardening.

---

## Product Goal

The app should let an operator go from photos to a usable draft with minimal friction.

Target operator flow:

1. Upload item photos
2. Generate structured extraction
3. Generate listing
4. Validate and preserve known-good fields
5. Route uncertain items to review
6. Create draft reliably
7. Track what happened
8. Learn from corrections and pricing decisions

---

## Primary Priorities

In order:

1. Preserve working behavior
2. Improve reliability of the full pipeline
3. Reduce bad listings and bad draft runs
4. Improve review routing for uncertain items
5. Improve pricing usefulness for resale
6. Keep code maintainable and testable
7. Keep runtime cost low

---

## Non-Negotiable Rules

### 1. Do not casually break Playwright flows
`app/draft_creator.py` is business-critical and fragile.

When changing it:
- keep edits minimal
- prefer isolated helpers over broad rewrites
- add logging where useful
- preserve current behavior unless explicitly asked to change it

### 2. Do not overwrite user-confirmed values
If a user has manually edited or confirmed a field, regeneration must not blindly replace it with new AI output.

### 3. Do not remove validation
Schema validation must remain.
Business-rule validation can be added on top, but never remove working checks.

### 4. Keep routes and UI behavior stable unless the task explicitly changes them
This app is operational, not just architectural.

### 5. Avoid unnecessary rewrites
Prefer targeted refactors that reduce risk.

### 6. Do not treat local runtime artifacts as source files
These are intentionally excluded from git and should be treated as runtime/generated data:
- `auth_state.json`
- `data/run_logs.jsonl`
- `data/corrections.jsonl`
- `debug_screenshots/`
- `cat_screenshots/`
- `inspection/`

---

## How to Think About This Repo

This is a listing operations system, not just an AI prompt wrapper.

The app combines:
- deterministic code
- AI extraction/writing
- browser automation
- review workflow
- operational observability
- pricing memory
- corrections feedback

When improving the repo, optimize for operator usefulness and business outcomes, not just elegant code.

---

## Preferred Engineering Approach

- prefer deterministic logic over model guessing
- keep modules focused
- reduce duplication in `web.py`
- move orchestration into services when appropriate
- preserve backward-compatible behavior where possible
- make failures visible, not silent
- write code that is easy to test without the browser where possible

---

## Architecture Direction

We are moving toward clearer separation between:

### Pipeline / orchestration
A single service should eventually own:
- extraction
- listing generation
- validation
- persistence
- review routing
- draft creation calls
- run logging

### Repository / state
The app currently uses folder-based item state and local JSON.
This is acceptable short term, but changes should make state cleaner and easier to reason about.

### Review routing
Low-confidence or problematic items should be obvious in the UI and easy to correct.

### Observability
Run logs and corrections are important first-class signals, not debug leftovers.

### Pricing
Use both generated logic and deterministic constraints where helpful.
Price memory should be respected and expanded carefully.

---

## File Sensitivity Guide

### High sensitivity
Change only with care:
- `app/draft_creator.py`
- `app/web.py`
- `app/extractor.py`
- `app/listing_writer.py`

### Medium sensitivity
- `app/validate_listing.py`
- `app/run_logger.py`
- templates tied to operator flow
- pricing memory handling
- auth/connect flow

### Lower sensitivity
- docs
- isolated helper modules
- new service modules
- focused tests

---

## Testing Rules

Every meaningful change should include one or more of:

### Unit / focused tests
Use for:
- category rules
- price logic
- confidence logic
- validation rules
- correction preservation
- memory behavior

### Integration tests
Use for:
- extraction to listing flow
- review routing
- regeneration behavior
- auth/session behavior where possible

### Manual QA
Required for:
- Playwright flows
- login/connect flows
- draft creation/editing
- UI workflow changes

If a change touches browser automation, always provide manual smoke test steps.

---

## Definition of Done

A task is done only when:

- the requested behavior is implemented
- existing working flows are preserved
- relevant tests are added or updated where sensible
- manual QA steps are clearly stated if browser/UI behavior is involved
- logs/errors remain understandable
- changes stay within scope

---

## Logging and Observability

This repo already has structured run/correction logging.

Preserve and improve that.

Prefer changes that make it easier to answer:
- what failed?
- where did it fail?
- what did the operator correct?
- which fields are weak?
- which categories or brands are causing issues?
- how often does draft creation fail?

Do not add opaque behavior that makes debugging harder.

---

## Pricing Philosophy

This is a resale tool.
Pricing is commercially important.

Pricing should consider:
- brand
- item type
- material quality
- condition / flaws
- buy price if known
- prior memory or known pricing anchors

Avoid obviously weak or generic pricing decisions.
If adding pricing logic, keep it explainable.

---

## Prompting / Model Philosophy

Use AI where it has real leverage:
- reading tags/material labels
- extracting uncertain clothing details
- producing concise listing copy
- handling edge-case reasoning

Do not use AI for things better handled in code:
- route flow
- browser clicking logic
- deterministic mapping
- simple state transitions
- logging
- test orchestration

Keep prompts concise and reusable.
Prefer explicit schemas and controlled output shapes.

---

## What Claude Should Do On Each Task

Unless explicitly told otherwise:

1. analyze the relevant code first
2. explain the plan briefly
3. make focused changes only
4. avoid unrelated cleanup
5. update or add tests if appropriate
6. provide manual QA steps if needed

If a requested change seems risky, prefer the smallest safe implementation first.

---

## Things To Avoid

- broad rewrites of `draft_creator.py`
- mixing new architecture work with unrelated UI cleanup
- replacing deterministic logic with prompt logic
- silent changes to operator-facing behavior
- changing too many files at once without need
- inventing new abstractions that the repo does not need yet

---

## Operational Goal

Every improvement should help move the system toward this outcome:

- faster item processing
- fewer listing mistakes
- fewer draft failures
- better operator visibility
- better resale pricing
- lower manual effort
- maintainable iteration toward beta
