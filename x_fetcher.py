"""Fetch posts from X/Twitter accounts using available APIs."""
import aiohttp
import json
import re  # <-- moved import to top
from datetime import datetime
from typing import List, Dict, Optional


class XFetcher:
    """Fetches latest posts from X accounts using RSS bridges and fallback methods."""

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        # Multiple RSS bridge endpoints for redundancy
        self.rss_endpoints = [
            "https://nitter.net",
            "https://nitter.it",
            "https://nitter.cz",
        ]

    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
        return self.session

    async def fetch_posts(self, username: str, limit: int = 5) -> List[Dict]:
        """Fetch latest posts from an X account.

        Returns list of post dicts with: id, text, created_at, media_urls,
        likes, retweets, replies, url, author_name, author_avatar
        """
        username = username.lower().strip().replace("@", "")
        posts = []

        # Try RSS bridges first
        for endpoint in self.rss_endpoints:
            try:
                posts = await self._fetch_from_rss(endpoint, username, limit)
                if posts:
                    break
            except Exception:
                continue

        # Fallback: use a mock/example for demonstration if no RSS works
        # In production, you'd want to use X API v2 with proper credentials
        if not posts:
            posts = await self._fetch_from_api(username, limit)

        return posts

    async def _fetch_from_rss(self, endpoint: str, username: str, limit: int) -> List[Dict]:
        """Fetch via Nitter RSS feed."""
        session = await self._get_session()
        rss_url = f"{endpoint}/{username}/rss"

        async with session.get(rss_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return []

            text = await resp.text()
            return self._parse_rss(text, username, limit)

    def _parse_rss(self, rss_text: str, username: str, limit: int) -> List[Dict]:
        """Parse RSS XML into post dicts."""
        import xml.etree.ElementTree as ET
        posts = []

        try:
            root = ET.fromstring(rss_text)
            channel = root.find("channel")
            if channel is None:
                return posts

            items = channel.findall("item")[:limit]

            for item in items:
                title = item.findtext("title", "")
                link = item.findtext("link", "")
                pub_date = item.findtext("pubDate", "")
                description = item.findtext("description", "")

                # Extract post ID from link
                post_id = ""
                if "/status/" in link:
                    post_id = link.split("/status/")[-1].split("?")[0].split("#")[0]

                # Parse media from description (basic img extraction)
                media_urls = []
                if "<img" in description:
                    # Use double quotes for the outer regex string to avoid quote conflicts
                    # This matches src="..." or src='...' and captures the URL
                    imgs = re.findall(r'src=["\']([^"\']+)["\']', description)
                    media_urls = [u for u in imgs if u.startswith("http")]

                # Clean description text
                clean_text = re.sub(r'<[^>]+>', '', description).strip()

                posts.append({
                    "id": post_id or link,
                    "text": clean_text or title,
                    "created_at": pub_date,
                    "media_urls": media_urls,
                    "likes": 0,
                    "retweets": 0,
                    "replies": 0,
                    "url": link.replace("nitter.net", "x.com").replace("nitter.it", "x.com").replace("nitter.cz", "x.com"),
                    "author_name": username,
                    "author_avatar": f"https://unavatar.io/x/{username}",
                })
        except Exception:
            pass

        return posts

    async def _fetch_from_api(self, username: str, limit: int) -> List[Dict]:
        """Fallback using X API or other services.

        NOTE: For production, implement X API v2 here with Bearer token.
        This is a placeholder that returns empty list.
        """
        # TODO: Implement X API v2 integration
        # Requires: X_BEARER_TOKEN env var
        # Endpoint: https://api.twitter.com/2/users/by/username/{username}
        # Then: https://api.twitter.com/2/users/{id}/tweets
        return []

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
