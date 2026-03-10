#!/usr/bin/env bash
# ============================================================
#  OpenClaw WhatsApp Agent — One-Shot Setup
# ============================================================
#  Run on a fresh Ubuntu 22.04+ VM (Oracle Cloud Free Tier, etc.)
#
#  What this does:
#    1. Installs Docker + Docker Compose
#    2. Creates ~/.openclaw with correct permissions
#    3. Copies config, skills, docker-compose.yml into ~/whatsapp-agent
#    4. Prompts for API keys and phone numbers
#    5. Starts OpenClaw and runs doctor --fix
#    6. Guides you through WhatsApp QR linking
#    7. Restarts the gateway so it picks up the new session
#    8. Sends a test prompt
#
#  Usage:
#    git clone <this-repo> ~/whatsapp-agent
#    cd ~/whatsapp-agent
#    bash setup.sh
# ============================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*"; }

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENCLAW_DIR="$HOME/.openclaw"

echo ""
echo "=========================================="
echo " OpenClaw WhatsApp Agent — Full Setup"
echo "=========================================="
echo ""

# ────────────────────────────────────────────
# 1. System packages + Docker
# ────────────────────────────────────────────
info "Step 1/9 — Installing system packages..."

sudo apt-get update -qq
sudo apt-get install -y -qq curl jq

if command -v docker &>/dev/null; then
    ok "Docker already installed: $(docker --version)"
else
    info "Installing Docker..."
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "$USER"
    ok "Docker installed."
fi

if docker compose version &>/dev/null 2>&1; then
    ok "Docker Compose available: $(docker compose version --short)"
else
    info "Installing Docker Compose plugin..."
    sudo apt-get install -y -qq docker-compose-plugin
    ok "Docker Compose installed."
fi

# ────────────────────────────────────────────
# 2. Create ~/.openclaw with correct permissions
# ────────────────────────────────────────────
info "Step 2/9 — Creating ~/.openclaw state directory..."

# These directories must exist BEFORE the container starts, otherwise
# Docker creates them as root and OpenClaw can't write to them.
mkdir -p "$OPENCLAW_DIR"
mkdir -p "$OPENCLAW_DIR/agents/main/sessions"
mkdir -p "$OPENCLAW_DIR/credentials"
mkdir -p "$OPENCLAW_DIR/workspace"

# Restrictive permissions — this dir holds WhatsApp session keys
chmod 700 "$OPENCLAW_DIR"

ok "State directory ready: $OPENCLAW_DIR"

# ────────────────────────────────────────────
# 3. Copy config + skills into ~/.openclaw
# ────────────────────────────────────────────
info "Step 3/9 — Copying configuration files..."

# The config goes into ~/.openclaw (NOT the project dir) because
# the container bind-mounts ~/.openclaw as its home config dir.
# Using a named Docker volume + bind mount overlay causes EBUSY errors.
if [ -f "$PROJECT_DIR/openclaw.json" ]; then
    cp "$PROJECT_DIR/openclaw.json" "$OPENCLAW_DIR/openclaw.json"
    chmod 600 "$OPENCLAW_DIR/openclaw.json"
    ok "Copied openclaw.json → $OPENCLAW_DIR/openclaw.json"
else
    err "openclaw.json not found in $PROJECT_DIR!"
    exit 1
fi

if [ -d "$PROJECT_DIR/skills" ]; then
    cp -r "$PROJECT_DIR/skills" "$OPENCLAW_DIR/skills"
    ok "Copied skills/ → $OPENCLAW_DIR/skills/"
else
    warn "skills/ directory not found — skipping."
fi

# ────────────────────────────────────────────
# 4. Collect API keys
# ────────────────────────────────────────────
info "Step 4/9 — Configuring API keys..."
echo ""

ENV_FILE="$PROJECT_DIR/.env"

if [ -f "$ENV_FILE" ]; then
    warn ".env already exists. Skipping key prompts."
    warn "Edit $ENV_FILE manually if you need to change keys."
else
    # Gateway token
    GATEWAY_TOKEN=$(openssl rand -hex 32)
    ok "Generated gateway token."

    # Anthropic API key
    echo ""
    echo -e "${CYAN}Enter your Anthropic API key${NC} (starts with sk-ant-):"
    read -r ANTHROPIC_KEY
    if [[ ! "$ANTHROPIC_KEY" =~ ^sk-ant- ]]; then
        warn "Key doesn't start with 'sk-ant-'. Continuing anyway."
    fi

    # Brave Search API key
    echo ""
    echo -e "${CYAN}Enter your Brave Search API key${NC} (starts with BSA-):"
    echo -e "(Free tier: https://brave.com/search/api/ — 2000 queries/month)"
    read -r BRAVE_KEY

    cat > "$ENV_FILE" <<EOF
OPENCLAW_GATEWAY_TOKEN=${GATEWAY_TOKEN}
ANTHROPIC_API_KEY=${ANTHROPIC_KEY}
BRAVE_API_KEY=${BRAVE_KEY}
OPENCLAW_GATEWAY_PORT=18789
OPENCLAW_GATEWAY_BIND=lan
EOF

    chmod 600 "$ENV_FILE"
    ok "Created $ENV_FILE"
fi

# ────────────────────────────────────────────
# 5. Collect phone numbers for the allowlist
# ────────────────────────────────────────────
info "Step 5/9 — Configuring WhatsApp allowlist..."
echo ""
echo -e "${YELLOW}IMPORTANT:${NC} Only numbers in the allowlist can talk to the bot."
echo "         Messages from other numbers are silently ignored."
echo ""
echo -e "${CYAN}Enter your grandfather's phone number${NC} (e.g. +79161234567):"
read -r GRANDPA_PHONE

echo -e "${CYAN}Enter your own phone number${NC} (for testing, e.g. +972545202413):"
read -r ADMIN_PHONE

# Update the config in ~/.openclaw (the one the container actually reads)
CONFIG="$OPENCLAW_DIR/openclaw.json"
if command -v jq &>/dev/null; then
    tmpfile=$(mktemp)
    jq --arg g "$GRANDPA_PHONE" --arg a "$ADMIN_PHONE" \
       '.channels.whatsapp.allowFrom = [$g, $a]' "$CONFIG" > "$tmpfile" \
       && mv "$tmpfile" "$CONFIG"
    chmod 600 "$CONFIG"
    ok "Updated allowlist: $GRANDPA_PHONE, $ADMIN_PHONE"
else
    warn "jq not found. Please manually edit $CONFIG and replace phone numbers."
fi

# Also update the timezone if needed
echo ""
echo -e "${CYAN}Enter the user's timezone${NC} [Asia/Jerusalem]:"
read -r TIMEZONE
TIMEZONE="${TIMEZONE:-Asia/Jerusalem}"

if command -v jq &>/dev/null; then
    tmpfile=$(mktemp)
    jq --arg tz "$TIMEZONE" \
       '.agents.defaults.userTimezone = $tz' "$CONFIG" > "$tmpfile" \
       && mv "$tmpfile" "$CONFIG"
    chmod 600 "$CONFIG"
    ok "Timezone set to $TIMEZONE"
fi

# ────────────────────────────────────────────
# 6. Create workspace dir
# ────────────────────────────────────────────
info "Step 6/9 — Preparing workspace..."
mkdir -p "$PROJECT_DIR/workspace"
ok "Workspace ready."

# ────────────────────────────────────────────
# 7. Start OpenClaw + run doctor
# ────────────────────────────────────────────
info "Step 7/9 — Starting OpenClaw..."
echo ""

cd "$PROJECT_DIR"
docker compose pull
docker compose up -d

info "Waiting for container to start..."
sleep 5

info "Running doctor --fix..."
docker compose exec openclaw node dist/index.js doctor --fix

echo ""
ok "OpenClaw is running."

# ────────────────────────────────────────────
# 8. Link WhatsApp
# ────────────────────────────────────────────
info "Step 8/9 — Linking WhatsApp..."
echo ""
echo "═══════════════════════════════════════════════"
echo "  A QR code will appear below."
echo ""
echo "  On the phone with your bot's SIM:"
echo "    WhatsApp → Settings → Linked Devices → Link a Device"
echo "    Scan the QR code."
echo ""
echo "  The QR expires quickly — have WhatsApp ready BEFORE pressing Enter."
echo "═══════════════════════════════════════════════"
echo ""
read -rp "Press Enter when ready to show QR code..."

docker compose exec openclaw node dist/index.js channels login

echo ""
ok "WhatsApp linked!"

# CRITICAL: Restart the gateway so it picks up the new WhatsApp session.
# Without this restart, the gateway process (PID 1) doesn't load the
# credentials that were just saved by the channels login command.
info "Restarting gateway to load WhatsApp session..."
docker compose restart openclaw
sleep 5
ok "Gateway restarted."

# ────────────────────────────────────────────
# 9. Verify
# ────────────────────────────────────────────
info "Step 9/9 — Final verification..."
echo ""

docker compose exec openclaw node dist/index.js doctor

echo ""
echo "=========================================="
echo -e "${GREEN} Setup complete!${NC}"
echo "=========================================="
echo ""
echo "  Your bot is running and linked to WhatsApp."
echo ""
echo "  Test it: send a message from $GRANDPA_PHONE or $ADMIN_PHONE"
echo "           to the bot's WhatsApp number."
echo ""
echo "  Useful commands:"
echo "    docker compose logs -f openclaw          # Live logs"
echo "    docker compose restart openclaw           # Restart"
echo "    docker compose exec openclaw node dist/index.js doctor  # Health check"
echo ""
echo "  Tail logs now? (Ctrl+C to stop)"
read -rp "  Press Enter to watch logs, or Ctrl+C to exit..."
docker compose logs -f openclaw
