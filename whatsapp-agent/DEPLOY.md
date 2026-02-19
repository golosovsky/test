# WhatsApp AI Assistant for Grandpa — Deployment Guide

A Russian-speaking AI assistant that lives in WhatsApp, powered by
[OpenClaw](https://github.com/openclaw/openclaw) + Claude Haiku 4.5.

## What You Get

- Your grandfather messages a WhatsApp contact, gets AI responses in Russian
- Translations (Russian <-> Hebrew, English, etc.)
- Web search (weather, news, general questions)
- Casual conversation with memory within a session
- Sessions auto-reset after 3 hours of inactivity
- Runs 24/7 on a free cloud server

## Prerequisites

### 1. Get a Prepaid SIM Card

Buy a cheap prepaid SIM that can receive one SMS. This will be the
WhatsApp number your grandfather texts.

### 2. Register WhatsApp on the New SIM

- Insert the SIM into any phone (can be an old spare phone)
- Install WhatsApp, verify the number via SMS
- After setup, WhatsApp stays linked even if you remove the SIM
- Save this number in your grandfather's phone as a contact (e.g. "Помощник")

### 3. Get an Anthropic API Key

1. Go to https://console.anthropic.com
2. Create an account, add a payment method
3. Go to Settings -> API Keys -> Create Key
4. Copy the key (starts with `sk-ant-`)

**Cost:** ~$1-5/month for light usage with Claude Haiku 4.5

### 4. Get a Brave Search API Key

1. Go to https://brave.com/search/api/
2. Sign up for the **Free** plan (2,000 queries/month)
3. Copy your API key (starts with `BSA-`)

### 5. Create a Cloud VM

Oracle Cloud Free Tier (or any Ubuntu 22.04+ VM):

1. Image: **Ubuntu 22.04+**
2. Shape: **VM.Standard.A1.Flex** (2 OCPUs, 12 GB RAM)
3. Add your SSH public key
4. **Upgrade to Pay-As-You-Go** to prevent idle reclamation (still free)

## One-Shot Setup

SSH into your server and run:

```bash
git clone <this-repo> ~/whatsapp-agent
cd ~/whatsapp-agent
bash setup.sh
```

The script handles everything:
1. Installs Docker + Docker Compose
2. Creates `~/.openclaw` with correct permissions (700)
3. Copies config and skills
4. Prompts for API keys and phone numbers
5. Starts OpenClaw and runs `doctor --fix`
6. Shows a QR code — scan with WhatsApp Linked Devices
7. Restarts the gateway to pick up the WhatsApp session
8. Runs final verification

## Architecture (Lessons Learned)

### Volume Mounts

The container bind-mounts `~/.openclaw` from the host as its config/state
directory. We do NOT use a named Docker volume because combining a named
volume with bind-mount overlays into subdirectories causes `EBUSY: resource
busy or locked` errors when OpenClaw tries to atomically rename config files.

### WhatsApp Linking

After scanning the QR code, the gateway process (PID 1) must be restarted
so it loads the new WhatsApp session credentials. Without this restart, the
health-monitor will show `reason: stopped` for the WhatsApp channel and
messages won't be received.

### DM Policy

The `dmPolicy: "allowlist"` setting silently drops messages from numbers
not in the `allowFrom` array. There is no error in the logs. If the bot
isn't responding, check this first.

### Permissions

- `~/.openclaw` must be `chmod 700` (contains WhatsApp session keys)
- `~/.openclaw/openclaw.json` must be `chmod 600`
- `.env` must be `chmod 600` (contains API keys)

## Maintenance

```bash
cd ~/whatsapp-agent

# View logs
docker compose logs -f openclaw

# Restart
docker compose restart openclaw

# Update OpenClaw
docker compose pull && docker compose up -d

# Health check
docker compose exec openclaw node dist/index.js doctor

# Check WhatsApp status
docker compose exec openclaw node dist/index.js channels status
```

## Configuration

### Allowed Users

Only numbers in `allowFrom` can chat. Edit `~/.openclaw/openclaw.json`:

```json
"allowFrom": [
  "+79161234567",
  "+972545202413"
]
```

### Session Timeout

Sessions reset after 3 hours idle (`idleMinutes: 180`).

### Model

Using Claude Haiku 4.5 (fast, cheap). To upgrade to Sonnet (better, ~3x cost):

```json
"model": {
  "primary": "anthropic/claude-sonnet-4-5-20250929"
}
```

### Timezone

Set `agents.defaults.userTimezone` in `~/.openclaw/openclaw.json`.

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| EBUSY errors on config write | Named Docker volume + bind mounts | Use host dir mount (`~/.openclaw`) — not a named volume |
| Bot doesn't respond (no errors in logs) | Phone number not in allowlist | Add number to `allowFrom` in config |
| Bot doesn't respond (health-monitor: stopped) | Gateway didn't load WhatsApp session | `docker compose restart openclaw` |
| QR code expired | Took too long to scan | Re-run `docker compose exec openclaw node dist/index.js channels login` |
| WhatsApp disconnected | Phone offline >14 days | Re-link with `channels login` |
| Oracle instance stopped | Idle reclamation | Upgrade to Pay-As-You-Go |

## File Structure

```
whatsapp-agent/
├── setup.sh               # One-shot setup script (run this)
├── docker-compose.yml      # Container config (host dir mount, no named volume)
├── openclaw.json           # Template config (copied to ~/.openclaw on setup)
├── .env.example            # API key template
├── skills/
│   └── russian-assistant/
│       └── SKILL.md        # Russian assistant persona
├── workspace/              # Agent workspace
└── DEPLOY.md               # This file
```

## Estimated Monthly Cost

| Item | Cost |
|------|------|
| Oracle Cloud VM | $0 (free tier) |
| Claude Haiku 4.5 API | $1-5 (light usage) |
| Brave Search API | $0 (free tier) |
| WhatsApp (Baileys) | $0 |
| **Total** | **$1-5/month** |
