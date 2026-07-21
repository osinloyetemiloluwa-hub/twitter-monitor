"""Twitter/X monitoring cog for Discord."""
import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime
import asyncio
import aiohttp
import io

from database import Database
from x_fetcher import XFetcher
from config import POLL_INTERVAL, EMBED_COLOR, EMBED_COLOR_NEW


class TwitterCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = Database()
        self.fetcher = XFetcher()
        self.poll_loop.start()

    async def cog_load(self):
        await self.db.connect()
        await self.db.setup()

    async def cog_unload(self):
        self.poll_loop.cancel()
        await self.fetcher.close()
        await self.db.close()

    # ============================================================
    # SLASH COMMAND GROUP: /twitter
    # ============================================================
    twitter = app_commands.Group(name="twitter", description="Manage X/Twitter account alerts")

    @twitter.command(name="add", description="Add an X account to monitor")
    @app_commands.describe(
        username="The X username to track (without @)",
        channel="The channel to post alerts in"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def twitter_add(
        self,
        interaction: discord.Interaction,
        username: str,
        channel: discord.TextChannel
    ):
        """Add an X account to monitor."""
        await interaction.response.defer(ephemeral=True)

        clean_username = username.lower().strip().replace("@", "")

        # Validate username format
        if not clean_username or len(clean_username) > 15:
            await interaction.followup.send(
                "❌ Invalid username. Please provide a valid X username.",
                ephemeral=True
            )
            return

        # Test fetch to verify account exists
        posts = await self.fetcher.fetch_posts(clean_username, limit=1)

        await self.db.add_account(
            guild_id=interaction.guild_id,
            channel_id=channel.id,
            username=clean_username
        )

        embed = discord.Embed(
            title="✅ Account Added",
            description=f"Now tracking **@{clean_username}** in {channel.mention}",
            color=EMBED_COLOR_NEW,
            timestamp=datetime.utcnow()
        )
        embed.add_field(
            name="Status",
            value="Active" if posts else "Added (could not verify account - may be private or API limit)",
            inline=False
        )
        embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @twitter.command(name="remove", description="Stop monitoring an X account")
    @app_commands.describe(username="The X username to stop tracking")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def twitter_remove(
        self,
        interaction: discord.Interaction,
        username: str
    ):
        """Remove a tracked X account."""
        await interaction.response.defer(ephemeral=True)

        clean_username = username.lower().strip().replace("@", "")

        result = await self.db.remove_account(interaction.guild_id, clean_username)

        if result:
            embed = discord.Embed(
                title="🗑️ Account Removed",
                description=f"Stopped tracking **@{clean_username}**",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )
        else:
            embed = discord.Embed(
                title="⚠️ Not Found",
                description=f"**@{clean_username}** was not being tracked in this server.",
                color=discord.Color.orange(),
                timestamp=datetime.utcnow()
            )

        embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @twitter.command(name="list", description="List all tracked X accounts")
    async def twitter_list(self, interaction: discord.Interaction):
        """Show all tracked accounts for this server."""
        await interaction.response.defer(ephemeral=True)

        accounts = await self.db.get_accounts(guild_id=interaction.guild_id)

        if not accounts:
            embed = discord.Embed(
                title="📋 Tracked Accounts",
                description="No accounts are being tracked in this server.",
                color=discord.Color.light_grey(),
                timestamp=datetime.utcnow()
            )
        else:
            embed = discord.Embed(
                title=f"📋 Tracked Accounts ({len(accounts)})",
                color=EMBED_COLOR,
                timestamp=datetime.utcnow()
            )

            for acc in accounts:
                channel = self.bot.get_channel(acc["channel_id"])
                ch_mention = channel.mention if channel else f"`{acc['channel_id']}`"
                embed.add_field(
                    name=f"@{acc['username']}",
                    value=f"Alerts in: {ch_mention}",
                    inline=True
                )

        embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @twitter.command(name="alert", description="Test alert for a tracked account")
    @app_commands.describe(username="The X username to test")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def twitter_alert(
        self,
        interaction: discord.Interaction,
        username: str
    ):
        """Manually trigger a test alert for an account."""
        await interaction.response.defer(ephemeral=True)

        clean_username = username.lower().strip().replace("@", "")
        posts = await self.fetcher.fetch_posts(clean_username, limit=1)

        if not posts:
            await interaction.followup.send(
                f"❌ Could not fetch posts for **@{clean_username}**. The account may be private or the service is unavailable.",
                ephemeral=True
            )
            return

        # Send test alert to the channel configured for this account
        accounts = await self.db.get_accounts(guild_id=interaction.guild_id)
        account = next((a for a in accounts if a["username"] == clean_username), None)

        if account:
            channel = self.bot.get_channel(account["channel_id"])
            if channel:
                await self._send_post_embed(channel, posts[0], is_test=True)
                await interaction.followup.send(
                    f"✅ Test alert sent to {channel.mention} for **@{clean_username}**!",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ Could not find the configured channel. It may have been deleted.",
                    ephemeral=True
                )
        else:
            # Send to current channel as demo
            await self._send_post_embed(interaction.channel, posts[0], is_test=True)
            await interaction.followup.send(
                f"✅ Test alert sent here (account not configured for this server).",
                ephemeral=True
            )

    # ============================================================
    # BACKGROUND POLLING LOOP
    # ============================================================
    @tasks.loop(seconds=POLL_INTERVAL)
    async def poll_loop(self):
        """Poll all tracked accounts for new posts."""
        accounts = await self.db.get_accounts()

        # Group by username to avoid duplicate fetches
        usernames = list(set(a["username"] for a in accounts))

        for username in usernames:
            try:
                posts = await self.fetcher.fetch_posts(username, limit=5)
                if not posts:
                    continue

                # Get accounts tracking this username
                accs_for_user = [a for a in accounts if a["username"] == username]

                for post in reversed(posts):  # Oldest first
                    post_id = post["id"]
                    if not post_id:
                        continue

                    # Check if already seen globally
                    if await self.db.is_post_seen(username, post_id):
                        continue

                    # Mark as seen
                    await self.db.mark_post_seen(username, post_id)

                    # Send to all configured channels for this account
                    for acc in accs_for_user:
                        channel = self.bot.get_channel(acc["channel_id"])
                        if channel and channel.permissions_for(channel.guild.me).send_messages:
                            try:
                                await self._send_post_embed(channel, post)
                                # Update last post ID
                                await self.db.update_last_post(
                                    acc["guild_id"], username, post_id
                                )
                            except Exception:
                                pass

                    # Small delay between posts
                    await asyncio.sleep(1)

            except Exception:
                continue

            # Delay between accounts to be nice to APIs
            await asyncio.sleep(2)

    @poll_loop.before_loop
    async def before_poll_loop(self):
        await self.bot.wait_until_ready()

    # ============================================================
    # EMBED BUILDER
    # ============================================================
    async def _send_post_embed(self, channel: discord.TextChannel, post: dict, is_test: bool = False):
        """Build and send a rich embed matching the reference image style."""
        embed = discord.Embed(
            title=f"{'🧪 TEST: ' if is_test else ''}New post from @{post['author_name']}",
            url=post["url"],
            color=EMBED_COLOR_NEW if not is_test else discord.Color.gold(),
            timestamp=datetime.utcnow()
        )

        # Post content
        text = post["text"]
        if len(text) > 4000:
            text = text[:3997] + "..."
        embed.description = text

        # Author info
        embed.set_author(
            name=f"@{post['author_name']}",
            url=f"https://x.com/{post['author_name']}",
            icon_url=post.get("author_avatar", "")
        )

        # Stats footer like the reference image
        stats = []
        if post.get("replies", 0) > 0:
            stats.append(f"💬 {self._format_number(post['replies'])}")
        if post.get("retweets", 0) > 0:
            stats.append(f"🔄 {self._format_number(post['retweets'])}")
        if post.get("likes", 0) > 0:
            stats.append(f"❤️ {self._format_number(post['likes'])}")

        if stats:
            embed.add_field(name="Engagement", value=" ｜ ".join(stats), inline=False)

        # Post timestamp
        if post.get("created_at"):
            embed.add_field(
                name="Posted",
                value=post["created_at"],
                inline=True
            )

        embed.set_footer(
            text=f"🔗 Open in X  •  Posted via X Bot",
            icon_url="https://abs.twimg.com/icons/apple-touch-icon-192x192.png"
        )

        # Attach media if available
        files = []
        if post.get("media_urls"):
            for i, media_url in enumerate(post["media_urls"][:4]):  # Max 4 images
                try:
                    session = await self.fetcher._get_session()
                    async with session.get(media_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            ext = media_url.split("?")[0].split(".")[-1]
                            if ext not in ["jpg", "jpeg", "png", "gif", "webp"]:
                                ext = "png"
                            file = discord.File(
                                fp=io.BytesIO(data),
                                filename=f"media_{i}.{ext}"
                            )
                            files.append(file)
                            if i == 0:
                                embed.set_image(url=f"attachment://media_{i}.{ext}")
                except Exception:
                    embed.set_image(url=media_url)  # Fallback to URL
                    break

        await channel.send(embed=embed, files=files if files else None)

    def _format_number(self, n: int) -> str:
        """Format large numbers like X does (1.2K, 3.8M)."""
        if n >= 1_000_000:
            return f"{n/1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n/1_000:.1f}K"
        return str(n)

    # Error handling for permissions
    @twitter_add.error
    @twitter_remove.error
    @twitter_alert.error
    async def twitter_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ You need **Manage Server** permission to use this command.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ An error occurred: {str(error)}",
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(TwitterCog(bot))
