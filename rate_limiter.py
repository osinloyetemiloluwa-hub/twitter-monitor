"""Global rate limit protection for Discord API requests."""
import asyncio
import time
from collections import deque
from typing import Optional
import discord
from discord.ext import commands


class GlobalRateLimiter:
    """
    Tracks and enforces delays to avoid Discord global rate limits.
    Shared across all API calls in the bot.
    """

    def __init__(self, max_requests_per_second: float = 45.0):
        # Discord global limit is ~50 req/s per token across ALL apps
        # We stay well under that since you share the token
        self.max_rps = max_requests_per_second
        self.request_times: deque = deque()
        self.lock = asyncio.Lock()
        self.last_warning = 0

    async def acquire(self, weight: int = 1):
        """Wait until it's safe to make a request."""
        async with self.lock:
            now = time.monotonic()

            # Clean old entries outside the 1-second window
            while self.request_times and self.request_times[0] < now - 1.0:
                self.request_times.popleft()

            # If we're at the limit, wait until the oldest entry expires
            while len(self.request_times) >= self.max_rps:
                sleep_time = self.request_times[0] - (now - 1.0) + 0.05
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                now = time.monotonic()
                while self.request_times and self.request_times[0] < now - 1.0:
                    self.request_times.popleft()

            # Record this request (weight = how many "slots" it uses)
            for _ in range(weight):
                self.request_times.append(now)

    async def safe_send(self, channel: discord.TextChannel, *args, **kwargs) -> Optional[discord.Message]:
        """Send a message with rate limit protection."""
        await self.acquire(weight=1)
        try:
            return await channel.send(*args, **kwargs)
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = e.retry_after if hasattr(e, 'retry_after') else 5
                await asyncio.sleep(min(retry_after, 60))
                return await self.safe_send(channel, *args, **kwargs)
            raise


class RateLimitedBot(commands.Bot):
    """Bot subclass with built-in global rate limiting."""

    def __init__(self, *args, rate_limit_rps: float = 45.0, **kwargs):
        super().__init__(*args, **kwargs)
        self.rate_limiter = GlobalRateLimiter(rate_limit_rps)

    async def on_error(self, event_method, *args, **kwargs):
        """Handle errors globally with backoff."""
        import traceback
        print(f"Error in {event_method}:")
        traceback.print_exc()
        # Add delay after any error to cool down
        await asyncio.sleep(2)
