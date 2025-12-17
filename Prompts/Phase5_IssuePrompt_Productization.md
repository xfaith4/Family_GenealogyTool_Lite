Title: Phase 5 — Productization (backups, diagnostics, packaging path, CI hygiene)

Context
We want “proud to show off” and “boring to run.” No fragile setup, no mystery failures.

Goals
- Add backup/restore:
  - DB backup with timestamp
  - media folder backup option (or manifest-based)
- Add diagnostics page:
  - app version
  - DB path + schema version
  - counts (people/families/media/unassigned)
  - last import timestamp (if available)
- Improve logging:
  - structured logs to a file under /logs
  - clear error messages surfaced to UI for common failures (bad GEDCOM, bad media upload)
- Optional packaging path (choose one maintained approach):
  - document a “single-folder distribution” and optionally PyInstaller build (only if stable)
- CI hygiene (lightweight):
  - ensure tests run in CI
  - optional ruff for lint/format in dev only

Non-goals
- No enterprise auth.
- No multi-user hosting.

Deliverables
- Updated scripts (Setup/Start/Test/Backup/Restore).
- Docs: README “Install / Run / Backup / Restore / Troubleshooting”.
- Tests: at least one test covering backup creation.

Acceptance criteria (Done)
- A non-dev user can follow README and run it locally on Windows without surprises.
- Tests pass.
- Diagnostics page gives enough info to debug quickly.

How to verify
- Fresh clone → Setup → Start → Import → Upload media → Backup DB → Restore DB → Verify data intact.
