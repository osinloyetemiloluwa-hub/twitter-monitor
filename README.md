# 🐦 X/Twitter Discord Bot

A Discord bot that monitors X (Twitter) accounts and automatically posts new tweets to configured channels with rich embeds.

## Features

- **Slash Commands**: `/twitter add`, `/twitter remove`, `/twitter list`, `/twitter alert`
- **Rich Embeds**: Full post content, media, engagement stats, author info
- **Background Polling**: Checks for new posts every 60 seconds
- **Multi-Server**: Track different accounts per server/channel
- **PostgreSQL/SQLite**: Persistent storage

## Commands

| Command | Description | Permission |
|---------|-------------|------------|
| `/twitter add <username> <channel>` | Start tracking an X account | Manage Server |
| `/twitter remove <username>` | Stop tracking an account | Manage Server |
| `/twitter list` | Show all tracked accounts | Anyone |
| `/twitter alert <username>` | Send a test alert | Manage Server |

## Setup

### 1. Discord Bot Token
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create New Application → Bot → Copy Token
3. Enable **Message Content Intent** and **Server Members Intent**
4. OAuth2 → URL Generator → Select `bot` and `applications.commands`
5. Copy the URL and invite the bot to your server

### 2. Local Development
```bash
# Clone and setup
git clone <repo>
cd discord-x-bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env and add your DISCORD_BOT_TOKEN

# Run
python main.py
```

### 3. Deploy on Render (Free)

#### Method A: Blueprint (Recommended)
1. Push code to GitHub
2. In Render Dashboard → **New** → **Blueprint**
3. Connect your repo → Render reads `render.yaml`
4. Set `DISCORD_BOT_TOKEN` in Environment Variables
5. Deploy!

#### Method B: Manual
1. **New Web Service** → Connect repo
2. Set:
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main.py`
   - **Instance Type**: Worker (not web service!)
3. Add **PostgreSQL** database (free tier)
4. Set `DISCORD_BOT_TOKEN` env var
5. Deploy

> ⚠️ **Important**: Use a **Background Worker** service type, not Web Service. Discord bots don't expose HTTP ports.

## Architecture

```
main.py          → Bot entry point, event handlers
cogs/twitter.py  → Slash commands + background polling loop
database.py      → PostgreSQL/SQLite persistence
x_fetcher.py     → Fetches posts via RSS bridges / X API
config.py        → Environment configuration
```

## X API Integration (Production)

The bot uses RSS bridges (Nitter) by default. For production reliability:

1. Apply for [X API v2](https://developer.twitter.com/en/portal/dashboard)
2. Add `X_BEARER_TOKEN` to your `.env`
3. Update `x_fetcher.py` to use the official API endpoints

## File Structure

```
discord-x-bot/
├── main.py
├── config.py
├── database.py
├── x_fetcher.py
├── requirements.txt
├── render.yaml
├── Dockerfile
├── .env.example
├── README.md
└── cogs/
    └── twitter.py
```

## License

MIT
