#!/bin/sh
# Termux setup script for Family Genealogy Tool Lite
# This script installs all necessary dependencies and initializes the database

set -e  # Exit on error

echo "=== Family Genealogy Tool Lite - Termux Setup ==="
echo ""

# Detect script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DATA_DIR="$REPO_ROOT/data"
DB_PATH="$DATA_DIR/family_tree.sqlite"

echo "Repository root: $REPO_ROOT"
echo "Database path: $DB_PATH"
echo ""

# Check if running in Termux
if [ -z "$PREFIX" ]; then
    echo "WARNING: \$PREFIX is not set. This script is designed for Termux."
    echo "Attempting to continue anyway..."
    echo ""
fi

# Update package list
echo "Updating Termux packages..."
pkg update -y || {
    echo "ERROR: Failed to update packages. Try running 'pkg update' manually."
    exit 1
}

# Install required packages
echo ""
echo "Installing required Termux packages..."
echo "This may take several minutes on first run..."

# Install base packages and image libraries needed for Pillow
pkg install -y python git binutils libjpeg-turbo libpng zlib || {
    echo "ERROR: Failed to install packages. Check your internet connection."
    exit 1
}

echo ""
echo "Termux packages installed successfully."
echo ""

# Find Python
PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "ERROR: Python not found after installation. Please install manually with 'pkg install python'."
    exit 1
fi

echo "Using Python: $PYTHON"
"$PYTHON" --version
echo ""

# Setup virtual environment (recommended on Termux to avoid conflicts)
VENV_DIR="$REPO_ROOT/.venv"
if [ -d "$VENV_DIR" ]; then
    echo "Virtual environment already exists at $VENV_DIR"
else
    echo "Creating Python virtual environment..."
    "$PYTHON" -m venv "$VENV_DIR" || {
        echo "ERROR: Failed to create virtual environment."
        echo "Try: pkg install python-pip"
        exit 1
    }
    echo "Virtual environment created."
fi

# Activate virtual environment
echo ""
echo "Activating virtual environment..."
. "$VENV_DIR/bin/activate"

# Upgrade pip
echo ""
echo "Upgrading pip..."
pip install --upgrade pip

# Install Python dependencies
echo ""
echo "Installing Python dependencies from requirements.txt..."
echo "This may take several minutes..."
pip install -r "$REPO_ROOT/requirements.txt" || {
    echo "ERROR: Failed to install Python dependencies."
    echo "Check the error messages above for details."
    exit 1
}

echo ""
echo "Python dependencies installed successfully."

# Ensure data directories exist
echo ""
echo "Creating data directories..."
mkdir -p "$DATA_DIR"
mkdir -p "$DATA_DIR/media"
mkdir -p "$DATA_DIR/media_ingest"

# Remove existing database to avoid conflicts (fresh setup)
echo ""
echo "⚠️  WARNING: This will remove any existing database!"
if [ -f "$DB_PATH" ]; then
    echo "Removing existing database for fresh setup..."
    rm -f "$DB_PATH"
    rm -f "${DB_PATH}-wal"
    rm -f "${DB_PATH}-shm"
    echo "Old database removed."
else
    echo "No existing database found."
fi

# Run database migrations
echo ""
echo "Running database migrations..."
cd "$REPO_ROOT"
python -m alembic upgrade head || {
    echo "ERROR: Database migration failed."
    exit 1
}

echo ""
echo "=== Setup Complete! ==="
echo ""
echo "To start the app, run:"
echo "  ./scripts/termux-run.sh"
echo ""
echo "Or manually:"
echo "  source .venv/bin/activate"
echo "  python run.py"
echo ""
echo "The app will be available at: http://127.0.0.1:3001"
echo ""
