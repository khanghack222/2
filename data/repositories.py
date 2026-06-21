"""
Repository Pattern - Data access layer
Pattern: Repository for each entity type
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from data.database import Database


class BaseRepository:
    """Base class for all repositories"""

    def __init__(self, db: Database):
        self.db = db


class ReminderRepository(BaseRepository):
    """Repository for reminder operations"""

    async def create(
        self,
        user_id: int,
        content: str,
        remind_at: datetime
    ) -> int:
        """
        Create a new reminder.

        Args:
            user_id: User ID
            content: Reminder content
            remind_at: When to remind

        Returns:
            Reminder ID
        """
        return await self.db.execute(
            """
            INSERT INTO reminders (user_id, content, remind_at)
            VALUES (?, ?, ?)
            """,
            (user_id, content, remind_at.isoformat())
        )

    async def get_by_user(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all reminders for a user"""
        return await self.db.fetch_all(
            """
            SELECT * FROM reminders
            WHERE user_id = ?
            ORDER BY remind_at ASC
            """,
            (user_id,)
        )

    async def get_pending(self) -> List[Dict[str, Any]]:
        """Get all pending reminders"""
        now = datetime.now().isoformat()
        return await self.db.fetch_all(
            """
            SELECT * FROM reminders
            WHERE remind_at <= ?
            ORDER BY remind_at ASC
            """,
            (now,)
        )

    async def delete(self, reminder_id: int) -> None:
        """Delete a reminder"""
        await self.db.execute(
            "DELETE FROM reminders WHERE id = ?",
            (reminder_id,)
        )


class PasswordRepository(BaseRepository):
    """Repository for password operations"""

    async def create(
        self,
        user_id: int,
        label: str,
        encrypted_password: str
    ) -> int:
        """
        Create a new password entry.

        Args:
            user_id: User ID
            label: Password label
            encrypted_password: Encrypted password

        Returns:
            Password ID
        """
        return await self.db.execute(
            """
            INSERT INTO passwords (user_id, label, encrypted_password)
            VALUES (?, ?, ?)
            """,
            (user_id, label, encrypted_password)
        )

    async def get_by_user(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all passwords for a user"""
        return await self.db.fetch_all(
            """
            SELECT id, label, created_at FROM passwords
            WHERE user_id = ?
            ORDER BY created_at DESC
            """,
            (user_id,)
        )

    async def get_password(
        self,
        password_id: int,
        user_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get a specific password"""
        return await self.db.fetch_one(
            """
            SELECT * FROM passwords
            WHERE id = ? AND user_id = ?
            """,
            (password_id, user_id)
        )

    async def delete(self, password_id: int, user_id: int) -> None:
        """Delete a password"""
        await self.db.execute(
            "DELETE FROM passwords WHERE id = ? AND user_id = ?",
            (password_id, user_id)
        )


class AIHistoryRepository(BaseRepository):
    """Repository for AI chat history"""

    async def add_message(
        self,
        user_id: int,
        role: str,
        content: str
    ) -> int:
        """
        Add a message to history.

        Args:
            user_id: User ID
            role: Message role (user/assistant)
            content: Message content

        Returns:
            Message ID
        """
        return await self.db.execute(
            """
            INSERT INTO ai_history (user_id, role, content)
            VALUES (?, ?, ?)
            """,
            (user_id, role, content)
        )

    async def get_history(
        self,
        user_id: int,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get chat history for a user.

        Args:
            user_id: User ID
            limit: Maximum messages to retrieve

        Returns:
            List of messages
        """
        return await self.db.fetch_all(
            """
            SELECT role, content FROM ai_history
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit)
        )

    async def clear_history(self, user_id: int) -> None:
        """Clear all history for a user"""
        await self.db.execute(
            "DELETE FROM ai_history WHERE user_id = ?",
            (user_id,)
        )


class UserRepository(BaseRepository):
    """Repository for user preferences"""

    async def get_preferences(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user preferences"""
        return await self.db.fetch_one(
            "SELECT * FROM user_preferences WHERE user_id = ?",
            (user_id,)
        )

    async def set_language(self, user_id: int, language: str) -> None:
        """Set user language preference"""
        await self.db.execute(
            """
            INSERT OR REPLACE INTO user_preferences (user_id, language, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            """,
            (user_id, language)
        )

    async def set_timezone(self, user_id: int, timezone: str) -> None:
        """Set user timezone"""
        await self.db.execute(
            """
            INSERT OR REPLACE INTO user_preferences (user_id, timezone, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            """,
            (user_id, timezone)
        )


class StatsRepository(BaseRepository):
    """Repository for usage statistics"""

    async def log_usage(
        self,
        user_id: int,
        command: str,
        success: bool = True,
        duration_ms: Optional[int] = None
    ) -> None:
        """
        Log command usage.

        Args:
            user_id: User ID
            command: Command name
            success: Whether command succeeded
            duration_ms: Execution duration in milliseconds
        """
        await self.db.execute(
            """
            INSERT INTO usage_stats (user_id, command, success, duration_ms)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, command, success, duration_ms)
        )

    async def get_user_stats(
        self,
        user_id: int,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Get usage statistics for a user.

        Args:
            user_id: User ID
            days: Number of days to look back

        Returns:
            Statistics dict
        """
        stats = await self.db.fetch_one(
            """
            SELECT
                COUNT(*) as total_commands,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful,
                SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failed,
                AVG(duration_ms) as avg_duration
            FROM usage_stats
            WHERE user_id = ?
            AND created_at >= datetime('now', '-' || ? || ' days')
            """,
            (user_id, days)
        )

        top_commands = await self.db.fetch_all(
            """
            SELECT command, COUNT(*) as count
            FROM usage_stats
            WHERE user_id = ?
            AND created_at >= datetime('now', '-' || ? || ' days')
            GROUP BY command
            ORDER BY count DESC
            LIMIT 5
            """,
            (user_id, days)
        )

        return {
            **stats,
            "top_commands": top_commands
        }
