# AGENTS.md — Working Agreement for AI Agents (Codex/Copilot/etc.)

This repo is intentionally **boring and portable**: Flask + SQLite + vanilla JS/CSS/HTML, with PowerShell + Termux helpers.  
Agents should optimize for **reliability, clarity, and low-dependency changes**.

---

## Prime directive

1. **Keep it dependency-light.** Don't introduce Node/build steps unless explicitly asked.
2. **Don't break portability.** Must keep working on:
   - Windows (PowerShell-friendly)
   - Linux/macOS (plain Python)
   - Android (Termux scripts)
3. **Prefer small PRs.** One feature/fix per PR when possible.
4. **Be deterministic.** Data migrations/imports must be repeatable.
5. **No secrets in repo.** Never commit tokens, private data, or real family datasets.

---

## What "Done" means

A change is "Done" when all are true:

- App starts successfully using the documented scripts/commands below
- Existing functionality still works (especially imports + analytics page)
- Tests run and pass (see **Testing**)
- New behavior is covered by either:
  - a test, or
  - a clear manual verification section in the PR description (with steps)
- No new heavyweight deps, no unreviewed refactors, no surprise rewrites
- UI changes are responsive (desktop + mobile)

---

## Repo map (mental model)

High-level components to keep distinct:

- **Backend (Flask):**
  - API routes (CRUD, analytics, import)
  - DB access / query helpers
  - import pipeline(s)
- **Frontend (static):**
  - pages + components in vanilla JS/CSS/HTML
  - chart rendering + drilldowns
  - responsive navigation + mobile behaviors
- **Scripts:**
  - `scripts/Setup.ps1` / `scripts/Start.ps1` (Windows)
  - Termux setup/run scripts (Android)
  - Export-to-JSON for GitHub Pages mode
- **Data layer:**
  - SQLite schema + any migrations
  - JSON export format (for Pages)

Agents should **not** blur boundaries. Example: frontend should not embed raw SQL logic; backend should not ship bundled/minified frameworks.

---

## Quick start commands

### Windows (PowerShell)
Preferred path for local dev:

```powershell
# From repo root
.\scripts\Setup.ps1
.\scripts\Start.ps1
```

Access: <http://127.0.0.1:3001>

### Linux/macOS
```bash
pip install -r requirements.txt
python -m alembic upgrade head
python run.py
```

### Android (Termux)
```bash
./scripts/termux-setup.sh
./scripts/termux-run.sh
```

See [docs/TERMUX.md](docs/TERMUX.md) for details.

---

## Testing

### Run all tests
**Windows:**
```powershell
.\scripts\Test.ps1
```

**Linux/macOS/Termux:**
```bash
python -m unittest discover -s tests -v
# or
pytest
```

### Targeted tests
```bash
pytest tests/test_api.py -q
pytest tests/test_media_ingest.py -q
```

**Always** run tests before and after changes. If a test fails unrelated to your work, note it but don't fix unrelated issues unless asked.

---

## Structure guidelines

### Backend (Flask)
- Routes in `app/routes.py`
- Models in `app/models.py`
- DB helpers in `app/db.py`
- Import logic in `app/gedcom.py`, `app/rmtree.py`
- Schema migrations in `migrations/versions/`

### Frontend
- Templates in `app/templates/`
- Static assets in `app/static/`
  - JS: `app/static/*.js`
  - CSS: `app/static/*.css`
- No build step required; vanilla HTML/CSS/JS

### Data
- SQLite DB: `data/family_tree.sqlite`
- Media files: `data/media/`
- Ingest folder: `data/media_ingest/`

---

## Common pitfalls

1. **Don't break portability**: Test on Windows (PowerShell) if you can. Avoid Unix-only shell commands in core logic.
2. **Don't add Node/npm**: This is a Python+vanilla-JS project. No webpack, no React, no build steps.
3. **Don't modify unrelated tests**: If a test fails unrelated to your change, leave it alone unless explicitly asked to fix it.
4. **Don't commit secrets or real data**: Use placeholder/sample data only.
5. **Don't surprise with rewrites**: Incremental changes > big refactors. Ask first if unsure.

---

## Manual verification checklist

When making changes that affect the UI or user workflows:

1. **Start the app**: Use `.\scripts\Start.ps1` (Windows) or `python run.py`
2. **Check mobile view**: Use browser dev tools to emulate 360x800px
3. **Test imports**: Try importing a GEDCOM or RMTree file
4. **Verify analytics**: Check that charts load and drilldowns work
5. **Check responsive behavior**: Ensure bottom nav appears on mobile, hidden on desktop

---

## Adding new features

When adding a feature:

1. **Check if tests exist**: Add tests alongside your code if test infrastructure is present
2. **Follow existing patterns**: Match coding style, naming conventions, project structure
3. **Update docs if needed**: README.md, this file, or inline docstrings
4. **Keep it simple**: Prefer clarity over cleverness
5. **Test on multiple platforms if possible**: At minimum, verify PowerShell scripts don't break

---

## Questions?

- Check [README.md](README.md) for project overview
- Check [RUNBOOK.md](RUNBOOK.md) for operational procedures
- Check [docs/TERMUX.md](docs/TERMUX.md) for Android/Termux specifics
- Review existing code for patterns and conventions
