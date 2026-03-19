Refactor this code safely.

Before writing code:
1. Read CLAUDE.md
2. Summarise the task in 3-6 bullets
3. Identify exact files in scope
4. List anything that must not break

Then:
- implement only the requested change
- avoid unrelated cleanup
- preserve route behaviour unless explicitly allowed to change
- preserve working Playwright logic unless directly in scope
- preserve user-confirmed values during regen/edit flows

After coding:
- show a concise summary of changed files
- explain risks
- provide focused test commands
- provide a short manual QA checklist
