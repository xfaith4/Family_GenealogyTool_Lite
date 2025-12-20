#!/bin/sh
# Termux run script for Family Genealogy Tool Lite
# This script starts the Flask application with proper configuration

set -e  # Exit on error

echo "=== Family Genealogy Tool Lite - Starting App ==="
echo ""

# Detect script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$REPO_ROOT/.venv"

# Check if virtual environment exists
if [ ! -d "$VENV_DIR" ]; then
    echo "ERROR: Virtual environment not found at $VENV_DIR"
    echo "Please run ./scripts/termux-setup.sh first"
    exit 1
fi

# Activate virtual environment
echo "Activating virtual environment..."
. "$VENV_DIR/bin/activate"

# Check if Python is available
if ! command -v python >/dev/null 2>&1; then
    echo "ERROR: Python not found in virtual environment"
    echo "Please run ./scripts/termux-setup.sh again"
    exit 1
fi

# Set environment variables for configuration
# These can be overridden by the user before running this script
export APP_BIND_HOST="${APP_BIND_HOST:-127.0.0.1}"
export APP_PORT="${APP_PORT:-3001}"
export APP_DEBUG="${APP_DEBUG:-0}"
# APP_DB_PATH defaults to ./data/family_tree.sqlite (handled in app/__init__.py)

echo "Configuration:"
echo "  Bind host: $APP_BIND_HOST"
echo "  Port: $APP_PORT"
echo "  Debug: $APP_DEBUG"
echo ""

# Check if port is already in use
if command -v netstat >/dev/null 2>&1; then
    if netstat -an | grep -q ":$APP_PORT "; then
        echo "WARNING: Port $APP_PORT appears to be in use!"
        echo "If the app fails to start, try:"
        echo "  export APP_PORT=3002"
        echo "  ./scripts/termux-run.sh"
        echo ""
    fi
elif command -v ss >/dev/null 2>&1; then
    if ss -an | grep -q ":$APP_PORT "; then
        echo "WARNING: Port $APP_PORT appears to be in use!"
        echo "If the app fails to start, try:"
        echo "  export APP_PORT=3002"
        echo "  ./scripts/termux-run.sh"
        echo ""
    fi
fi

# Change to repo root
cd "$REPO_ROOT"

# Print access URL
echo "=== Starting Flask application ==="
echo ""
echo "Access the app at: http://${APP_BIND_HOST}:${APP_PORT}"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""
echo "---"
echo ""

# Start the Flask application
python run.py

# This line is only reached if the app stops
echo ""
echo "App stopped."
