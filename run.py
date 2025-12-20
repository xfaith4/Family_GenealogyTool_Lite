import os
import sys

try:
    from app import create_app
except (ModuleNotFoundError, ImportError) as e:
    print("=" * 70)
    print("ERROR: Required dependencies are not installed.")
    print("=" * 70)
    
    # Extract module name safely from the error message
    module_name = 'unknown'
    if hasattr(e, 'name') and e.name:
        module_name = e.name
    else:
        # Try to parse module name from error message
        error_msg = str(e)
        if "'" in error_msg:
            try:
                module_name = error_msg.split("'")[1]
            except IndexError:
                pass
    
    print(f"\nMissing module: {module_name}")
    print("\nPlease run the setup script first:")
    print("  • On Termux/Linux: ./scripts/termux-setup.sh")
    print("  • On Windows:      .\\scripts\\Setup.ps1")
    print("  • Manual setup:    pip install -r requirements.txt")
    print("\nSee README.md or docs/TERMUX.md for detailed setup instructions.")
    print("=" * 70)
    sys.exit(1)

app = create_app()

if __name__ == "__main__":
    # Environment-driven configuration for Termux and other environments
    host = os.environ.get("APP_BIND_HOST", "127.0.0.1")
    port = int(os.environ.get("APP_PORT", "3001"))
    debug = os.environ.get("APP_DEBUG", "0") == "1"
    
    app.run(host=host, port=port, debug=debug)
