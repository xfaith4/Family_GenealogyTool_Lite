# Family Genealogy Tool Lite

Minimal, dependency-light genealogy app designed to run cleanly on Windows.

- **Backend:** Flask
- **Database:** SQLite (single file)
- **Frontend:** Vanilla HTML/CSS/JS (no build step)
- **No Node / no native modules / no WSL / no Docker**

## Quick start (PowerShell)

```powershell
set-executionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\Setup.ps1 
.\scripts\Start.ps1
```

Open: <http://127.0.0.1:3001>

## Importing RMTree exports

Use the **Import RMTree** button in either view to load .rmtree, .sql, or .txt exports.
The importer focuses on populated tables so it extracts individuals, media locations, and media relationships into the existing schema without trying to recreate the original database.

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
1. Start the app normally (http://127.0.0.1:3001).
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
