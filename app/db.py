from flask import g
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session

# Global engine and session factory
_engine = None
_SessionLocal = None

def init_engine(database_url: str) -> None:
    """Initialize the SQLAlchemy engine and session factory."""
    global _engine, _SessionLocal
    _engine = create_engine(
        database_url,
        echo=False,
        connect_args={"check_same_thread": False} if database_url.startswith("sqlite") else {}
    )
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)

    # Non-breaking startup migrations / legacy compatibility
    ensure_places_authority_columns(_engine)
    ensure_place_normalization_rules(_engine)
    ensure_media_links_asset_id(_engine)
    ensure_media_assets_status(_engine)
    ensure_media_derivations_table(_engine)
    ensure_data_quality_tables(_engine)
    ensure_person_attributes_table(_engine)

def get_engine():
    """Get the SQLAlchemy engine."""
    return _engine

def get_session() -> Session:
    """Get a SQLAlchemy session tied to the Flask request context."""
    if "db_session" not in g:
        g.db_session = _SessionLocal()
    return g.db_session

def close_session(e=None) -> None:
    """Close the SQLAlchemy session at the end of the request."""
    session = g.pop("db_session", None)
    if session is not None:
        session.close()

def init_app(app) -> None:
    """Initialize database with Flask app."""
    from pathlib import Path
    
    # Initialize engine
    db_path = app.config["DATABASE"]
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    database_url = f"sqlite:///{db_path}"
    init_engine(database_url)

    # Non-breaking migration: add optional place authority fields
    ensure_places_authority_columns(get_engine())
    ensure_person_attributes_table(get_engine())

    # Register teardown
    app.teardown_appcontext(close_session)


def ensure_places_authority_columns(engine) -> None:
    """Add places.authority_source and places.authority_id for legacy DBs (idempotent)."""
    inspector = inspect(engine)
    if "places" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("places")}
    with engine.begin() as conn:
        if "authority_source" not in columns:
            conn.execute(text("ALTER TABLE places ADD COLUMN authority_source TEXT"))
        if "authority_id" not in columns:
            conn.execute(text("ALTER TABLE places ADD COLUMN authority_id TEXT"))

        # Helpful indexes for lookups / joins
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_places_authority_source ON places(authority_source)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_places_authority_id ON places(authority_id)"))



def ensure_place_normalization_rules(engine) -> None:
    """Create place_normalization_rules table if it does not exist (non-breaking)."""
    inspector = inspect(engine)
    if "place_normalization_rules" in inspector.get_table_names():
        return
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS place_normalization_rules (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              canonical TEXT NOT NULL UNIQUE,
              variants_json TEXT NOT NULL,
              approved INTEGER NOT NULL DEFAULT 0,
              source_issue_id INTEGER,
              authority_source TEXT,
              authority_id TEXT,
              latitude REAL,
              longitude REAL,
              notes TEXT,
              created_at DATETIME NOT NULL DEFAULT (datetime('now')),
              updated_at DATETIME NOT NULL DEFAULT (datetime('now'))
            )
            """
        ))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_place_norm_rules_approved ON place_normalization_rules(approved)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_place_norm_rules_source_issue ON place_normalization_rules(source_issue_id)"))

def ensure_media_links_asset_id(engine) -> None:
    """Backfill asset_id column for legacy databases missing it."""
    inspector = inspect(engine)
    if "media_links" not in inspector.get_table_names():
        return

    def _create_media_links_table(conn):
        conn.execute(
            text(
                """
                CREATE TABLE media_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_id INTEGER NOT NULL,
                    person_id INTEGER,
                    family_id INTEGER,
                    description TEXT,
                    created_at DATETIME NOT NULL,
                    FOREIGN KEY(asset_id) REFERENCES media_assets(id) ON DELETE CASCADE,
                    FOREIGN KEY(person_id) REFERENCES persons(id) ON DELETE CASCADE,
                    FOREIGN KEY(family_id) REFERENCES families(id) ON DELETE CASCADE
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_media_links_person ON media_links(person_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_media_links_family ON media_links(family_id)"))

def ensure_media_derivations_table(engine) -> None:
    """Create media_derivations table if missing (idempotent)."""
    inspector = inspect(engine)
    if "media_derivations" in inspector.get_table_names():
        return
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE media_derivations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_asset_id INTEGER NOT NULL,
                derived_asset_id INTEGER NOT NULL,
                derivation_type TEXT NOT NULL,
                created_at DATETIME NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY(original_asset_id) REFERENCES media_assets(id) ON DELETE CASCADE,
                FOREIGN KEY(derived_asset_id) REFERENCES media_assets(id) ON DELETE CASCADE
            )
            """
        ))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_media_derivations_original ON media_derivations(original_asset_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_media_derivations_derived ON media_derivations(derived_asset_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_media_derivations_type ON media_derivations(derivation_type)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_media_links_asset ON media_links(asset_id)"))

    columns = {col["name"] for col in inspector.get_columns("media_links")}
    if "asset_id" in columns:
        with engine.begin() as conn:
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_media_links_asset ON media_links(asset_id)"))
        return

    with engine.begin() as conn:
        if "media_asset_id" in columns:
            conn.execute(text("ALTER TABLE media_links RENAME TO media_links_old"))
            _create_media_links_table(conn)
            conn.execute(
                text(
                    """
                    INSERT INTO media_links (id, asset_id, person_id, family_id, description, created_at)
                    SELECT id, media_asset_id, person_id, family_id, description, created_at
                    FROM media_links_old
                    WHERE media_asset_id IS NOT NULL
                    """
                )
            )
            conn.execute(text("DROP TABLE media_links_old"))
        else:
            row_count = conn.execute(text("SELECT COUNT(*) FROM media_links")).scalar()
            if row_count == 0:
                conn.execute(text("DROP TABLE media_links"))
                _create_media_links_table(conn)
            else:
                conn.execute(text("ALTER TABLE media_links ADD COLUMN asset_id INTEGER"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_media_links_asset ON media_links(asset_id)"))


def ensure_media_assets_status(engine) -> None:
    """Add status/source_path columns for legacy media_assets tables and backfill values."""
    inspector = inspect(engine)
    if "media_assets" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("media_assets")}
    has_media_links = "media_links" in inspector.get_table_names()

    with engine.begin() as conn:
        if "status" not in columns:
            conn.execute(text("ALTER TABLE media_assets ADD COLUMN status VARCHAR(50) NOT NULL DEFAULT 'unassigned'"))
        if "source_path" not in columns:
            conn.execute(text("ALTER TABLE media_assets ADD COLUMN source_path VARCHAR(500)"))

        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_media_assets_original_filename ON media_assets(original_filename)"))
        if has_media_links:
            conn.execute(
                text(
                    "UPDATE media_assets "
                    "SET status='assigned' "
                    "WHERE id IN (SELECT DISTINCT asset_id FROM media_links WHERE asset_id IS NOT NULL)"
                )
            )
        conn.execute(text("UPDATE media_assets SET status='unassigned' WHERE status IS NULL OR status=''"))


def ensure_data_quality_tables(engine) -> None:
    """
    Recreate data-quality tables if legacy schemas are missing required columns.
    NOTE: This may drop and recreate the affected table when columns are missing.
    """
    inspector = inspect(engine)

    def _needs_rebuild(table_name: str, required_cols: set[str]) -> bool:
        if table_name not in inspector.get_table_names():
            return True
        existing = {col["name"] for col in inspector.get_columns(table_name)}
        return not required_cols.issubset(existing)

    def _recreate(table):
        table.drop(engine, checkfirst=True)
        table.create(engine, checkfirst=False)

    from .models import DataQualityIssue, DataQualityActionLog, DateNormalization

    schemas = {
        "dq_issues": (
            DataQualityIssue.__table__,
            {
                "id",
                "issue_type",
                "severity",
                "entity_type",
                "entity_ids",
                "status",
                "confidence",
                "impact_score",
                "explanation_json",
                "detected_at",
                "resolved_at",
            },
        ),
        "dq_action_log": (
            DataQualityActionLog.__table__,
            {
                "id",
                "action_type",
                "payload_json",
                "undo_payload_json",
                "created_at",
                "applied_by",
            },
        ),
        "date_normalizations": (
            DateNormalization.__table__,
            {
                "id",
                "entity_type",
                "entity_id",
                "raw_value",
                "normalized",
                "precision",
                "qualifier",
                "confidence",
                "is_ambiguous",
                "detected_at",
            },
        ),
    }

    for name, (table, cols) in schemas.items():
        if _needs_rebuild(name, cols):
            _recreate(table)


def ensure_person_attributes_table(engine) -> None:
    """Create person_attributes table for legacy databases (idempotent)."""
    inspector = inspect(engine)
    if "person_attributes" in inspector.get_table_names():
        return

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE person_attributes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_person_attributes_person_key ON person_attributes(person_id, key)"))
