"""database.py - SQLite database for bot with WAL mode and connection pooling."""
import aiosqlite
import os
import time
import logging
import asyncio

logger = logging.getLogger(__name__)
DB_PATH = os.environ.get("DB_PATH", "bot.db")
_db = None
_db_lock = asyncio.Lock()
_flush_task = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
    content TEXT NOT NULL, seconds INTEGER NOT NULL, due_ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS passwords (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
    label TEXT NOT NULL, password TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stats_cmds (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
    username TEXT, command TEXT NOT NULL, timestamp REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS stats_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT, command TEXT NOT NULL,
    error TEXT, timestamp REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS van_blacklist (
    id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS ai_history (
    user_id INTEGER PRIMARY KEY, messages TEXT NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS user_lang (
    user_id INTEGER PRIMARY KEY,
    lang TEXT NOT NULL DEFAULT 'vi',
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reminders_user ON reminders(user_id);
CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(due_ts);
CREATE INDEX IF NOT EXISTS idx_stats_cmds_user ON stats_cmds(user_id);
CREATE INDEX IF NOT EXISTS idx_stats_cmds_cmd ON stats_cmds(command);
CREATE INDEX IF NOT EXISTS idx_stats_cmds_ts ON stats_cmds(timestamp);
CREATE INDEX IF NOT EXISTS idx_stats_errors_ts ON stats_errors(timestamp);
CREATE INDEX IF NOT EXISTS idx_passwords_user ON passwords(user_id);
"""


async def get_db():
    global _db
    if _db is None:
        async with _db_lock:
            if _db is None:
                try:
                    _db = await aiosqlite.connect(DB_PATH)
                    _db.row_factory = aiosqlite.Row
                    await _db.execute("PRAGMA journal_mode=WAL")
                    await _db.execute("PRAGMA synchronous=NORMAL")
                    await _db.execute("PRAGMA cache_size=-64000")
                    await _db.execute("PRAGMA temp_store=MEMORY")
                    await _db.executescript(SCHEMA)
                    await _db.commit()
                    logger.info("Database connected (WAL mode)")
                except Exception:
                    _db = None
                    raise
    return _db


async def close_db():
    global _db, _flush_task
    if _flush_task and not _flush_task.done():
        _flush_task.cancel()
        try:
            await _flush_task
        except asyncio.CancelledError:
            pass
    if _db:
        await _db.close()
        _db = None
        logger.info("Database closed")


async def _flush_loop():
    """Batch commit writes every 2 seconds for better throughput."""
    global _db
    while True:
        try:
            await asyncio.sleep(2)
            if _db:
                await _db.commit()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.debug(f"Flush loop error: {e}")


def start_flush_loop():
    global _flush_task
    if _flush_task is None or _flush_task.done():
        _flush_task = asyncio.create_task(_flush_loop())


async def _exec_write(sql, params=None) -> aiosqlite.Cursor:
    """Queue a write and let the flush loop batch-commit."""
    db = await get_db()
    if params:
        return await db.execute(sql, params)
    return await db.execute(sql)


async def _exec_read(sql, params=None):
    """Immediate read with commit to ensure consistency."""
    db = await get_db()
    if params:
        cur = await db.execute(sql, params)
    else:
        cur = await db.execute(sql)
    return cur


async def add_reminder(user_id, content, seconds, due_ts):
    cur = await _exec_write(
        "INSERT INTO reminders (user_id,content,seconds,due_ts) VALUES (?,?,?,?)",
        (user_id, content, seconds, due_ts),
    )
    return cur.lastrowid


async def get_reminders(user_id):
    cur = await _exec_read("SELECT id,content,seconds,due_ts FROM reminders WHERE user_id=?", (user_id,))
    return [dict(r) for r in await cur.fetchall()]


async def get_all_reminders():
    cur = await _exec_read("SELECT id,user_id,content,seconds,due_ts FROM reminders")
    return [dict(r) for r in await cur.fetchall()]


async def delete_reminder(user_id, rid):
    db = await get_db()
    cur = await db.execute("DELETE FROM reminders WHERE user_id=? AND id=?", (user_id, rid))
    await db.commit()
    return cur.rowcount > 0 if cur.rowcount >= 0 else False


async def delete_reminder_by_id(rid):
    await _exec_write("DELETE FROM reminders WHERE id=?", (rid,))


async def add_password(user_id, label, password):
    cur = await _exec_write(
        "INSERT INTO passwords (user_id,label,password) VALUES (?,?,?)",
        (user_id, label, password),
    )
    return cur.lastrowid


async def get_passwords(user_id):
    cur = await _exec_read("SELECT id,label,password FROM passwords WHERE user_id=?", (user_id,))
    return [dict(r) for r in await cur.fetchall()]


async def update_password(user_id, pid, new_pw):
    cur = await _exec_write(
        "UPDATE passwords SET password=? WHERE user_id=? AND id=?",
        (new_pw, user_id, pid),
    )
    return cur.rowcount > 0


async def delete_password(user_id, pid):
    cur = await _exec_write("DELETE FROM passwords WHERE user_id=? AND id=?", (user_id, pid))
    return cur.rowcount > 0


async def log_command(user_id, username, command):
    await _exec_write(
        "INSERT INTO stats_cmds (user_id,username,command,timestamp) VALUES (?,?,?,?)",
        (user_id, username, command, time.time()),
    )


async def log_error(command, error):
    await _exec_write(
        "INSERT INTO stats_errors (command,error,timestamp) VALUES (?,?,?)",
        (command, str(error)[:500], time.time()),
    )


async def get_stats_summary():
    db = await get_db()
    today = time.time() - (time.time() % 86400)

    async def _one(sql, params=None):
        cur = await db.execute(sql, params or ())
        r = await cur.fetchone()
        return r[0] if r else 0

    async def _all(sql, params=None):
        cur = await db.execute(sql, params or ())
        return [dict(r) for r in await cur.fetchall()]

    return {
        "total_cmds": await _one("SELECT COUNT(*) FROM stats_cmds"),
        "today_cmds": await _one(
            "SELECT COUNT(*) FROM stats_cmds WHERE timestamp>=?", (today,)
        ),
        "total_users": await _one(
            "SELECT COUNT(DISTINCT user_id) FROM stats_cmds WHERE user_id IS NOT NULL"
        ),
        "total_reminders": await _one("SELECT COUNT(*) FROM reminders"),
        "total_passwords": await _one("SELECT COUNT(*) FROM passwords"),
        "top_cmds": await _all(
            "SELECT command,COUNT(*) as cnt FROM stats_cmds GROUP BY command ORDER BY cnt DESC LIMIT 10"
        ),
        "top_users": await _all(
            "SELECT user_id,username,COUNT(*) as cnt FROM stats_cmds "
            "WHERE user_id IS NOT NULL GROUP BY user_id ORDER BY cnt DESC LIMIT 10"
        ),
        "recent_errors": await _all(
            "SELECT command,error,timestamp FROM stats_errors ORDER BY timestamp DESC LIMIT 10"
        ),
    }


async def save_ai_history(user_id: int, messages: list):
    import json
    db = await get_db()
    blob = json.dumps(messages, ensure_ascii=False)
    await db.execute(
        "INSERT OR REPLACE INTO ai_history (user_id, messages, updated_at) VALUES (?,?,?)",
        (user_id, blob, time.time()),
    )
    await db.commit()


async def load_ai_history(user_id: int) -> list:
    import json
    cur = await _exec_read("SELECT messages FROM ai_history WHERE user_id=?", (user_id,))
    row = await cur.fetchone()
    if row:
        return json.loads(row[0])
    return []


async def clear_ai_history(user_id: int):
    await _exec_write("DELETE FROM ai_history WHERE user_id=?", (user_id,))


async def get_van_blacklist():
    cur = await _exec_read("SELECT url FROM van_blacklist")
    return [r[0] for r in await cur.fetchall()]


async def add_van_blacklist(url):
    await _exec_write("INSERT OR IGNORE INTO van_blacklist (url) VALUES (?)", (url,))


async def clear_van_blacklist():
    await _exec_write("DELETE FROM van_blacklist")


async def cleanup_old_errors(days=30):
    cutoff = time.time() - (days * 86400)
    await _exec_write("DELETE FROM stats_errors WHERE timestamp < ?", (cutoff,))


async def get_user_lang(user_id: int) -> str:
    cur = await _exec_read("SELECT lang FROM user_lang WHERE user_id=?", (user_id,))
    row = await cur.fetchone()
    return row[0] if row else "vi"


async def set_user_lang(user_id: int, lang: str):
    await _exec_write(
        "INSERT OR REPLACE INTO user_lang (user_id, lang, updated_at) VALUES (?,?,?)",
        (user_id, lang, time.time()),
    )
