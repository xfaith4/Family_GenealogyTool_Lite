# Running Family Genealogy Tool Lite on Android (Termux)

This guide explains how to run the Family Genealogy Tool Lite web app locally on your Android device using Termux—no root access or Docker required.

## Prerequisites

1. **Termux**: Install from [F-Droid](https://f-droid.org/en/packages/com.termux/) (not Google Play, as the Play Store version is outdated)
2. **Android device** with at least 1GB free storage
3. **Internet connection** for initial setup

## Quick Start

### 1. Install Termux

Download and install Termux from F-Droid:
- Visit https://f-droid.org on your Android device
- Search for "Termux"
- Install the app

### 2. Initial Termux Setup

Open Termux and grant storage permissions (optional but recommended for future file access):

```bash
termux-setup-storage
```

This will prompt for permission to access device storage. Tap "Allow" to continue.

### 3. Clone the Repository

```bash
# Install git if not already available
pkg install git -y

# Clone the repository
cd ~
git clone https://github.com/xfaith4/Family_GenealogyTool_Lite.git
cd Family_GenealogyTool_Lite
```

### 4. Run Setup Script

This installs all dependencies and initializes the database:

```bash
chmod +x scripts/termux-setup.sh
./scripts/termux-setup.sh
```

**Note**: This step may take 10-15 minutes on first run as it downloads and compiles Python packages. Be patient!

### 5. Start the App

```bash
chmod +x scripts/termux-run.sh
./scripts/termux-run.sh
```

The app will start and display:
```
Access the app at: http://127.0.0.1:3001
```

### 6. Access the App

Open your browser (Chrome, Firefox, etc.) and navigate to:
```
http://127.0.0.1:3001
```

**Success!** You should see the Family Genealogy Tool interface.

## Configuration

### Environment Variables

You can customize the app behavior by setting environment variables before running:

```bash
# Change the port (default: 3001)
export APP_PORT=8080
./scripts/termux-run.sh

# Change the bind host (default: 127.0.0.1)
export APP_BIND_HOST=0.0.0.0
./scripts/termux-run.sh

# Enable debug mode (default: disabled)
export APP_DEBUG=1
./scripts/termux-run.sh

# Custom database location (default: ./data/family_tree.sqlite)
export APP_DB_PATH=/path/to/custom/db.sqlite
./scripts/termux-run.sh
```

**Security Note**: Binding to `0.0.0.0` makes the app accessible on your local network. Only use this if you understand the security implications.

## Manual Setup (Alternative)

If you prefer manual control, follow these steps:

```bash
# 1. Install packages
pkg update
pkg install python git binutils -y

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 4. Initialize database
python -m alembic upgrade head

# 5. Start the app
python run.py
```

## Keeping the App Running in Background

### Option 1: Using tmux (Recommended)

Install tmux to keep the app running when you close Termux:

```bash
# Install tmux
pkg install tmux -y

# Start a new tmux session
tmux new -s genealogy

# Run the app
./scripts/termux-run.sh

# Detach from session: Press Ctrl+B, then D
# Reattach later: tmux attach -t genealogy
# Kill session: tmux kill-session -t genealogy
```

### Option 2: Using Termux:Boot (Optional)

For automatic startup on device boot:

1. Install [Termux:Boot](https://f-droid.org/en/packages/com.termux.boot/) from F-Droid
2. Create boot script:

```bash
mkdir -p ~/.termux/boot
cat > ~/.termux/boot/start-genealogy.sh << 'EOF'
#!/data/data/com.termux/files/usr/bin/sh
cd ~/Family_GenealogyTool_Lite
./scripts/termux-run.sh
EOF
chmod +x ~/.termux/boot/start-genealogy.sh
```

3. Reboot your device to test

## Troubleshooting

### Port Already in Use

**Symptom**: Error message `Address already in use`

**Solution**: 
```bash
# Check what's using the port
netstat -an | grep 3001

# Use a different port
export APP_PORT=3002
./scripts/termux-run.sh
```

### Permission Denied Errors

**Symptom**: `Permission denied` when accessing files

**Solution**:
```bash
# Grant storage permissions
termux-setup-storage

# Ensure scripts are executable
chmod +x scripts/termux-setup.sh scripts/termux-run.sh
```

### Package Installation Failures

**Symptom**: `pkg install` or `pip install` fails

**Solution**:
```bash
# Update package lists
pkg update
pkg upgrade

# Clear pip cache
pip cache purge

# Try installing dependencies one at a time
pip install Flask
pip install Pillow
pip install SQLAlchemy
pip install alembic
pip install pytest
```

### Python Module Not Found

**Symptom**: `ModuleNotFoundError` when starting the app

**Solution**:
```bash
# Ensure virtual environment is activated
source .venv/bin/activate

# Reinstall requirements
pip install -r requirements.txt
```

### Database Migration Errors

**Symptom**: Alembic migration fails or database errors on startup

**Solution**:
```bash
# Remove corrupted database
rm -f data/family_tree.sqlite*

# Re-run migrations
python -m alembic upgrade head
```

### App Not Accessible in Browser

**Symptom**: Browser can't connect to `http://127.0.0.1:3001`

**Solution**:
1. Verify the app is running (look for "Running on http://127.0.0.1:3001" message)
2. Try `http://localhost:3001` instead
3. Check if port is blocked: `netstat -an | grep 3001`
4. Restart the app with a different port

### Slow Performance

**Symptom**: App is very slow or unresponsive

**Solution**:
- Ensure you have enough free RAM (at least 500MB)
- Close other apps to free memory
- Consider using a device with more RAM
- Disable debug mode: `unset APP_DEBUG`

### Out of Storage Space

**Symptom**: Installation fails due to insufficient space

**Solution**:
```bash
# Check available space
df -h $HOME

# Clean up Termux package cache
pkg clean

# Remove old pip cache
pip cache purge
```

### "Python not found" After Setup

**Symptom**: Python command not found in virtual environment

**Solution**:
```bash
# Verify Python installation
pkg list-installed | grep python

# Recreate virtual environment
rm -rf .venv
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Health Check Failed

**Symptom**: App starts but doesn't respond to requests

**Solution**:
```bash
# Test the health endpoint
curl http://127.0.0.1:3001/api/health

# If it returns {"ok":true}, the app is working
# If connection refused, check if app is actually running
```

## Updating the App

To update to the latest version:

```bash
cd ~/Family_GenealogyTool_Lite

# Stop the app if running (Ctrl+C)

# Pull latest changes
git pull origin main

# Activate virtual environment
source .venv/bin/activate

# Update dependencies
pip install -r requirements.txt

# Run migrations (if any)
python -m alembic upgrade head

# Restart the app
./scripts/termux-run.sh
```

## Uninstalling

To completely remove the app:

```bash
# Stop the app if running (Ctrl+C)

# Delete the repository
cd ~
rm -rf Family_GenealogyTool_Lite

# Remove virtual environment is inside the repo, so it's already deleted

# Optionally uninstall Termux packages (if not needed for other apps)
pkg uninstall python git binutils
```

## Performance Tips

1. **Use a modern device**: Android 8.0+ with at least 2GB RAM recommended
2. **Close background apps**: Free up RAM before starting the app
3. **Use tmux**: Prevents the app from stopping when you switch apps
4. **Disable debug mode**: Set `APP_DEBUG=0` for better performance
5. **Use WiFi**: Faster than mobile data for downloading dependencies

## Security Considerations

- **Default binding**: The app binds to `127.0.0.1` (localhost only) for security
- **No remote access**: By default, the app is only accessible from your device
- **Debug mode**: Disabled by default in production to avoid leaking sensitive info
- **Database**: Stored locally on your device; not synced to cloud automatically
- **Backups**: Regularly backup `data/family_tree.sqlite` to prevent data loss

## Accessing from Other Devices (Advanced)

⚠️ **Warning**: Only do this on a trusted private network!

To access the app from other devices on your local network:

```bash
# Find your device's IP address
ifconfig

# Look for an address like 192.168.1.xxx

# Start app bound to all interfaces
export APP_BIND_HOST=0.0.0.0
./scripts/termux-run.sh

# Access from other devices at:
# http://192.168.1.xxx:3001
```

## Additional Resources

- **Main README**: See `README.md` in the repository root
- **Import Guide**: See `IMPORT_RMTREE.md` for importing family tree data
- **Data Quality**: See `DataQuality.md` for data cleanup tools
- **Termux Wiki**: https://wiki.termux.com
- **F-Droid**: https://f-droid.org

## Known Limitations on Termux

1. **No native SQLite CLI**: Use Python instead: `python -c "import sqlite3; ..."`
2. **Limited RAM**: Large family trees (>10,000 people) may be slow
3. **Storage access**: Requires `termux-setup-storage` for external storage
4. **Battery usage**: Keep device plugged in for long sessions
5. **Network changes**: May need to restart if switching WiFi/mobile data

## Getting Help

If you encounter issues not covered here:

1. Check the main README.md for general app documentation
2. Review error messages carefully—they often indicate the solution
3. Search existing GitHub issues: https://github.com/xfaith4/Family_GenealogyTool_Lite/issues
4. Open a new issue with:
   - Your Android version
   - Termux version
   - Error messages (full output)
   - Steps to reproduce

---

**Happy genealogy research on Android! 📱🌳**
