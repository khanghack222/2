"""
Database Layer - SQLite with WAL mode and connection pooling
Pattern: Repository pattern with async operations
"""
import aiosqlite
import asyncio
from pathlib import Path
from typing import Optional, Any, Dict, List
from contextlib import asynccontextmanager


class Database:
    """
    Async SQLite database with WAL mode for better concurrency.
    Provides connection pooling and automatic schema migrations.
    """

    def __init__(self, db_path: str):
        """
        Initialize database.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._pool: Dict[int, aiosqlite.Connection] = {}
        self._lock = asyncio.Lock()

        # Ensure directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    async def connect(self) -> None:
        """Initialize database connection and create tables"""
        async with self._lock:
            conn = await aiosqlite.connect(self.db_path)
            conn.row_factory = aiosqlite.Row

            # Enable WAL mode for better concurrency
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA synchronous=NORMAL")
            await conn.execute("PRAGMA cache_size=10000")
            await conn.execute("PRAGMA temp_store=MEMORY")

            self._pool[0] = conn
            await self._create_tables(conn)

    async def _create_tables(self, conn: aiosqlite.Connection) -> None:
        """Create database tables if they don't exist"""

        # Reminders table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                remind_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Passwords table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS passwords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                encrypted_password TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # AI history table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # User preferences table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id INTEGER PRIMARY KEY,
                language TEXT DEFAULT 'vi',
                timezone TEXT DEFAULT 'Asia/Ho_Chi_Minh',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Usage statistics table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS usage_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                command TEXT NOT NULL,
                success BOOLEAN DEFAULT 1,
                duration_ms INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create indexes
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_reminders_user_id
            ON reminders(user_id, remind_at)
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_passwords_user_id
            ON passwords(user_id)
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ai_history_user_id
            ON ai_history(user_id, created_at)
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_usage_stats_user_id
            ON usage_stats(user_id, created_at)
        """)

        await conn.commit()

    @asynccontextmanager
    async def get_connection(self):
        """Get a database connection from the pool"""
        # For simplicity, use single connection
        # In production, implement proper connection pooling
        if not self._pool:
            await self.connect()

        conn = self._pool[0]
        try:
            yield conn
        except Exception:
            await conn.rollback()
            raise

    async def execute(
        self,
        query: str,
        params: tuple = (),
        commit: bool = True
    ) -> int:
        """
        Execute a query and return lastrowid.

        Args:
            query: SQL query
            params: Query parameters
            commit: Whether to commit

        Returns:
            Last row ID
        """
        async with self.get_connection() as conn:
            cursor = await conn.execute(query, params)
            if commit:
                await conn.commit()
            return cursor.lastrowid

    async def fetch_one(
        self,
        query: str,
        params: tuple = ()
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch a single row.

        Args:
            query: SQL query
            params: Query parameters

        Returns:
            Row as dict or None
        """
        async with self.get_connection() as conn:
            cursor = await conn.execute(query, params)
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def fetch_all(
        self,
        query: str,
        params: tuple = ()
    ) -> List[Dict[str, Any]]:
        """
        Fetch all rows.

        Args:
            query: SQL query
            params: Query parameters

        Returns:
            List of rows as dicts
        """
        async with self.get_connection() as conn:
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def close(self) -> None:
        """Close all database connections"""
        for conn in self._pool.values():
            await conn.close()
        self._pool.clear()
