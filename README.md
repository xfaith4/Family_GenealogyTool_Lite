# Family Genealogy Tool Lite

Minimal, dependency-light genealogy app designed to run cleanly on Windows.

- **Backend:** Flask
- **Database:** SQLite (single file)
- **Frontend:** Vanilla HTML/CSS/JS (no build step)
- **No Node / no native modules / no WSL / no Docker**

## Table of Contents
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Backup & Restore](#backup--restore)
- [Diagnostics](#diagnostics)
- [Troubleshooting](#troubleshooting)
- [Development](#development)

## Installation

### Prerequisites
- **Python 3.11 or higher** - [Download Python](https://www.python.org/downloads/)
  - During installation, check "Add Python to PATH"
  - Verify installation: `python --version` or `py --version`

### Windows Setup

1. **Download/Clone the repository**
   ```powershell
   git clone https://github.com/xfaith4/Family_GenealogyTool_Lite.git
   cd Family_GenealogyTool_Lite
   ```

2. **Run Setup**
   ```powershell
   .\scripts\Setup.ps1
   ```
   
   This will:
   - Install Flask (the only dependency)
   - Create the SQLite database
   - Set up the data directory structure

## Quick Start

### Starting the Application

```powershell
.\scripts\Start.ps1
```

Open your browser to: **http://127.0.0.1:3001**

### First Steps
1. **Create a person** - Click "New Person"
2. **Import GEDCOM** - Click "Import GEDCOM" to upload a genealogy file
3. **Upload media** - Select a person and upload photos/documents
4. **Explore the tree** - Click on people to see their family relationships

### Stopping the Application
Press `Ctrl+C` in the PowerShell window to stop the server.

## Backup & Restore

### Creating a Backup

**Option 1: Using PowerShell Script**
```powershell
.\scripts\Backup.ps1
```

This creates a timestamped backup in `./backups/backup_YYYYMMDD_HHMMSS/` containing:
- Database file (`family_tree.sqlite`)
- Media folder (all uploaded photos/documents)

**Option 2: Using API (programmatic)**
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:3001/api/backup" -Method POST
```

### Restoring from Backup

```powershell
.\scripts\Restore.ps1 -BackupName backup_20231217_120000
```

Replace `backup_20231217_120000` with your actual backup folder name.

**⚠️ Warning:** Restoring will overwrite your current database and media files. Create a backup first if needed.

## Diagnostics

### Using the API

Get system diagnostics:
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:3001/api/diagnostics"
```

Returns:
- App version
- Database path and size
- Schema version
- Record counts (people, families, media)
- Last GEDCOM import timestamp

### Example Output
```json
{
  "app_version": "1.0.0",
  "db_path": "C:/path/to/data/family_tree.sqlite",
  "db_size_bytes": 98304,
  "schema_version": "1.0",
  "counts": {
    "people": 150,
    "families": 45,
    "media": 23,
    "unassigned_media": 0
  },
  "last_import": "2023-12-17 12:34:56"
}
```

## Troubleshooting

### Python Not Found
**Problem:** `python` or `py` command not recognized

**Solution:**
1. Install Python from [python.org](https://www.python.org/downloads/)
2. During installation, check "Add Python to PATH"
3. Restart PowerShell
4. Verify: `python --version`

### Flask Not Installed
**Problem:** `ModuleNotFoundError: No module named 'flask'`

**Solution:**
```powershell
.\scripts\Setup.ps1
```

Or manually:
```powershell
python -m pip install -r requirements.txt
```

### Port Already in Use
**Problem:** `Address already in use` or port 3001 is blocked

**Solution:** Another application is using port 3001. 
- Stop the other application, or
- Edit `run.py` and change the port number

### Database Locked
**Problem:** `database is locked`

**Solution:**
1. Stop all running instances of the app
2. Close any SQLite database browsers
3. Restart the application

### Import GEDCOM Fails
**Problem:** GEDCOM import returns an error

**Solution:**
1. Check the log file: `./logs/app.log`
2. Ensure the GEDCOM file is valid UTF-8 encoded
3. Try with a smaller GEDCOM file first
4. Check for error details in the logs

### Media Upload Fails
**Problem:** Cannot upload photos/documents

**Solution:**
1. Check file size (max 25MB per file)
2. Check available disk space
3. Verify `./data/media` directory exists and is writable
4. Check logs: `./logs/app.log`

### Logs Location
All application logs are stored in: `./logs/app.log`

The log file rotates automatically (max 10MB, keeps 5 backups).

## Development

### Running Tests

```powershell
.\scripts\Test.ps1
```

Or manually:
```powershell
python -m unittest discover -s tests -v
```

### Reset Database

To start fresh with an empty database:
```powershell
.\scripts\Reset-Database.ps1
.\scripts\Setup.ps1
```

**⚠️ Warning:** This deletes all data. Backup first!

### Project Structure
```
Family_GenealogyTool_Lite/
├── app/
│   ├── __init__.py          # App factory
│   ├── db.py                # Database connection
│   ├── routes.py            # API endpoints
│   ├── gedcom.py            # GEDCOM parser
│   ├── logging_config.py    # Logging setup
│   ├── schema.sql           # Database schema
│   ├── static/              # CSS/JS
│   └── templates/           # HTML
├── data/                    # Created by setup
│   ├── family_tree.sqlite   # Database
│   └── media/               # Uploaded files
├── logs/                    # Application logs
├── backups/                 # Database backups
├── scripts/                 # PowerShell scripts
│   ├── Setup.ps1
│   ├── Start.ps1
│   ├── Test.ps1
│   ├── Backup.ps1
│   └── Restore.ps1
├── tests/                   # Unit tests
├── requirements.txt         # Python dependencies
└── run.py                   # Entry point
```

### CI/CD
GitHub Actions automatically runs tests on:
- Push to `main` or `develop` branches
- Pull requests to `main`

See: `.github/workflows/test.yml`

## License
MIT

## Support
For issues and questions, please check:
1. This README's Troubleshooting section
2. Application logs in `./logs/app.log`
3. GitHub Issues
