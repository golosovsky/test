#!/usr/bin/env bash
# ============================================================
# Oracle Cloud Free Tier — OpenClaw WhatsApp Agent Setup
# ============================================================
# Run this script on a fresh Oracle Cloud ARM instance (Ubuntu 22.04+).
# It installs Docker, clones the config, and starts OpenClaw.
#
# Usage:
#   ssh ubuntu@<your-oracle-ip>
#   curl -sSL <raw-url-to-this-script> | bash
#   # OR:
#   bash setup-oracle.sh
# ============================================================

set -euo pipefail

echo "=========================================="
echo " OpenClaw WhatsApp Agent — Server Setup"
echo "=========================================="

# --- 1. System updates ---
echo ""
echo "[1/5] Updating system packages..."
sudo apt-get update -qq
sudo apt-get upgrade -y -qq

# --- 2. Install Docker ---
echo ""
echo "[2/5] Installing Docker..."
if command -v docker &>/dev/null; then
    echo "  Docker already installed: $(docker --version)"
else
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "$USER"
    echo "  Docker installed. You may need to log out and back in for group changes."
fi

# --- 3. Install Docker Compose plugin ---
echo ""
echo "[3/5] Checking Docker Compose..."
if docker compose version &>/dev/null; then
    echo "  Docker Compose already available: $(docker compose version)"
else
    sudo apt-get install -y -qq docker-compose-plugin
    echo "  Docker Compose installed."
fi

# --- 4. Install useful tools ---
echo ""
echo "[4/5] Installing utilities (jq, rg)..."
sudo apt-get install -y -qq jq ripgrep curl

# --- 5. Create project directory ---
echo ""
echo "[5/5] Setting up project directory..."
PROJECT_DIR="$HOME/whatsapp-agent"

if [ -d "$PROJECT_DIR" ]; then
    echo "  Directory $PROJECT_DIR already exists. Skipping creation."
else
    mkdir -p "$PROJECT_DIR"
    echo "  Created $PROJECT_DIR"
fi

echo ""
echo "=========================================="
echo " Setup complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "  1. Copy your config files to $PROJECT_DIR/"
echo "     (openclaw.json, docker-compose.yml, skills/, .env)"
echo ""
echo "  2. Create your .env file:"
echo "     cp .env.example .env"
echo "     nano .env    # Fill in your API keys"
echo ""
echo "  3. Open firewall for WhatsApp QR code scanning:"
echo "     sudo iptables -I INPUT -p tcp --dport 18789 -j ACCEPT"
echo ""
echo "  4. Start OpenClaw:"
echo "     cd $PROJECT_DIR"
echo "     docker compose up -d"
echo ""
echo "  5. Run the onboard wizard to link WhatsApp:"
echo "     docker compose exec openclaw node dist/index.js onboard"
echo ""
echo "  6. Scan the QR code with WhatsApp on the new SIM phone"
echo ""
echo "  7. After linking, close the firewall port:"
echo "     sudo iptables -D INPUT -p tcp --dport 18789 -j ACCEPT"
echo ""
echo "  8. Check logs:"
echo "     docker compose logs -f openclaw"
echo ""
