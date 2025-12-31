# Media Ingest & OCR

This project supports a deterministic media ingest pipeline with optional OCR and legacy association linking.

## Folder layout

- `data/media/` — canonical media storage (assets are copied here and referenced by the DB)
- `data/media/derived/ocr/` — OCR PDF + text sidecars
- `data/media_ingest/` — drop folder for new files
- `data/reports/` — legacy-link review reports

## Dependencies

OCR uses external tools (not bundled):

- **Preferred:** `ocrmypdf`
- **Fallback:** `tesseract` (PDF output, not guaranteed PDF/A)

Install examples:

- Windows: `winget install ocrmypdf`
- macOS: `brew install ocrmypdf`
- Linux (Ubuntu): `sudo apt-get install ocrmypdf`

## CLI usage

Run commands from repo root:

```bash
python scripts/media_cli.py scan --source data/media
python scripts/media_cli.py ingest --source data/media_ingest
python scripts/media_cli.py ingest --source data/media_ingest --ocr --lang eng
python scripts/media_cli.py ocr --source data/media_ingest --only-missing --lang eng
python scripts/media_cli.py watch --interval 5 --ocr
```

Legacy association migration:

```bash
python scripts/media_cli.py legacy-link --legacy-db path/to/legacy.sqlite --dry-run
python scripts/media_cli.py legacy-link --legacy-db path/to/legacy.sqlite --apply --min-confidence 0.9
```

The legacy-link command always emits a CSV report at:

`data/reports/legacy_media_link_candidates.csv`

## Notes

- The ingest/scan commands are idempotent; re-running does not create duplicates.
- OCR outputs are stored in `data/media/derived/ocr/` using SHA256 filenames.
- No originals are deleted; ingest copies files into `data/media/`.
