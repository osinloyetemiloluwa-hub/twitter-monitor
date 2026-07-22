"""X/Twitter Discord Bot - Main Entry Point."""
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os
from aiohttp import web

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

        self.rate_limiter = GlobalRateLimiter(max_requests_per_second=30.0)
        self.consecutive_429s = 0
        self.last_429_time = 0
        self._http_server = None

    async def setup_hook(self):
        """Load cogs and register commands before bot starts."""
        await self.load_extension("cogs.twitter")
        print("✅ Twitter cog loaded")

        # Register the manual sync command (slash)
        self.tree.add_command(self.sync_commands)
        print("ℹ️  /sync_commands registered (admin only inside)")
        print("ℹ️  Also use !sync (prefix command) to sync slash commands")
        await asyncio.sleep(2)

    # ---------- PREFIX COMMAND: !sync ----------
    @commands.command(name="sync")
    async def sync_prefix(self, ctx: commands.Context):
        """Sync slash commands via prefix command."""
        # Only allow server admins (optional)
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ You need administrator permissions to sync commands.")
            return

        await ctx.send("⏳ Syncing slash commands...")
        try:
            synced = await self.tree.sync()
            await ctx.send(f"✅ Synced {len(synced)} slash command(s).")
            print(f"✅ Manual sync (prefix) completed: {len(synced)} commands")
        except discord.HTTPException as e:
            if e.status == 429:
                await ctx.send("⚠️ Rate limited. Wait a minute and try again.")
            else:
                await ctx.send(f"❌ Sync failed: {e}")

    # ---------- SLASH COMMAND: /sync_commands ----------
    @app_commands.command(name="sync_commands", description="Sync all slash commands")
    # No default_permissions here – we'll check inside
    async def sync_commands(self, interaction: discord.Interaction):
        """Manually sync slash commands – run once after deployment."""
        # Check admin inside (so command is visible but restricted)
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ You need administrator permissions to use this command.",
                ephemeral=True
            )
            return

        if not hasattr(self, "_last_sync_time"):
            self._last_sync_time = 0

        now = asyncio.get_event_loop().time()
        if now - self._last_sync_time < 60:
            await interaction.response.send_message(
                "⏳ Command sync can only be used once per minute. Please wait.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            synced = await self.tree.sync()
            self._last_sync_time = now
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

    async def on_ready(self):
        """Called when bot is fully ready."""
        print(f"🚀 Logged in as {self.user} (ID: {self.user.id})")
        print(f"📊 Connected to {len(self.guilds)} guild(s)")
        print(f"⏱️  Rate limit: 30 req/s (shared token protection)")
        print("─" * 40)

        await self.start_health_server()
        await asyncio.sleep(5)

    async def start_health_server(self):
        if self._http_server is not None:
            return

        port = int(os.environ.get("PORT", 8080))
        if not (3000 <= port <= 10000):
            port = 8080

        app = web.Application()
        app.router.add_get("/", self._health_handler)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()

        self._http_server = runner
        print(f"✅ Health server started on port {port}")

    async def _health_handler(self, request):
        return web.Response(text="OK", status=200)

    async def on_guild_join(self, guild: discord.Guild):
        print(f"➕ Joined guild: {guild.name} (ID: {guild.id})")
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
            await self.rate_limiter.safe_send(target, embed=embed)

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"⏳ Command on cooldown. Try again in {error.retry_after:.1f}s.", delete_after=10)
        elif isinstance(error, discord.HTTPException) and error.status == 429:
            self.consecutive_429s += 1
            self.last_429_time = asyncio.get_event_loop().time()
            backoff = min(2 ** self.consecutive_429s, 60)
            print(f"⚠️ 429 hit! Backing off for {backoff}s")
            await asyncio.sleep(backoff)
        else:
            print(f"Command error: {error}")

    async def on_interaction(self, interaction: discord.Interaction):
        await self.rate_limiter.acquire(weight=1)
        await super().on_interaction(interaction)


def main():
    if not DISCORD_BOT_TOKEN:
        print("❌ ERROR: DISCORD_BOT_TOKEN not set!")
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
