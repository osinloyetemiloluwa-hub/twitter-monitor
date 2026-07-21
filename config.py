"""Bot configuration and constants."""
import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///xbot.db")

# Polling interval in seconds (check for new posts every 60 seconds)
POLL_INTERVAL = 60

# X/Twitter RSS bridge (Nitter instances often go down, using RSSHub or similar)
# Using a reliable RSS-to-JSON service for X accounts
RSS_BRIDGE_URL = "https://nitter.net"  # Fallback, can be configured

# Embed colors
EMBED_COLOR = 0x1DA1F2  # Twitter blue
EMBED_COLOR_NEW = 0x00ff88  # Green for new posts
