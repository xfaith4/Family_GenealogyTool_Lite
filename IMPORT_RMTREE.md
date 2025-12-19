# RootsMagic RMTree Import (`/api/import/rmtree`)

This endpoint ingests RootsMagic 8/9 tree databases and produces a canonical, queryable representation inside the application database.

## Supported inputs

- **`.rmtree`** (SQLite RM database). Signature must start with `SQLite format 3\0`.
- **`.rmbackup` / `.rmgb`** (ZIP archives). The service locates an embedded `.rmtree` and validates it is SQLite.

Uploads are accepted as **`multipart/form-data`** with form field **`file`**. The default size limit is `MAX_CONTENT_LENGTH` (25 MB by default). The uploaded database is opened **read-only**; no writes are issued against it.

## Validation and safety

- Signature sniffing (ZIP vs SQLite); empty or unknown signatures are rejected.
- Size guard with clear `file_too_large` error that includes the limit.
- `PRAGMA quick_check` and `PRAGMA user_version` are run against the uploaded DB.
- Schema fingerprint (SHA-256 of `sqlite_master`) is returned to aid troubleshooting.
- RMNOCASE is avoided; data is read with plain `SELECT` queries.
- Orphaned relationships/media links are detected and reported.

## Response shape (success)

```json
{
  "imported": {
    "people": 3,
    "media_assets": 2,
    "media_links": 2,
    "relationships": 2,
    "events": 0,
    "places": 0,
    "sources": 0
  },
  "warnings": ["PRAGMA quick_check reported: ok"],
  "orphaned": {"relationships": 0, "media_links": 0},
  "schema": {"user_version": 0, "fingerprint": "<sha256>", "objects_seen": 12},
  "job": {"status": "completed", "started_at": "...Z", "ended_at": "...Z"}
}
```

## Error codes (JSON)

- `missing_file` – expected `multipart/form-data` with field `file`
- `invalid_content_type` – wrong content type
- `invalid_signature` – not ZIP/SQLite
- `invalid_archive` – ZIP without `.rmtree` or corrupt archive
- `file_too_large` – exceeds `MAX_CONTENT_LENGTH`
- `empty_file` – zero-byte upload
- `open_failed` / `integrity_check_failed` – SQLite could not be opened or checked
- `no_data` – recognized DB but no importable tables

## Client example (Python + requests)

```python
import requests

file_path = "path/to/tree.rmtree"  # or .rmbackup
resp = requests.post(
    "http://localhost:3001/api/import/rmtree",
    files={"file": open(file_path, "rb")},
)
print(resp.status_code, resp.json())
```

### cURL one-liner

```sh
curl -F "file=@/path/to/tree.rmtree" http://localhost:3001/api/import/rmtree
```

## Root cause of prior HTTP 400

The original `/api/import/rmtree` expected a text dump of SQL `INSERT` statements and attempted to `decode()` uploaded files as UTF-8. Real RootsMagic uploads are binary SQLite/ZIP files, so decoding failed and the parser returned `failed to parse RMTree file`, producing a generic 400. The new implementation sniffs signatures, supports `.rmtree` and `.rmbackup`, opens the database read-only, and returns structured JSON errors to prevent regression.
