"""database.py - SQLite database for bot."""
import aiosqlite, os, time, logging
logger = logging.getLogger(__name__)
DB_PATH = os.environ.get("DB_PATH", "bot.db")
_db = None

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
"""

async def get_db():
    global _db
    if _db is None:
        _db = await aiosqlite.connect(DB_PATH)
        _db.row_factory = aiosqlite.Row
        await _db.executescript(SCHEMA)
        await _db.commit()
    return _db

async def close_db():
    global _db
    if _db:
        await _db.close()
        _db = None

async def add_reminder(user_id, content, seconds, due_ts):
    db = await get_db()
    cur = await db.execute("INSERT INTO reminders (user_id,content,seconds,due_ts) VALUES (?,?,?,?)",
                           (user_id, content, seconds, due_ts))
    await db.commit()
    return cur.lastrowid

async def get_reminders(user_id):
    db = await get_db()
    cur = await db.execute("SELECT id,content,seconds,due_ts FROM reminders WHERE user_id=?",(user_id,))
    return [dict(r) for r in await cur.fetchall()]

async def get_all_reminders():
    db = await get_db()
    cur = await db.execute("SELECT id,user_id,content,seconds,due_ts FROM reminders")
    return [dict(r) for r in await cur.fetchall()]

async def delete_reminder(user_id, rid):
    db = await get_db()
    cur = await db.execute("DELETE FROM reminders WHERE user_id=? AND id=?",(user_id,rid))
    await db.commit()
    return cur.rowcount > 0

async def delete_reminder_by_id(rid):
    db = await get_db()
    await db.execute("DELETE FROM reminders WHERE id=?",(rid,))
    await db.commit()

async def add_password(user_id, label, password):
    db = await get_db()
    cur = await db.execute("INSERT INTO passwords (user_id,label,password) VALUES (?,?,?)",(user_id,label,password))
    await db.commit()
    return cur.lastrowid

async def get_passwords(user_id):
    db = await get_db()
    cur = await db.execute("SELECT id,label,password FROM passwords WHERE user_id=?",(user_id,))
    return [dict(r) for r in await cur.fetchall()]

async def update_password(user_id, pid, new_pw):
    db = await get_db()
    cur = await db.execute("UPDATE passwords SET password=? WHERE user_id=? AND id=?",(new_pw,user_id,pid))
    await db.commit()
    return cur.rowcount > 0

async def delete_password(user_id, pid):
    db = await get_db()
    cur = await db.execute("DELETE FROM passwords WHERE user_id=? AND id=?",(user_id,pid))
    await db.commit()
    return cur.rowcount > 0

async def log_command(user_id, username, command):
    db = await get_db()
    await db.execute("INSERT INTO stats_cmds (user_id,username,command,timestamp) VALUES (?,?,?,?)",
                     (user_id, username, command, time.time()))
    await db.commit()

async def log_error(command, error):
    db = await get_db()
    await db.execute("INSERT INTO stats_errors (command,error,timestamp) VALUES (?,?,?)",
                     (command, str(error)[:500], time.time()))
    await db.commit()

async def get_stats_summary():
    db = await get_db()
    today = time.time() - (time.time() % 86400)
    async def _one(sql): cur=await db.execute(sql);r=await cur.fetchone();return r[0] if r else 0
    async def _all(sql): cur=await db.execute(sql);return [dict(r) for r in await cur.fetchall()]
    return {
        "total_cmds": await _one("SELECT COUNT(*) FROM stats_cmds"),
        "today_cmds": await _one(f"SELECT COUNT(*) FROM stats_cmds WHERE timestamp>={today}"),
        "total_users": await _one("SELECT COUNT(DISTINCT user_id) FROM stats_cmds WHERE user_id IS NOT NULL"),
        "total_reminders": await _one("SELECT COUNT(*) FROM reminders"),
        "total_passwords": await _one("SELECT COUNT(*) FROM passwords"),
        "top_cmds": await _all("SELECT command,COUNT(*) as cnt FROM stats_cmds GROUP BY command ORDER BY cnt DESC LIMIT 10"),
        "top_users": await _all("SELECT user_id,username,COUNT(*) as cnt FROM stats_cmds WHERE user_id IS NOT NULL GROUP BY user_id ORDER BY cnt DESC LIMIT 10"),
        "recent_errors": await _all("SELECT command,error,timestamp FROM stats_errors ORDER BY timestamp DESC LIMIT 10"),
    }

async def save_ai_history(user_id: int, messages: list):
    """Store full chat history (excluding system prompt) as JSON."""
    db = await get_db()
    import json
    blob = json.dumps(messages, ensure_ascii=False)
    await db.execute(
        "INSERT OR REPLACE INTO ai_history (user_id, messages, updated_at) VALUES (?,?,?)",
        (user_id, blob, time.time()),
    )
    await db.commit()

async def load_ai_history(user_id: int) -> list:
    """Load chat history; returns list of {role, content} dicts."""
    db = await get_db()
    cur = await db.execute("SELECT messages FROM ai_history WHERE user_id=?", (user_id,))
    row = await cur.fetchone()
    if row:
        import json
        return json.loads(row[0])
    return []

async def clear_ai_history(user_id: int):
    db = await get_db()
    await db.execute("DELETE FROM ai_history WHERE user_id=?", (user_id,))
    await db.commit()

async def get_van_blacklist():
    db = await get_db()
    cur = await db.execute("SELECT url FROM van_blacklist")
    return [r[0] for r in await cur.fetchall()]

async def add_van_blacklist(url):
    db = await get_db()
    await db.execute("INSERT OR IGNORE INTO van_blacklist (url) VALUES (?)",(url,))
    await db.commit()

async def clear_van_blacklist():
    db = await get_db()
    await db.execute("DELETE FROM van_blacklist")
    await db.commit()
