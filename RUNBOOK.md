# Family_GenealogyTool_Lite Runbook

## Setup (fresh environment)
1. Windows PowerShell 5.1+ or PowerShell 7:
   ```powershell
   cd <repo_root>\scripts
   .\Setup.ps1
   ```
   - Prints the exact SQLite DB path and deletes any prior DB before running `alembic upgrade head`.
2. Python (manual):
   ```bash
   python -m pip install -r requirements.txt
   ```

## Run the server
```bash
export FLASK_APP=run.py
python run.py
```
Defaults:
- DB: `data/family_tree.sqlite`
- Media: `data/media`
- Ingest watch folder: `data/media_ingest`

## Reproduce fixed issues
- **ERROR A (logging KeyError):**
  - Before: `POST /api/import/rmtree` with any file could 500 due to `filename` in logging `extra`.
  - After: call `curl -F "file=@tests/data/sample.rmtree" http://localhost:5000/api/import/rmtree` → no KeyError, JSON error on bad input (HTTP 400/422).
- **ERROR B (duplicate index):**
  - Run `scripts/Setup.ps1` twice; both runs succeed and recreate DB cleanly, printing deleted DB path. Alembic migration guards index creation for SQLite.

## Validate media ingest / unassigned workflow
1. Drop 1–3 media files into `data/media_ingest/`.
2. Call `GET /api/media/unassigned` → triggers scan; new items appear with `status="unassigned"`.
3. Call `POST /api/media/assign` with `{"media_id": <id>, "person_id": <pid>}` → item moves out of unassigned; `status` becomes `assigned`.

## Validate RMTree import with media associations
1. Import an RMTree file:
   ```bash
   curl -F "file=@path/to/sample.rmtree" http://localhost:5000/api/import/rmtree
   ```
2. Expected:
   - People created/updated.
   - Media assets created (or placeholders when files missing).
   - Links created between people and media.
   - Missing files counted in response (`missing_media`).
3. Logs use safe `extra` keys; no KeyError.

## Tests
- Run all:
  ```bash
  pytest
  ```
- Targeted:
  - `pytest tests/test_media_ingest.py -q`
  - `pytest tests/test_api.py::TestApi::test_rmtree_import_populates_people_and_media_from_sqlite -q`
