"""X/Twitter Discord Bot - Main Entry Point."""
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os

from config import DISCORD_BOT_TOKEN
from rate_limiter import GlobalRateLimiter


class XBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="X/Twitter for new posts"
            )
        )

        # More conservative: 30 req/s (leaves safety margin)
        self.rate_limiter = GlobalRateLimiter(max_requests_per_second=30.0)

        # Track consecutive 429s for exponential backoff
        self.consecutive_429s = 0
        self.last_429_time = 0

        # Flag to ensure sync happens only once (if we ever allow auto-sync)
        self._synced_commands = False

    async def setup_hook(self):
        """Load cogs before bot starts."""
        await self.load_extension("cogs.twitter")
        print("✅ Twitter cog loaded")

        # ----------------------------------------------------------------
        # IMPORTANT: Do NOT sync commands automatically on every startup.
        # This is the #1 cause of rate limits. We'll use a manual command.
        # ----------------------------------------------------------------
        # If you absolutely must auto-sync, uncomment the block below,
        # but then add a long random delay (e.g., 30–60s) and only do it once.
        # await asyncio.sleep(30)
        # if not self._synced_commands:
        #     synced = await self.tree.sync()
        #     self._synced_commands = True
        #     print(f"✅ Synced {len(synced)} slash command(s)")
        # ----------------------------------------------------------------

        print("ℹ️  Slash commands will be synced manually with /sync_commands")
        print("   (Run this command once after deployment)")

        # Optional: add a small delay before starting any background tasks
        await asyncio.sleep(2)

    async def on_ready(self):
        """Called when bot is fully ready."""
        print(f"🚀 Logged in as {self.user} (ID: {self.user.id})")
        print(f"📊 Connected to {len(self.guilds)} guild(s)")
        print(f"⏱️  Rate limit: 30 req/s (shared token protection)")
        print("─" * 40)

        # Stagger any startup operations
        await asyncio.sleep(5)

    async def on_guild_join(self, guild: discord.Guild):
        """Welcome message when bot joins a server — with rate limit protection."""
        print(f"➕ Joined guild: {guild.name} (ID: {guild.id})")

        # Wait before sending welcome to avoid burst
        await asyncio.sleep(3)

        target = guild.system_channel
        if not target or not target.permissions_for(guild.me).send_messages:
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).send_messages:
                    target = channel
                    break

        if target:
            embed = discord.Embed(
                title="👋 X Bot is here!",
                description="I'll monitor X/Twitter accounts and post updates to your channels.",
                color=0x1DA1F2
            )
            embed.add_field(
                name="Setup",
                value="Use `/twitter add <username> <channel>` to start tracking accounts.",
                inline=False
            )
            embed.add_field(
                name="Commands",
                value=(
                    "`/twitter add` - Track an X account\n"
                    "`/twitter remove` - Stop tracking\n"
                    "`/twitter list` - Show tracked accounts\n"
                    "`/twitter alert` - Test an alert"
                ),
                inline=False
            )

            # Use rate-limited send
            await self.rate_limiter.safe_send(target, embed=embed)

    async def on_command_error(self, ctx, error):
        """Handle command errors with backoff on 429s."""
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"⏳ Command on cooldown. Try again in {error.retry_after:.1f}s.", delete_after=10)
        elif isinstance(error, discord.HTTPException) and error.status == 429:
            self.consecutive_429s += 1
            self.last_429_time = asyncio.get_event_loop().time()
            backoff = min(2 ** self.consecutive_429s, 60)  # Exponential up to 60s
            print(f"⚠️ 429 hit! Backing off for {backoff}s (consecutive: {self.consecutive_429s})")
            await asyncio.sleep(backoff)
        else:
            print(f"Command error: {error}")

    async def on_interaction(self, interaction: discord.Interaction):
        """Wrap interactions with rate limit tracking."""
        await self.rate_limiter.acquire(weight=1)
        await super().on_interaction(interaction)


# ------------------------------------------------------------------------
# MANUAL SYNC COMMAND – run this once after deployment
# ------------------------------------------------------------------------
@bot.tree.command(name="sync_commands", description="Sync all slash commands (admin only)")
@app_commands.default_permissions(administrator=True)
async def sync_commands(interaction: discord.Interaction):
    """Syncs slash commands manually to avoid auto-sync rate limits."""
    # Rate-limit this command: can only be used once per minute globally
    # (simple guard using a class variable)
    if not hasattr(sync_commands, "_last_use"):
        sync_commands._last_use = 0

    now = asyncio.get_event_loop().time()
    if now - sync_commands._last_use < 60:
        await interaction.response.send_message(
            "⏳ Command sync can only be used once per minute. Please wait.",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    try:
        # Actually sync
        synced = await interaction.client.tree.sync()
        sync_commands._last_use = now
        await interaction.followup.send(
            f"✅ Successfully synced {len(synced)} slash command(s).",
            ephemeral=True
        )
        print(f"✅ Manual sync completed: {len(synced)} commands")
    except discord.HTTPException as e:
        if e.status == 429:
            await interaction.followup.send(
                "⚠️ Rate limited while syncing. Wait a few minutes and try again.",
                ephemeral=True
            )
        else:
            await interaction.followup.send(f"❌ Sync failed: {e}", ephemeral=True)


# ------------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------------
def main():
    if not DISCORD_BOT_TOKEN:
        print("❌ ERROR: DISCORD_BOT_TOKEN not set!")
        print("   Create a .env file or set the environment variable.")
        return

    bot = XBot()

    try:
        bot.run(DISCORD_BOT_TOKEN)
    except discord.LoginFailure:
        print("❌ ERROR: Invalid Discord bot token!")
    except Exception as e:
        print(f"❌ ERROR: {e}")


if __name__ == "__main__":
    main()
