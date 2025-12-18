# Family Genealogy Tool Lite

Minimal, dependency-light genealogy app designed to run cleanly on Windows.

- **Backend:** Flask
- **Database:** SQLite (single file)
- **Frontend:** Vanilla HTML/CSS/JS (no build step)
- **No Node / no native modules / no WSL / no Docker**

## Quick start (PowerShell)

```powershell
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
