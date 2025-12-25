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
    
    # Register teardown
    app.teardown_appcontext(close_session)


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


def ensure_data_quality_tables(engine) -> None:
    """Recreate data-quality tables if legacy schemas are missing required columns."""
    inspector = inspect(engine)

    def _needs_rebuild(table_name: str, required_cols: set[str]) -> bool:
        if table_name not in inspector.get_table_names():
            return True
        existing = {col["name"] for col in inspector.get_columns(table_name)}
        return not required_cols.issubset(existing)

    def _recreate(table):
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {table.name}"))
        table.metadata.create_all(engine, tables=[table], checkfirst=False)

    from .models import DataQualityIssue, DataQualityActionLog, DateNormalization

    dq_issue_cols = {
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
    }
    action_log_cols = {
        "id",
        "action_type",
        "payload_json",
        "undo_payload_json",
        "created_at",
        "applied_by",
    }
    date_norm_cols = {
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
    }

    if _needs_rebuild("dq_issues", dq_issue_cols):
        _recreate(DataQualityIssue.__table__)
    if _needs_rebuild("dq_action_log", action_log_cols):
        _recreate(DataQualityActionLog.__table__)
    if _needs_rebuild("date_normalizations", date_norm_cols):
        _recreate(DateNormalization.__table__)
