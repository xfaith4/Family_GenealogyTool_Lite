import os
from app import create_app

app = create_app()

if __name__ == "__main__":
    # Environment-driven configuration for Termux and other environments
    host = os.environ.get("APP_BIND_HOST", "127.0.0.1")
    port = int(os.environ.get("APP_PORT", "3001"))
    debug = os.environ.get("APP_DEBUG", "0") == "1"
    
    app.run(host=host, port=port, debug=debug)
