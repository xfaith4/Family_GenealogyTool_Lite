# Migration to SQLAlchemy + Alembic

## Summary of Changes

This implementation successfully introduces SQLAlchemy 2.x ORM and Alembic migrations to the Family Genealogy Tool while maintaining complete backward compatibility with existing functionality.

## Key Features Added

### 1. SQLAlchemy 2.x Models (`app/models.py`)

All database entities are now defined as SQLAlchemy ORM models:

- **Person**: Core person entity with legacy date/place fields preserved
- **Family**: Family unit linking spouses and children  
- **Event**: Typed events (birth, death, marriage, etc.) with:
  - `date_raw` and `place_raw` for original GEDCOM data
  - `date_canonical` for normalized datetime queries
  - Support for typed events via EventType enum
- **Place**: Canonical place names with optional coordinates
- **PlaceVariant**: Multiple name variants for same place (future standardization)
- **MediaAsset**: Actual media file metadata
- **MediaLink**: Links media to persons/families (supports unassigned media)
- **Note**: Text notes attached to persons or families
- **DataQualityFlags**: Framework for tracking data quality issues

### 2. Alembic Migrations

- Initial migration creates complete schema from scratch
- Migration files in `migrations/versions/`
- `alembic.ini` configured for SQLite database
- `migrations/env.py` imports models for autogenerate support

### 3. Updated Database Layer (`app/db.py`)

- Replaced raw SQLite connections with SQLAlchemy engine/session
- Session management integrated with Flask request context
- Clean separation of concerns

### 4. Updated Routes (`app/routes.py`)

All API endpoints now use SQLAlchemy ORM:
- Type-safe queries with SQLAlchemy 2.x syntax
- Cleaner relationship navigation
- Better error handling

### 5. Updated Scripts

**Setup.ps1**:
- Now runs `alembic upgrade head` to create/update database
- No manual schema.sql execution needed

**Reset-Database.ps1**:
- Cleans up database and WAL files
- User must run Setup.ps1 after reset

### 6. New Tests

Added two required tests in `tests/test_api.py`:

1. **test_migration_creates_empty_db**: Verifies migration creates all 11 required tables
2. **test_gedcom_import_populates_expected_rows**: Verifies GEDCOM import correctly populates database

## Database Schema

### Tables Created

1. `persons` - Core person data
2. `families` - Family relationships  
3. `events` - Typed events with raw/canonical fields
4. `places` - Canonical place names
5. `place_variants` - Place name variants
6. `media_assets` - Media file metadata
7. `media_links` - Person/family media associations
8. `notes` - Text annotations
9. `data_quality_flags` - Data quality tracking
10. `family_children` - Family child associations
11. `relationships` - Parent-child relationships
12. `alembic_version` - Migration version tracking

### Key Schema Features

- **Foreign key constraints** with proper ON DELETE behavior
- **Indexes** on frequently queried columns (names, xrefs, dates)
- **Unique constraints** on xrefs, canonical place names, media sha256
- **DateTime columns** for proper date handling (instead of TEXT)
- **Typed enums** for event types and severities

## Backward Compatibility

✅ **All existing API endpoints work unchanged**
✅ **GEDCOM import preserves original date/place strings**  
✅ **All 8 original tests pass without modification**
✅ **UI templates work without changes**
✅ **Legacy `birth_date`, `birth_place`, etc. fields preserved on Person and Family models**

## Testing Results

```
Ran 10 tests in 0.536s
OK
```

- 8 original tests (unchanged)
- 2 new tests for migration and import verification
- **0 CodeQL security vulnerabilities**
- All code review feedback addressed

## Migration Workflow

### Fresh Setup
```powershell
.\scripts\Setup.ps1
```

This will:
1. Install Python dependencies (Flask, SQLAlchemy, Alembic)
2. Run `alembic upgrade head` to create database

### Reset Database
```powershell
.\scripts\Reset-Database.ps1
.\scripts\Setup.ps1
```

### Manual Migration Commands
```bash
# Create new migration after model changes
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Show current version
alembic current
```

## File Changes

### New Files
- `app/models.py` - SQLAlchemy model definitions (11KB)
- `alembic.ini` - Alembic configuration
- `migrations/env.py` - Alembic environment setup
- `migrations/versions/10740efec864_*.py` - Initial migration
- `.gitignore` - Ignore cache, database files

### Modified Files
- `app/db.py` - Replaced raw SQLite with SQLAlchemy
- `app/routes.py` - Use ORM instead of raw SQL (all endpoints)
- `requirements.txt` - Added SQLAlchemy>=2.0, alembic>=1.13
- `scripts/Setup.ps1` - Run alembic migrations
- `scripts/Reset-Database.ps1` - Clean up WAL files
- `tests/test_api.py` - Added setup for SQLAlchemy, 2 new tests

### Removed Files
- `app/schema.sql` - Replaced by Alembic migrations

## Future Enhancements Enabled

This foundation enables:
- ✅ Event-based timeline queries
- ✅ Place standardization and geocoding
- ✅ Advanced media management (unassigned media, multiple links)
- ✅ Data quality analytics
- ✅ Efficient date-range queries with canonical dates
- ✅ Database migrations for schema evolution

## Security Summary

**CodeQL Scan Results**: ✅ **No vulnerabilities found**

All code follows secure practices:
- Parameterized queries via SQLAlchemy (no SQL injection)
- Proper session management
- Secure file handling for media uploads
- Foreign key constraints enforced

## Performance Notes

- SQLAlchemy adds minimal overhead for this app size
- Indexes created on all frequently-queried columns
- Connection pooling handled by SQLAlchemy
- SQLite WAL mode for better concurrency

## Acceptance Criteria

✅ `.\scripts\Setup.ps1` works from clean clone and creates DB via migration  
✅ `python -m unittest discover -s tests -v` passes (10/10 tests)  
✅ GEDCOM import works and app loads UI successfully  
✅ No regressions - all existing endpoints functional  
✅ Migration creates empty DB (verified in tests)  
✅ Import populates expected rows (verified in tests)

## Verified Workflows

1. **Fresh clone → Setup → Start → Import GEDCOM**: ✅ Works
2. **Reset → Setup**: ✅ Works  
3. **All API endpoints**: ✅ Working
4. **GEDCOM import**: ✅ Preserves all data
5. **Tests**: ✅ All pass (10/10)
6. **CodeQL security**: ✅ No issues
