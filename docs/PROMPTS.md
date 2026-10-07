# Prompt cheat-sheet (save tokens)

Start a message with a **code word**. Claude knows what each one means (see "Codes" in CLAUDE.md),
so you don't need to explain. Add a screenshot and one line if it's visual.

| Code | You type | Claude does |
|---|---|---|
| `fix:` | `fix: Create button hidden under nav (screenshot)` | Smallest fix, tests, ship. No essay. |
| `tweak:` | `tweak: chip text "drafts" → "listings"` | Text/CSS only. Cheap helper agent, ship. |
| `build:` | `build: phase 2 quests` | Short plan (3–5 lines), build, test, screenshot, ship. |
| `plan:` | `plan: streak freezes` | Plan/ideas only. No code. |
| `ask:` | `ask: why is price £38?` | Answer only. No code changes. |
| `look:` | `look: drafts page` | Screenshot at phone size and report problems. |
| `ship` | `ship` | Tests → commit → push → confirm Render is live. |
| `link` | `link` | Just the Render URL. |
| `logs:` | `logs: Galvin Green` | Read Render logs for that, short summary. |

## Tips that save the most
- **One job per message.** Bundles of 4–5 unrelated asks cost far more (more files read, more checks).
- **Screenshot + circle** beats a long description.
- Say **"no screenshots"** if you don't need visual proof back.
- Say **"just do it"** to skip the plan step.
- When you see the change live, reply **"good"** — no need to re-describe it.

Live app: https://vinted-measurements-test.onrender.com
