# Family Genealogy Tool Lite

Minimal, dependency-light genealogy app designed to run cleanly on Windows and Android.

- **Backend:** Flask
- **Database:** SQLite (single file)
- **Frontend:** Vanilla HTML/CSS/JS (no build step)
- **No Node / no native modules / no WSL / no Docker**

## 🌐 GitHub Pages Static Version

A read-only static version is available that can be hosted on GitHub Pages:

- **No backend required** - All data loaded from JSON files
- **Perfect for sharing** - Host your family tree online
- **See it in action:** [View the static demo](docs/)

To create your own static version:

1. Import your genealogy data into the app
2. Run `python3 scripts/export_to_json.py` to export to JSON
3. Enable GitHub Pages in your repo settings (point to `/docs`)
4. Your family tree will be live at `https://yourusername.github.io/repo-name/`

See [docs/README.md](docs/README.md) for full instructions.

## Quick start (PowerShell)

```powershell
set-executionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\Setup.ps1
.\scripts\Start.ps1
```

Open: <http://127.0.0.1:3001>

## Local setup (venv recommended)

If your system Python is externally managed (PEP 668), use a virtual environment:

```bash
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
python run.py
```

## Run on Android (Termux)

You can run this app natively on Android using Termux—no root or Docker required!

**Quick setup:**

```bash
# Install Termux from F-Droid, then:
pkg install git -y
git clone https://github.com/xfaith4/Family_GenealogyTool_Lite.git
cd Family_GenealogyTool_Lite
./scripts/termux-setup.sh
./scripts/termux-run.sh
```

Open in your Android browser: <http://127.0.0.1:3001>

📖 **Full guide:** See [docs/TERMUX.md](docs/TERMUX.md) for detailed instructions, troubleshooting, and configuration options.

## Importing RMTree exports

Use the **Import RMTree** button in either view to load .rmtree, .sql, or .txt exports.
The importer focuses on populated tables so it extracts individuals, media locations, and media relationships into the existing schema without trying to recreate the original database.

## Media & OCR

The repo includes a deterministic media ingest + OCR pipeline with a CLI entrypoint.

Quick examples:

```bash
python scripts/media_cli.py scan --source data/media
python scripts/media_cli.py ingest --source data/media_ingest
python scripts/media_cli.py ingest --source data/media_ingest --ocr --lang eng
python scripts/media_cli.py legacy-link --legacy-db path/to/legacy.sqlite --dry-run
```

See [docs/media_ingest.md](docs/media_ingest.md) for details and OCR dependencies.

## Data Quality workflow

The Data Quality page (`/data-quality`) is the primary workflow for cleaning data safely. It detects issues, queues fixes, and provides reversible actions.

### What it detects

- **Duplicates:** People, families, duplicate media links, and similar media assets
- **Places:** clusters and similar names with suggested canonical values
- **Dates:** normalizations with confidence and qualifiers
- **Standards:** formatting suggestions for consistent name casing/spacing
- **Integrity:** timeline warnings and relationship checks (death before birth, parent too young, marriage too early, orphan families/events)

Integrity rules (current thresholds):

- Death before birth (same person).
- Parent too young: parent birth year within 12 years of child birth year.
- Parent died before child birth.
- Marriage too early: marriage year within 12 years of spouse birth year.
- Marriage after death: marriage year later than spouse death year.
- Orphaned family: no spouses and no children.
- Orphaned event: no person and no family.

### How to use it

1. Open **Data Quality** and click **Scan for issues**.
2. Work each queue:
   - **Duplicates:** Review a match, choose the record to keep, and merge. Missing fields can be filled automatically.
   - **Places:** Pick a canonical place name and standardize variants.
   - **Dates:** Apply unambiguous normalizations (qualifiers like "About/Abt" are preserved until you choose a standard).
   - **Standards:** Apply suggested name casing/spacing improvements.
3. Use **Change Log** to review actions and undo if needed.

### Notes

- All cleanup actions are logged with undo payloads.
- Date normalization only updates stored dates when the value is unambiguous and has no qualifier.

## Reset to empty

```powershell
.\scripts\Reset-Database.ps1
.\scripts\Setup.ps1
```

## Tests

```powershell
.\scripts\Test.ps1
```

## Mobile UI behaviors and breakpoints

- Uses responsive CSS to support 360–480px widths; grids collapse to single column below 980px.
- Top actions wrap for small screens; primary buttons maintain ~44px height.
- Sticky bottom navigation appears only on small viewports (Tree/People, Unassigned Media, Import, Settings) and highlights the active route.
- Additional bottom padding avoids nav overlap on main content/footers.

## PWA (installable) support

- Manifest: `/static/manifest.webmanifest` with standalone display, 192/512 icons, theme/background color `#0b0f14`.
- Service worker: `/service-worker.js` registered via `/static/pwa.js`.
  - Cache-first for static assets (JS, CSS, icons, manifest).
  - Network-first with cache fallback for HTML shell; API responses are not cached.
- Icons: `/static/icons/icon-192.png` and `/static/icons/icon-512.png`.

## Analytics drilldown contract

- Each chart/table defines a `chartId`, title, and a `getDrilldownPayload` (implemented in `static/analytics.js`) that returns `{ type, filters, label }`.
- Drilldowns call `POST /api/analytics/drilldown` with that payload plus pagination, and render in the right-side drawer.
- To add a new chart, extend `buildDrilldownPayload` with the new `chartId`, add the title to `data-chart-title` in `templates/analytics.html`, and return a `type/filters` pair the backend endpoint can understand.

### Install steps (Android Chrome)

1. Start the app normally (<http://127.0.0.1:3001>).
2. Open the browser menu → “Add to Home screen” / “Install app”.
3. Launch from the home screen icon; it opens in standalone mode.
4. Offline: static shell loads from cache; API calls may fail but UI still renders.

## Manual test checklist

- **Phase 1 (mobile UI)**
  - Emulate 360x800: verify no horizontal scrolling and text remains readable.
  - Ensure bottom nav is visible on mobile, hidden on desktop, and links work.
  - Confirm buttons/list items are finger-friendly (~44px) and spaced.
- **Phase 2 (PWA)**
  - Confirm manifest is accessible at `/static/manifest.webmanifest`.
  - Check service worker registration (Application tab → Service Workers).
  - Verify install prompt available; launch installed app shows standalone UI.
  - Toggle offline and reload: shell + static assets load; APIs may fail gracefully.
