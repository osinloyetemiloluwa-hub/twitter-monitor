"""Database operations for the X Bot."""
import aiosqlite
import asyncpg
import os
from config import DATABASE_URL


class Database:
    def __init__(self):
        self.db_type = "postgres" if DATABASE_URL.startswith("postgresql") else "sqlite"
        self.conn = None
        self.pool = None

    async def connect(self):
        """Connect to the database."""
        if self.db_type == "postgres":
            self.pool = await asyncpg.create_pool(DATABASE_URL)
        else:
            self.conn = await aiosqlite.connect(DATABASE_URL.replace("sqlite:///", ""))
            await self.conn.execute("PRAGMA foreign_keys = ON")
            await self.conn.commit()

    async def setup(self):
        """Create tables if they don't exist."""
        if self.db_type == "postgres":
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS tracked_accounts (
                        id SERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        channel_id BIGINT NOT NULL,
                        username TEXT NOT NULL,
                        last_post_id TEXT DEFAULT '',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(guild_id, username)
                    )
                """)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS post_history (
                        id SERIAL PRIMARY KEY,
                        username TEXT NOT NULL,
                        post_id TEXT NOT NULL,
                        posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(username, post_id)
                    )
                """)
        else:
            await self.conn.execute("""
                CREATE TABLE IF NOT EXISTS tracked_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    last_post_id TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(guild_id, username)
                )
            """)
            await self.conn.execute("""
                CREATE TABLE IF NOT EXISTS post_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    post_id TEXT NOT NULL,
                    posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(username, post_id)
                )
            """)
            await self.conn.commit()

    async def add_account(self, guild_id: int, channel_id: int, username: str):
        """Add a tracked X account."""
        username = username.lower().strip().replace("@", "")
        if self.db_type == "postgres":
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO tracked_accounts (guild_id, channel_id, username)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (guild_id, username) DO UPDATE
                    SET channel_id = $2
                """, guild_id, channel_id, username)
        else:
            await self.conn.execute("""
                INSERT OR REPLACE INTO tracked_accounts (guild_id, channel_id, username, last_post_id)
                VALUES (?, ?, ?, COALESCE((SELECT last_post_id FROM tracked_accounts WHERE guild_id=? AND username=?), ''))
            """, (guild_id, channel_id, username, guild_id, username))
            await self.conn.commit()

    async def remove_account(self, guild_id: int, username: str):
        """Remove a tracked X account."""
        username = username.lower().strip().replace("@", "")
        if self.db_type == "postgres":
            async with self.pool.acquire() as conn:
                result = await conn.execute("""
                    DELETE FROM tracked_accounts WHERE guild_id = $1 AND username = $2
                """, guild_id, username)
                return result
        else:
            cursor = await self.conn.execute(
                "DELETE FROM tracked_accounts WHERE guild_id = ? AND username = ?",
                (guild_id, username)
            )
            await self.conn.commit()
            return cursor.rowcount

    async def get_accounts(self, guild_id: int = None):
        """Get all tracked accounts, optionally filtered by guild."""
        if self.db_type == "postgres":
            async with self.pool.acquire() as conn:
                if guild_id:
                    rows = await conn.fetch("""
                        SELECT guild_id, channel_id, username, last_post_id
                        FROM tracked_accounts WHERE guild_id = $1
                    """, guild_id)
                else:
                    rows = await conn.fetch("""
                        SELECT guild_id, channel_id, username, last_post_id
                        FROM tracked_accounts
                    """)
                return [dict(row) for row in rows]
        else:
            if guild_id:
                cursor = await self.conn.execute(
                    "SELECT guild_id, channel_id, username, last_post_id FROM tracked_accounts WHERE guild_id = ?",
                    (guild_id,)
                )
            else:
                cursor = await self.conn.execute(
                    "SELECT guild_id, channel_id, username, last_post_id FROM tracked_accounts"
                )
            rows = await cursor.fetchall()
            return [
                {"guild_id": r[0], "channel_id": r[1], "username": r[2], "last_post_id": r[3]}
                for r in rows
            ]

    async def update_last_post(self, guild_id: int, username: str, post_id: str):
        """Update the last seen post ID for an account."""
        username = username.lower().strip()
        if self.db_type == "postgres":
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE tracked_accounts SET last_post_id = $1
                    WHERE guild_id = $2 AND username = $3
                """, post_id, guild_id, username)
        else:
            await self.conn.execute(
                "UPDATE tracked_accounts SET last_post_id = ? WHERE guild_id = ? AND username = ?",
                (post_id, guild_id, username)
            )
            await self.conn.commit()

    async def is_post_seen(self, username: str, post_id: str) -> bool:
        """Check if a post has already been processed."""
        if self.db_type == "postgres":
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT 1 FROM post_history WHERE username = $1 AND post_id = $2
                """, username, post_id)
                return row is not None
        else:
            cursor = await self.conn.execute(
                "SELECT 1 FROM post_history WHERE username = ? AND post_id = ?",
                (username, post_id)
            )
            row = await cursor.fetchone()
            return row is not None

    async def mark_post_seen(self, username: str, post_id: str):
        """Mark a post as processed."""
        if self.db_type == "postgres":
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO post_history (username, post_id) VALUES ($1, $2)
                    ON CONFLICT DO NOTHING
                """, username, post_id)
        else:
            await self.conn.execute(
                "INSERT OR IGNORE INTO post_history (username, post_id) VALUES (?, ?)",
                (username, post_id)
            )
            await self.conn.commit()

    async def close(self):
        """Close database connection."""
        if self.conn:
            await self.conn.close()
        if self.pool:
            await self.pool.close()
