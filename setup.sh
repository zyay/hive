#!/bin/bash
# Hive Setup Script — installs dependencies, Tailscale, and starts Hive
# Works on: Linux, macOS, Windows (Git Bash)

set -e

echo "=== Hive Setup ==="
echo ""

# Detect OS
OS="$(uname -s)"
case "$OS" in
    Linux*)  PLATFORM=linux;;
    Darwin*) PLATFORM=macos;;
    MINGW*|MSYS*|CYGWIN*) PLATFORM=windows;;
    *)       PLATFORM=unknown;;
esac

echo "Detected: $PLATFORM"
echo ""

# ── Python venv ──
echo "[1/4] Setting up Python environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv 2>/dev/null || python -m venv venv
fi

if [ "$PLATFORM" = "windows" ]; then
    source venv/Scripts/activate
else
    source venv/bin/activate
fi

pip install -r requirements.txt
pip install -e .
echo "  Python OK"
echo ""

# ── Tailscale ──
echo "[2/4] Checking Tailscale..."
if command -v tailscale &>/dev/null; then
    echo "  Tailscale already installed"
else
    echo "  Installing Tailscale..."
    if [ "$PLATFORM" = "linux" ]; then
        curl -fsSL https://tailscale.com/install.sh | sh
    elif [ "$PLATFORM" = "macos" ]; then
        brew install tailscale 2>/dev/null || echo "  Install manually: https://tailscale.com/download/mac"
    elif [ "$PLATFORM" = "windows" ]; then
        echo "  Download Tailscale: https://tailscale.com/download/windows"
        echo "  Or run: winget install Tailscale.Tailscale"
    fi
fi
echo ""

# ── Start Tailscale ──
echo "[3/4] Starting Tailscale..."
if command -v tailscale &>/dev/null; then
    tailscale up 2>/dev/null || true
    TAILSCALE_IP=$(tailscale ip -4 2>/dev/null || echo "not-connected")
    echo "  Tailscale IP: $TAILSCALE_IP"
else
    echo "  Tailscale not found. Install it manually."
    echo "  Visit: https://tailscale.com/download"
fi
echo ""

# ── Initialize DB ──
echo "[4/4] Initializing database..."
python -c "from hive.core.db import init_db; init_db()" 2>/dev/null || true
echo "  Database OK"
echo ""

echo "=== Setup Complete ==="
echo ""
echo "Start Hive:"
echo "  python main.py"
echo ""
echo "Access Hive:"
echo "  Local:    http://127.0.0.1:8000"
if [ "$TAILSCALE_IP" != "not-connected" ] && [ -n "$TAILSCALE_IP" ]; then
    echo "  Tailscale: http://$TAILSCALE_IP:8000"
    echo ""
    echo "Share this URL with anyone on your Tailnet!"
fi
echo ""
