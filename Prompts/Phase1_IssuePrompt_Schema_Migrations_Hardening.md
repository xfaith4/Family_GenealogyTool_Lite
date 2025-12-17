Title: Phase 1 — Introduce SQLAlchemy + Alembic and expand schema (no regressions)

Context
We have a working Flask + SQLite app. Now we need a professional, migration-based schema that supports places, events, media links, and data-quality flags while keeping today’s behavior intact.

Goals
- Add SQLAlchemy models and Alembic migrations.
- Ensure “single empty DB” can always be created from migrations.
- Expand schema to support:
  - Person, Family, relationships
  - Events (typed), raw/original fields + canonical date column
  - Places + place variants (for future standardization)
  - MediaAsset + MediaLink (person/family), plus “unassigned” support
  - DataQualityFlags table (or equivalent) for analytics later
- Keep existing endpoints working (or update UI + tests accordingly).

Non-goals
- No redesign of the UI yet.
- No heavy analytics logic yet (just schema foundation).

Implementation notes
- Use SQLAlchemy 2.x style.
- Use Alembic for migrations; do not require manual SQL.
- Provide a clean “init/reset DB” flow via scripts/Reset-Database.ps1 (update if needed).

Deliverables
- New `app/db.py` (engine/session), `app/models.py` (models), `migrations/` (alembic).
- Updated GEDCOM import to write into the new schema (raw fields preserved).
- Updated tests and at least 2 new tests: (a) migration creates empty DB, (b) import populates expected rows.

Acceptance criteria (Done)
- `.\scripts\Setup.ps1` works from a clean clone and creates DB via migration.
- `python -m unittest discover -s tests -v` passes.
- GEDCOM import still works and app loads UI successfully.

How to verify
- Fresh clone → Setup → Start → Import a GEDCOM → Confirm people + families appear.
- Run tests.
