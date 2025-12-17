from flask import g
from sqlalchemy import create_engine
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
