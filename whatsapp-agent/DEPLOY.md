# WhatsApp AI Assistant for Grandpa — Deployment Guide

A Russian-speaking AI assistant that lives in WhatsApp, powered by
[OpenClaw](https://github.com/openclaw/openclaw) + Claude Haiku 4.5.

## What You Get

- Your grandfather messages a WhatsApp contact, gets AI responses in Russian
- Translations (Russian ↔ Hebrew, English, etc.)
- Web search (weather, news, general questions)
- Casual conversation with memory within a session
- Sessions auto-reset after 3 hours of inactivity
- Runs 24/7 on a free cloud server

## Prerequisites (Your Tasks)

### 1. Get a Prepaid SIM Card

Buy a cheap prepaid SIM that can receive one SMS. This will be the
WhatsApp number your grandfather texts. Using a separate number protects
your grandfather's personal WhatsApp from any risk of account flagging.

**Cost:** ~$5 one-time

### 2. Register WhatsApp on the New SIM

- Insert the SIM into any phone (can be an old spare phone)
- Install WhatsApp, verify the number via SMS
- After setup, WhatsApp stays linked even if you remove the SIM
- Save this number in your grandfather's phone as a contact (e.g. "Помощник")

### 3. Get an Anthropic API Key

1. Go to https://console.anthropic.com
2. Create an account
3. Add a payment method (credit card)
4. Go to Settings → API Keys → Create Key
5. Copy the key (starts with `sk-ant-`)

**Cost:** ~$1-5/month for light usage with Claude Haiku 4.5

### 4. Get a Brave Search API Key

1. Go to https://brave.com/search/api/
2. Sign up for the **Free** plan (2,000 queries/month)
3. Copy your API key (starts with `BSA-`)

**Cost:** $0 (free tier is plenty for personal use)

### 5. Create an Oracle Cloud Account

1. Go to https://cloud.oracle.com and sign up
2. Choose a **Home Region** close to your grandfather's location
   - If in Israel: choose a nearby European region
   - If in Russia: choose a nearby region
3. Provide a credit card for verification (you will NOT be charged)
4. After account creation, **upgrade to Pay-As-You-Go** (still free):
   - This prevents Oracle from reclaiming your free instance for being idle
   - You only pay if you manually create resources beyond the free limits

## Server Setup

### Step 1: Create the VM

1. In Oracle Cloud Console, go to **Compute → Instances → Create Instance**
2. Image: **Ubuntu 22.04** (or later)
3. Shape: **VM.Standard.A1.Flex** (Ampere ARM)
   - OCPUs: **2** (4 max free, but 2 is plenty)
   - Memory: **12 GB** (24 max free, but 12 is plenty)
4. Add your SSH public key
5. Click **Create**

> If you get a capacity error, try again in a few hours or pick a
> less popular region. ARM instances are in high demand.

### Step 2: SSH into the Server

```bash
ssh ubuntu@<your-server-ip>
```

### Step 3: Run the Setup Script

Upload and run the setup script:

```bash
# Option A: Copy the script from your machine
scp setup-oracle.sh ubuntu@<your-server-ip>:~/

# On the server:
bash ~/setup-oracle.sh
```

### Step 4: Upload Configuration Files

From your local machine:

```bash
scp -r openclaw.json docker-compose.yml skills/ .env.example \
    ubuntu@<your-server-ip>:~/whatsapp-agent/
```

### Step 5: Configure Environment Variables

On the server:

```bash
cd ~/whatsapp-agent
cp .env.example .env
nano .env
```

Fill in:
- `OPENCLAW_GATEWAY_TOKEN` — run `openssl rand -hex 32` to generate
- `ANTHROPIC_API_KEY` — your `sk-ant-...` key
- `BRAVE_API_KEY` — your `BSA-...` key

### Step 6: Edit Phone Numbers

Edit `openclaw.json` and replace the placeholder phone numbers:

```bash
nano openclaw.json
```

Find the `allowFrom` section and replace:
- `+GRANDFATHER_PHONE_NUMBER` → your grandfather's actual number (e.g. `+79161234567`)
- `+YOUR_PHONE_NUMBER` → your own number (for testing/admin)

### Step 7: Start OpenClaw

```bash
cd ~/whatsapp-agent
docker compose up -d
```

### Step 8: Link WhatsApp

Run the onboard wizard:

```bash
docker compose exec openclaw node dist/index.js onboard
```

- Select **WhatsApp** as the channel
- A **QR code** will appear in the terminal
- On the phone with the new SIM:
  - Open WhatsApp → Settings → **Linked Devices** → **Link a Device**
  - Scan the QR code
- The link is established. OpenClaw now receives and sends WhatsApp messages.

> The QR code expires quickly. If it times out, run the onboard
> command again.

### Step 9: Test It

From your grandfather's WhatsApp (or your own phone if your number is
in the allowlist), send a message to the bot's WhatsApp number:

```
Привет! Переведи "здравствуйте" на иврит
```

You should get a response in Russian within a few seconds.

## Maintenance

### View Logs

```bash
cd ~/whatsapp-agent
docker compose logs -f openclaw
```

### Restart

```bash
docker compose restart openclaw
```

### Update OpenClaw

```bash
docker compose pull
docker compose up -d
```

### Check Session Logs

Sessions are stored in the Docker volume. To inspect:

```bash
docker compose exec openclaw bash -c \
  'ls -la ~/.openclaw/agents/*/sessions/*.jsonl'
```

### Monitor Costs

Check your Anthropic API usage at https://console.anthropic.com/settings/usage

## Configuration Reference

### Session Behavior

Current config: sessions reset after **3 hours of inactivity** (`idleMinutes: 180`).

To change this, edit `openclaw.json`:

```json
"session": {
  "reset": {
    "mode": "idle",
    "idleMinutes": 180
  }
}
```

- Set to `360` for 6-hour sessions
- Set `"mode": "daily"` with `"atHour": 4` to reset every night at 4 AM instead

### Allowed Users

Only numbers listed in `allowFrom` can chat with the bot. To add more:

```json
"allowFrom": [
  "+79161234567",
  "+79169876543"
]
```

### Model

Currently using Claude Haiku 4.5. To upgrade to Sonnet (better but ~3x more expensive):

```json
"model": {
  "primary": "anthropic/claude-sonnet-4-5-20250929"
}
```

### Timezone

Set in `agents.defaults.userTimezone`. Currently `Europe/Moscow`. Change to
match your grandfather's location (e.g. `Asia/Jerusalem`).

## Troubleshooting

| Problem | Solution |
|---------|----------|
| QR code expired | Run `docker compose exec openclaw node dist/index.js onboard` again |
| No response to messages | Check `docker compose logs -f openclaw` for errors |
| "API key invalid" | Verify `ANTHROPIC_API_KEY` in `.env`, restart: `docker compose restart` |
| WhatsApp disconnected | Phone must stay online. If offline >14 days, re-link. |
| Oracle instance stopped | Check Oracle console; upgrade to PAYG to prevent idle reclamation |
| High API costs | Check usage at console.anthropic.com; reduce `idleMinutes` to shorten sessions |

## File Structure

```
whatsapp-agent/
├── openclaw.json          # Main OpenClaw configuration
├── docker-compose.yml     # Docker container setup
├── .env.example           # Environment variable template
├── setup-oracle.sh        # Oracle Cloud server setup script
├── skills/
│   └── russian-assistant/
│       └── SKILL.md       # Russian assistant persona & instructions
├── workspace/             # Agent workspace (file operations)
└── DEPLOY.md              # This file
```

## Estimated Monthly Cost

| Item | Cost |
|------|------|
| Oracle Cloud VM | $0 (free tier) |
| Claude Haiku 4.5 API | $1-5 (light usage) |
| Brave Search API | $0 (free tier) |
| WhatsApp (Baileys) | $0 |
| **Total** | **$1-5/month** |
