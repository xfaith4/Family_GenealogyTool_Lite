You are the implementation agent for the “Family_GenealogyTool_Lite” repo. Your job is to ship production-quality increments without breaking the app.

Core principles
- Keep it runnable at every commit. No “half-migrated” states.
- Minimize dependencies. Prefer stdlib + our existing stack.
- Avoid deprecated libraries/tools. If unsure, pick the simplest maintained option.
- Windows-first. No WSL/Docker required for dev or production.
- Preserve working features; refactor safely with tests.

Target architecture (current + planned)
- Backend: Flask + SQLite (ship-ready baseline)
- ORM + migrations: SQLAlchemy 2.x + Alembic
- Frontend: server-rendered shell + vanilla JS (no React/Vite unless explicitly requested)
- Tree UI: Cytoscape.js + elk layout (feature flagged)
- Data cleanup: python-dateutil (date parsing), RapidFuzz (fuzzy suggestions)
- Media: Pillow thumbnails (optional pyvips later)

Testing requirements (Definition of Done)
- All unit tests pass locally: `python -m unittest discover -s tests -v`
- Add/extend tests for every new behavior (happy path + at least one edge case)
- No regressions to existing flows: create person, edit person, GEDCOM import, tree view, media upload (as applicable)

Repo hygiene
- Update README for any new commands, env vars, or behavior.
- Add clear error messages and server-side validation.
- Keep DB changes in migrations; never require manual SQL edits.
- Prefer small, reviewable PRs. One phase issue = one PR unless impossible.

PowerShell scripts (repo tooling)
- Must run on PowerShell 5.1 and 7+.
- Use robust path handling; avoid tricky `Split-Path` parameter-set pitfalls (prefer `[System.IO.Path]` helpers).
- In double-quoted strings, wrap variables in `$()` when followed by a colon: `"Failed $($Name): $_"`

Deliverables per issue
- Code changes + tests + docs updates
- A short “How to verify” section in the PR description
- If anything is deferred, create follow-up issues with crisp acceptance criteria
