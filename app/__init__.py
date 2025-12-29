from flask import Flask
from pathlib import Path
import os

def create_app(test_config: dict | None = None) -> Flask:
    """
    App factory.

    Minimal dependencies: Flask only (SQLite is built-in).
    """
    app = Flask(__name__, instance_relative_config=False)

    repo_root = Path(__file__).resolve().parents[1]
    
    # Support environment variable for database path (for Termux and other environments)
    db_path_env = os.environ.get("APP_DB_PATH")
    if db_path_env:
        db_path = Path(db_path_env)
        # Convert relative paths to absolute based on repo root
        if not db_path.is_absolute():
            db_path = repo_root / db_path
    else:
        # Default path
        db_path = repo_root / "data" / "family_tree.sqlite"
    
    # Ensure parent directory exists
    data_dir = db_path.parent
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "media").mkdir(exist_ok=True)
    (data_dir / "media_ingest").mkdir(exist_ok=True)

    app.config.from_mapping(
        DATABASE=str(db_path),
        MEDIA_DIR=str(data_dir / "media"),
        MEDIA_INGEST_DIR=str(data_dir / "media_ingest"),
        MAX_CONTENT_LENGTH=25 * 1024 * 1024,
        JSON_SORT_KEYS=False,
        TESTING=False,
    )

    if test_config:
        app.config.update(test_config)

    from . import db
    db.init_app(app)

    from .routes import api_bp, ui_bp
    app.register_blueprint(api_bp)
    app.register_blueprint(ui_bp)

    # Ensure tables exist for tests and first-run scenarios
    with app.app_context():
        from .db import (
            get_engine,
            ensure_media_links_asset_id,
            ensure_media_assets_status,
            ensure_data_quality_tables,
            ensure_person_attributes_table,
        )
        from .models import Base
        engine = get_engine()
        Base.metadata.create_all(engine)
        ensure_media_links_asset_id(engine)
        ensure_media_assets_status(engine)
        ensure_data_quality_tables(engine)
        ensure_person_attributes_table(engine)

    return app
