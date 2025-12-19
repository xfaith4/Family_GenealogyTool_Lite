from flask import Flask
from pathlib import Path

def create_app(test_config: dict | None = None) -> Flask:
    """
    App factory.

    Minimal dependencies: Flask only (SQLite is built-in).
    """
    app = Flask(__name__, instance_relative_config=False)

    repo_root = Path(__file__).resolve().parents[1]
    data_dir = repo_root / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "media").mkdir(exist_ok=True)
    (data_dir / "media_ingest").mkdir(exist_ok=True)

    app.config.from_mapping(
        DATABASE=str(data_dir / "family_tree.sqlite"),
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
        from .db import get_engine, ensure_media_links_asset_id
        from .models import Base
        engine = get_engine()
        Base.metadata.create_all(engine)
        ensure_media_links_asset_id(engine)

    return app
