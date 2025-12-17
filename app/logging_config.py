"""
Structured logging configuration.
"""
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler

def setup_logging(app):
    """
    Configure structured logging to file.
    Logs are written to logs/app.log with rotation.
    """
    repo_root = Path(__file__).resolve().parents[1]
    log_dir = repo_root / "logs"
    log_dir.mkdir(exist_ok=True)
    
    log_file = log_dir / "app.log"
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # File handler with rotation (10MB max, keep 5 backups)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=5
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    
    # Console handler for development
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    # Configure app logger
    app.logger.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)
    
    # Also configure werkzeug logger (Flask's HTTP logs)
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.setLevel(logging.INFO)
    werkzeug_logger.addHandler(file_handler)
    
    app.logger.info(f"Logging initialized. Log file: {log_file}")
    
    return app.logger
