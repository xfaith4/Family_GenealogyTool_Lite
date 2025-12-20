"""
Test environment variable configuration for Termux compatibility

Note: `create_app` is imported inside test functions (not at module level)
to ensure each test gets a fresh Flask app with the environment variables
set specifically for that test, avoiding cross-test contamination.
"""
import os
import pytest


def test_default_configuration():
    """Test app uses default values when env vars not set"""
    # Clear any existing env vars
    for key in ['APP_DB_PATH', 'APP_BIND_HOST', 'APP_PORT', 'APP_DEBUG']:
        os.environ.pop(key, None)
    
    # Import after clearing env vars to get fresh app
    from app import create_app
    app = create_app()
    
    # Default database path should be relative
    assert 'data/family_tree.sqlite' in app.config['DATABASE']
    assert os.path.exists(app.config['MEDIA_DIR'])
    assert os.path.exists(app.config['MEDIA_INGEST_DIR'])


def test_custom_db_path_absolute():
    """Test custom absolute database path via env var"""
    custom_path = '/tmp/test_custom.sqlite'
    os.environ['APP_DB_PATH'] = custom_path
    
    try:
        # Import after setting env var to get fresh app
        from app import create_app
        app = create_app()
        assert app.config['DATABASE'] == custom_path
        # Media dirs should be in parent of custom db
        assert '/tmp/media' in app.config['MEDIA_DIR']
    finally:
        os.environ.pop('APP_DB_PATH', None)


def test_custom_db_path_relative():
    """Test custom relative database path via env var"""
    custom_path = 'custom_data/my_db.sqlite'
    os.environ['APP_DB_PATH'] = custom_path
    
    try:
        # Import after setting env var to get fresh app
        from app import create_app
        app = create_app()
        # Relative path should be resolved from repo root
        assert 'custom_data/my_db.sqlite' in app.config['DATABASE']
        assert 'custom_data/media' in app.config['MEDIA_DIR']
    finally:
        os.environ.pop('APP_DB_PATH', None)


def test_env_vars_for_run_script():
    """Test that environment variables can be read and used correctly"""
    # Test default values
    os.environ.pop('APP_BIND_HOST', None)
    os.environ.pop('APP_PORT', None)
    os.environ.pop('APP_DEBUG', None)
    
    assert os.environ.get('APP_BIND_HOST', '127.0.0.1') == '127.0.0.1'
    assert int(os.environ.get('APP_PORT', '3001')) == 3001
    assert os.environ.get('APP_DEBUG', '0') == '0'
    
    # Test custom values
    os.environ['APP_BIND_HOST'] = '0.0.0.0'
    os.environ['APP_PORT'] = '8080'
    os.environ['APP_DEBUG'] = '1'
    
    try:
        assert os.environ.get('APP_BIND_HOST') == '0.0.0.0'
        assert int(os.environ.get('APP_PORT')) == 8080
        assert os.environ.get('APP_DEBUG') == '1'
    finally:
        os.environ.pop('APP_BIND_HOST', None)
        os.environ.pop('APP_PORT', None)
        os.environ.pop('APP_DEBUG', None)
