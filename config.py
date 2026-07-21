"""Bot configuration and constants."""
import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///xbot.db")

# Polling interval in seconds — INCREASED to 120s to reduce API load
# since you share the token with other apps. Set via env if needed.
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "120"))

# X/Twitter RSS bridge
RSS_BRIDGE_URL = "https://nitter.net"

# Embed colors
EMBED_COLOR = 0x1DA1F2
EMBED_COLOR_NEW = 0x00ff88
