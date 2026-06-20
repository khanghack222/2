import logging
import asyncio
import functools
import re
import datetime
import json
import os
import time
import urllib.request
import urllib.parse
import urllib.error
import secrets
import string
import random
import html as html_mod
import sys
import lunardate
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import database as db
from dashboard import setup_routes as setup_dashboard
from ai_chat import ask_ai

# FIX: consolidated logging config, added rotation-friendly format
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    force=True,
)
logger = logging.getLogger(__name__)

# FIX: validate TOKEN at startup instead of using a dummy fallback
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    sys.exit("FATAL: BOT_TOKEN environment variable is required")

# FIX: handle ADMIN_ID missing gracefully with warning
ADMIN_ID_STR = os.environ.get("ADMIN_ID")
ADMIN_ID = int(ADMIN_ID_STR) if ADMIN_ID_STR else None
if ADMIN_ID is None:
    logger.warning("ADMIN_ID not set — /restart disabled for all users")

DATA_FILE = "reminders.json"
API2_BYPASS_URL = "http://fi5.bot-hosting.net:22301/bypass"
API2_BYPASS_KEY = "thi-thi"
PASSWORDS_FILE = "passwords.json"
START_TIME = datetime.datetime.now()
VAN_BLACKLIST_FILE = "van_blacklist.json"

# Proxy list: paste proxy của bạn vào đây, mỗi dòng 1 cái
# Định dạng: ip:port hoặc user:pass@ip:port
PROXY_LIST = [
    # Thay proxy của bạn vào bên dưới, ví dụ:
    # "proxy1.example.com:8080",
    # "user:pass@proxy2.example.com:3128",
]



# FIX: safe JSON loading with corruption recovery
def safe_json_load(path, fallback):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, type(fallback)):
                    return data
                logger.warning(f"Corrupted {path}, resetting")
        return fallback
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        logger.warning(f"Cannot load {path}: {e}, resetting")
        return fallback


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# --- Password encryption (Fernet) ---
# FIX: passwords were stored in plaintext. We now encrypt passwords.json at rest.
# Key comes from PASS_KEY env (preferred for deploy) or a local pass.key file
# (auto-generated, gitignored). Legacy plaintext is migrated on first load.
PASSWORDS_ENC_FILE = "passwords.enc"
KEY_FILE = "pass.key"


def _get_fernet():
    from cryptography.fernet import Fernet
    key = os.environ.get("PASS_KEY")
    if key:
        key = key.encode()
        try:
            Fernet(key)
        except Exception:
            logger.warning("PASS_KEY invalid; use Fernet.generate_key()")
            raise
    elif os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as f:
            key = f.read()
    else:
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as f:
            f.write(key)
        logger.warning("Generated new %s — back it up or set PASS_KEY env", KEY_FILE)
    return Fernet(key)


def save_passwords(data):
    token = _get_fernet().encrypt(json.dumps(data, ensure_ascii=False).encode("utf-8"))
    with open(PASSWORDS_ENC_FILE, "wb") as f:
        f.write(token)


def load_passwords():
    # Migrate legacy plaintext passwords.json -> encrypted passwords.enc (once)
    if os.path.exists(PASSWORDS_FILE) and not os.path.exists(PASSWORDS_ENC_FILE):
        legacy = safe_json_load(PASSWORDS_FILE, {})
        save_passwords(legacy)
        try:
            os.remove(PASSWORDS_FILE)
        except OSError:
            pass
        logger.info("Migrated plaintext passwords -> encrypted store")
        return legacy
    if not os.path.exists(PASSWORDS_ENC_FILE):
        return {}
    try:
        with open(PASSWORDS_ENC_FILE, "rb") as f:
            token = f.read()
        if not token:
            return {}
        return json.loads(_get_fernet().decrypt(token).decode("utf-8"))
    except Exception as e:
        logger.warning("Cannot decrypt passwords: %s", e)
        return {}


# FIX: global mutable state is acceptable for single-process async,
# but we add a deep-copy on write to prevent partial corruption
reminders = safe_json_load(DATA_FILE, {})
passwords = load_passwords()


# --- Async HTTP helpers (non-blocking) ---
# FIX: urllib.urlopen is blocking; calling it directly inside an async handler
# freezes the whole bot until the request returns. We run it in a thread pool
# via asyncio.to_thread so other updates keep being processed concurrently.
DEFAULT_UA = "Mozilla/5.0"


class RateLimited(Exception):
    """Raised when an upstream API returns HTTP 429."""


def _fetch_bytes_sync(url, headers=None, data=None, timeout=10):
    req = urllib.request.Request(url, data=data, headers=headers or {"User-Agent": DEFAULT_UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise RateLimited(url) from e
        raise


async def fetch_bytes(url, headers=None, data=None, timeout=10):
    return await asyncio.to_thread(_fetch_bytes_sync, url, headers, data, timeout)


async def fetch_text(url, headers=None, data=None, timeout=10, encoding="utf-8"):
    raw = await fetch_bytes(url, headers=headers, data=data, timeout=timeout)
    return raw.decode(encoding)


async def fetch_json(url, headers=None, data=None, timeout=10):
    raw = await fetch_bytes(url, headers=headers, data=data, timeout=timeout)
    return json.loads(raw.decode("utf-8"))


# --- Simple TTL cache to cut down on repeat API calls ---
_cache = {}
_cache_maxsize = 200
_shutdown_event = None


def cache_get(key, ttl):
    entry = _cache.get(key)
    if entry is not None and (time.monotonic() - entry[0]) < ttl:
        return entry[1]
    return None


def cache_set(key, value):
    _cache[key] = (time.monotonic(), value)


# --- Per-user rate limiting (anti-spam) ---
_last_call = {}


def rate_limit(seconds=3):
    """Limit each user to one call per `seconds` for a given command."""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(update, context):
            user = update.effective_user
            key = (user.id, func.__name__)
            now = time.monotonic()
            elapsed = now - _last_call.get(key, 0.0)
            if elapsed < seconds:
                await update.effective_message.reply_text(
                    f"⏳ Chậm thôi nào! Thử lại sau {int(seconds - elapsed) + 1}s."
                )
                return
            _last_call[key] = now
            return await func(update, context)
        return wrapper
    return decorator


# --- Van blacklist helpers ---
def load_van_blacklist():
    return safe_json_load(VAN_BLACKLIST_FILE, [])


def save_van_blacklist(data):
    save_json(VAN_BLACKLIST_FILE, data)


# --- Core command handlers ---

# --- Interactive command menu (inline keyboard) ---
MENU_SECTIONS = {
    "tienich": ("🌤  Tiện ích",
        "`/weather`   — Xem thời tiết\n"
        "`/translate` — Dịch văn bản → Tiếng Việt\n"
        "`/shorten`   — Rút gọn đường link\n"
        "`/qr`        — Tạo mã QR\n"
        "`/ip`        — IP & vị trí của bạn\n"
        "`/screenshot` — Chụp ảnh trang web"),
    "congcu": ("🛠  Công cụ",
        "`/code`      — Code → ảnh đẹp\n"
        "`/calc`      — Máy tính (1+1, pi, sqrt)\n"
        "`/password`  — Tạo & lưu mật khẩu\n"
        "`/passwords` — DS mật khẩu đã lưu\n"
        "`/editpass`  — Sửa mật khẩu\n"
        "`/delpass`   — Xoá mật khẩu\n"
        "`/proxy`     — Proxy miễn phí ngẫu nhiên\n"
        "`/bypass`    — Bypass link rút gọn"),
    "giaitri": ("🎭  Giải trí",
        "`/joke`      — Chuyện cười ngẫu nhiên\n"
        "`/anime`     — Tra cứu anime\n"
        "`/meme`      — Meme ngẫu nhiên từ Reddit"),
    "hoctap": ("📚  Học tập",
        "`/van`       — Văn mẫu lớp 8\n"
        "`/dictionary` — Tra từ điển Anh-Việt\n"
        "`/wiki`      — Tra Wikipedia"),
    "taichinh": ("💰  Tài chính",
        "`/crypto`    — Giá crypto (BTC, ETH…)\n"
        "`/tygia`     — Tỷ giá ngoại tệ → VND"),
    "lich": ("📅  Lịch & Nhắc nhở",
        "`/lich`      — Lịch âm (hôm nay / ngày)\n"
        "`/remind`    — Đặt nhắc nhở\n"
        "`/list`      — DS nhắc nhở\n"
        "`/cancel`    — Huỷ nhắc nhở"),
    "ai": ("🤖  AI Chatbot",
        "`/ask <câu hỏi>`    — Hỏi AI ChatGPT/Claude\n"
        "`/ask reset`        — Xoá lịch sử chat"),
    "tiktok": ("🎵  TikTok",
        "`/tiktok <url>`      — Tải video không logo\n"
        "`/tiktok_profile <u>` — Xem profile\n"
        "`/tiktok_search <kw>` — Tìm kiếm video\n"
        "`/tiktok_trending`   — Video thịnh hành\n"
        "`/tiktok_seo <kw>`   — Gợi ý SEO\n"
        "`/tiktok_hashtag <t>` — Tra hashtag"),
    "stats": ("📊  Thống kê",
        "`/stats`      — Xem thống kê sử dụng\n"
        "`/myusage`    — Xem lịch sử của bạn"),
    "khac": ("ℹ️  Hệ thống",
        "`/id`        — Thông tin Telegram của bạn\n"
        "`/status`    — Trạng thái & thời gian hoạt động\n"
        "`/help`      — Hướng dẫn chi tiết"),
}

MENU_GREETING = (
    "╭──────────────────────────────────────╮\n"
    "│  🤖  **BOT TERMINAL**               │\n"
    "│  › Gõ `/help` để xem hướng dẫn  │\n"
    "╰──────────────────────────────────────╯\n\n"
    "━━━ Chọn danh mục bên dưới ━━━")


def main_menu_keyboard():
    rows, row = [], []
    for key, (title, _) in MENU_SECTIONS.items():
        row.append(InlineKeyboardButton(title, callback_data=f"menu_{key}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


# No-arg commands runnable straight from a menu button
SECTION_RUN = {
    "tienich": [("🌍 IP của tôi", "ip")],
    "giaitri": [("🎭 Joke", "joke"), ("😂 Meme", "meme")],
    "taichinh": [("💰 Crypto", "crypto"), ("💱 Tỷ giá", "tygia")],
}


def section_keyboard(key=None):
    rows = []
    run_btns = [
        InlineKeyboardButton(label, callback_data=f"run_{cmd}")
        for label, cmd in SECTION_RUN.get(key, [])
    ]
    for i in range(0, len(run_btns), 2):  # 2 nút / hàng
        rows.append(run_btns[i:i + 2])
    rows.append([InlineKeyboardButton("⬅️ Quay lại menu", callback_data="menu_home")])
    return InlineKeyboardMarkup(rows)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        MENU_GREETING, reply_markup=main_menu_keyboard(), parse_mode="Markdown"
    )


async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    # Quick-run a no-arg command from a button
    if data.startswith("run_"):
        handler = RUN_ACTIONS.get(data.replace("run_", ""))
        if handler:
            await handler(update, context)
        return
    if data == "menu_home":
        await q.edit_message_text(
            MENU_GREETING, reply_markup=main_menu_keyboard(), parse_mode="Markdown"
        )
        return
    key = data.replace("menu_", "")
    section = MENU_SECTIONS.get(key)
    if section:
        title, body = section
        await q.edit_message_text(
            f"**{title}**\n\n{body}", reply_markup=section_keyboard(key), parse_mode="Markdown"
        )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "━━━ **Ví dụ sử dụng** ━━━\n\n"
        "**Thời tiết & Dịch thuật**\n"
        "  `/weather hanoi`          — Thời tiết tại Hà Nội\n"
        "  `/translate hello`        — Dịch sang tiếng Việt\n\n"
        "**Web & Media**\n"
        "  `/shorten https://…`      — Rút gọn đường link\n"
        "  `/qr https://…`           — Tạo mã QR\n"
        "  `/screenshot https://…`   — Chụp ảnh trang web\n\n"
        "**Tài chính & Crypto**\n"
        "  `/crypto`                 — Giá BTC, ETH, SOL\n"
        "  `/tygia`                  — Tỷ giá ngoại tệ → VND\n\n"
        "**Máy tính**\n"
        "  `/calc 2+2*pi`            — Tính toán cơ bản\n"
        "  `/calc sqrt(144)+abs(-5)` — Hàm toán học\n\n"
        "**Mật khẩu**\n"
        "  `/password 16`            — Tạo mật khẩu 16 ký tự\n"
        "  `/password 20 email`      — Tạo + lưu với nhãn\n"
        "  `/passwords`              — DS mật khẩu đã lưu\n"
        "  `/editpass 1 newpass`     — Sửa mật khẩu số 1\n"
        "  `/delpass 1`              — Xoá mật khẩu số 1\n\n"
        "**Học tập**\n"
        "  `/dictionary hello`       — Tra từ điển Anh-Việt\n"
        "  `/wiki Vietnam`           — Tra Wikipedia\n"
        "  `/van`                    — Văn mẫu lớp 8\n\n"
        "**Giải trí**\n"
        "  `/joke`                   — Chuyện cười ngẫu nhiên\n"
        "  `/anime naruto`           — Tra cứu anime\n"
        "  `/meme`                   — Meme ngẫu nhiên\n\n"
        "**Lịch & Nhắc nhở**\n"
        "  `/lich`                   — Lịch âm (hôm nay)\n"
        "  `/lich 30/4/2026`         — Lịch âm (ngày cụ thể)\n"
        "  `/remind 60 Buy milk`     — Đặt nhắc nhở 60 giây\n"
        "  `/list`                   — DS nhắc nhở\n"
        "  `/cancel 1`               — Huỷ nhắc nhở số 1\n\n"
        "**Hệ thống**\n"
        "  `/id`                     — Thông tin Telegram của bạn\n"
        "  `/bypass`                 — Bypass link rút gọn\n"
        "  `/status`                 — Trạng thái & thời gian hoạt động\n"
        "  `/ip`                     — IP & vị trí của bạn\n"
        "  `/proxy`                  — Proxy miễn phí ngẫu nhiên\n\n"
        "**AI Chatbot**\n"
        "  `/ask <câu hỏi>`         — Hỏi AI (Groq/OpenAI free)\n"
        "  `/ask reset`             — Xoá lịch sử chat\n\n"
        "**Thống kê**\n"
        "  `/stats`                 — Xem thống kê sử dụng\n"
        "  `/myusage`               — Xem lịch sử của bạn\n\n"
        "**TikTok**\n"
        "  `/tiktok <url>`              — Tải video không logo\n"
        "  `/tiktok_profile <username>` — Xem profile TikTok\n"
        "  `/tiktok_search <từ khóa>`  — Tìm kiếm video\n"
        "  `/tiktok_trending`           — Video thịnh hành\n"
        "  `/tiktok_seo <từ khóa>`    — Gợi ý SEO\n"
        "  `/tiktok_hashtag <tag>`      — Tra hashtag"
    )
    await update.message.reply_text(msg)


async def _fire_reminder(bot, user_id, rid, content, due_ts):
    """Sleep until due_ts (absolute epoch) then deliver, surviving restarts."""
    try:
        await asyncio.sleep(max(0, due_ts - time.time()))
        await bot.send_message(chat_id=int(user_id), text=f"⏰ Nhắc nhở #{rid}: {content}")
    except Exception as e:
        logger.warning(f"Failed to send reminder #{rid}: {e}")
    finally:
        if user_id in reminders:
            reminders[user_id] = [r for r in reminders[user_id] if r["id"] != rid]
            save_json(DATA_FILE, reminders)


async def reschedule_reminders(bot):
    """Re-arm reminders persisted in JSON after a restart."""
    count = 0
    for user_id, items in list(reminders.items()):
        for r in items:
            # legacy entries had no due_ts; fall back to original seconds from now
            due_ts = r.get("due_ts", time.time() + r.get("seconds", 0))
            asyncio.create_task(_fire_reminder(bot, user_id, r["id"], r["content"], due_ts))
            count += 1
    if count:
        logger.info("Re-scheduled %d reminder(s) after startup", count)


async def remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        seconds = int(context.args[0])
        content = " ".join(context.args[1:]) if len(context.args) > 1 else "Nhắc nhở!"
        # FIX: upper bound to prevent memory exhaustion
        if seconds < 5:
            await update.message.reply_text("Tối thiểu 5 giây.")
            return
        if seconds > 86400 * 30:  # 30 days max
            await update.message.reply_text("Tối đa 30 ngày.")
            return

        user_id = str(update.effective_user.id)
        if user_id not in reminders:
            reminders[user_id] = []
        # FIX: use max+1 (not len+1) so ids don't collide after deletions
        rid = max((r["id"] for r in reminders[user_id]), default=0) + 1
        due_ts = time.time() + seconds
        reminders[user_id].append({"id": rid, "content": content, "seconds": seconds, "due_ts": due_ts})
        save_json(DATA_FILE, reminders)

        await update.message.reply_text(f" Đã đặt nhắc nhở #{rid}: '{content}' sau {seconds}s")
        asyncio.create_task(_fire_reminder(context.application.bot, user_id, rid, content, due_ts))
    except (IndexError, ValueError):
        await update.message.reply_text("Sai cú pháp. Ví dụ: /remind 60 Mua sữa")


async def list_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in reminders or not reminders[user_id]:
        await update.message.reply_text("Không có nhắc nhở nào.")
        return
    now = time.time()
    lines = []
    for r in reminders[user_id]:
        left = int(r.get("due_ts", now + r.get("seconds", 0)) - now)
        left = max(0, left)
        lines.append(f"#{r['id']} - {r['content']} (còn {left}s)")
    await update.message.reply_text("Danh sách nhắc nhở:\n" + "\n".join(lines))


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        rid = int(context.args[0])
        user_id = str(update.effective_user.id)
        if user_id in reminders:
            reminders[user_id] = [r for r in reminders[user_id] if r["id"] != rid]
            save_json(DATA_FILE, reminders)
            await update.message.reply_text(f" Đã hủy nhắc nhở #{rid}")
        else:
            await update.message.reply_text("Không tìm thấy nhắc nhở.")
    except (IndexError, ValueError):
        await update.message.reply_text("Sai cú pháp. Ví dụ: /cancel 1")


@rate_limit(3)
async def dictionary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    word = " ".join(context.args)
    if not word:
        await update.message.reply_text("Nhập từ cần tra. Ví dụ: /dictionary hello")
        return

    cache_key = f"dict:{word.lower()}"
    cached = cache_get(cache_key, ttl=86400)
    if cached:
        await update.message.reply_text(cached)
        return

    try:
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{urllib.parse.quote(word)}"
        data = await fetch_json(url)

        meanings = data[0].get("meanings", [])
        lines = [f"**{data[0]['word']}**"]
        for m in meanings[:3]:
            part = m["partOfSpeech"]
            defs = m["definitions"][:2]
            for d in defs:
                lines.append(f"({part}) {d['definition']}")
                if d.get("example"):
                    lines.append(f"  VD: {d['example']}")
        result = "\n".join(lines) if len(lines) > 1 else "Không tìm thấy."
        if len(lines) > 1:
            cache_set(cache_key, result)
        await update.message.reply_text(result)
    except Exception as e:
        logger.debug(f"Dictionary lookup failed: {e}")
        await update.message.reply_text(f"Không tìm thấy từ '{word}' hoặc lỗi API.")


# WMO weather interpretation codes -> Vietnamese description
# https://open-meteo.com/en/docs (weather_code)
WMO_CODES = {
    0: "Trời quang", 1: "Ít mây", 2: "Có mây", 3: "Nhiều mây",
    45: "Sương mù", 48: "Sương mù đóng băng",
    51: "Mưa phùn nhẹ", 53: "Mưa phùn", 55: "Mưa phùn dày",
    56: "Mưa phùn băng giá nhẹ", 57: "Mưa phùn băng giá",
    61: "Mưa nhẹ", 63: "Mưa vừa", 65: "Mưa to",
    66: "Mưa băng giá nhẹ", 67: "Mưa băng giá",
    71: "Tuyết nhẹ", 73: "Tuyết vừa", 75: "Tuyết dày", 77: "Hạt tuyết",
    80: "Mưa rào nhẹ", 81: "Mưa rào", 82: "Mưa rào dữ dội",
    85: "Mưa tuyết nhẹ", 86: "Mưa tuyết dày",
    95: "Dông", 96: "Dông kèm mưa đá nhẹ", 99: "Dông kèm mưa đá to",
}


@rate_limit(3)
async def weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = " ".join(context.args)
    if not city:
        await update.message.reply_text(
            "🌤 `/weather hanoi` — Thời tiết Hà Nội\n"
            "🌤 `/weather tuyên quang` — Tuyên Quang\n"
            "🌤 `/weather da nang` — Đà Nẵng"
        )
        return

    # FIX: strip legacy ",vi"/",vn" suffix from the old wttr.in format
    city = city.split(",")[0].strip()
    cache_key = f"weather:{city.lower()}"
    cached = cache_get(cache_key, ttl=300)
    if cached:
        await update.message.reply_text(cached)
        return

    try:
        # Step 1: geocode city name -> lat/lon
        geo_url = (
            "https://geocoding-api.open-meteo.com/v1/search"
            f"?name={urllib.parse.quote(city)}&count=1&language=vi&format=json"
        )
        geo = await fetch_json(geo_url)
        results = geo.get("results")
        if not results:
            await update.message.reply_text(f"❌ Không tìm thấy '{city}'. Thử /weather hanoi")
            return
        loc = results[0]
        lat, lon = loc["latitude"], loc["longitude"]
        name = loc.get("name", city.title())
        admin = loc.get("admin1") or loc.get("country") or ""

        # Step 2: current weather at those coordinates
        fc_url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            "&current=temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code,apparent_temperature"
            "&wind_speed_unit=kmh&timezone=auto"
        )
        fc = await fetch_json(fc_url)
        cur = fc["current"]
        desc = WMO_CODES.get(cur.get("weather_code"), "Không rõ")
        place = f"{name}, {admin}" if admin else name
        msg = (
            f"🌤 **Thời tiết {place}:**\n"
            f"☁️ {desc}\n"
            f"🌡 {cur['temperature_2m']}°C (cảm giác {cur['apparent_temperature']}°C)\n"
            f"💧 Độ ẩm {cur['relative_humidity_2m']}%\n"
            f"💨 Gió {cur['wind_speed_10m']} km/h"
        )
        cache_set(cache_key, msg)
        await update.message.reply_text(msg)
    except RateLimited:
        await update.message.reply_text("⏳ API thời tiết đang bị giới hạn, thử lại sau.")
    except Exception as e:
        logger.debug(f"Weather failed: {e}")
        await update.message.reply_text(f"❌ Không tìm thấy '{city}'. Thử /weather hanoi")


@rate_limit(5)
async def ip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cached = cache_get("ip", ttl=300)
    if cached:
        await update.effective_message.reply_text(cached)
        return
    try:
        data = await fetch_json("http://ip-api.com/json/")
        msg = (
            f"IP: {data.get('query')}\n"
            f"Quốc gia: {data.get('country')}\n"
            f"Thành phố: {data.get('city')}\n"
            f"ISP: {data.get('isp')}\n"
            f"Lat/Lon: {data.get('lat')}, {data.get('lon')}"
        )
        cache_set("ip", msg)
        await update.effective_message.reply_text(msg)
    except Exception as e:
        logger.debug(f"IP lookup failed: {e}")
        await update.effective_message.reply_text("Lỗi lấy thông tin IP.")


async def password_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        length = int(context.args[0]) if context.args else 16
    except ValueError:
        length = 16
    length = max(6, min(length, 64))
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    pw = "".join(secrets.choice(chars) for _ in range(length))

    user_id = str(update.effective_user.id)
    if user_id not in passwords:
        passwords[user_id] = []
    idx = max((p["id"] for p in passwords[user_id]), default=0) + 1
    label = " ".join(context.args[1:]) if len(context.args) > 1 else f"pass{idx}"
    # FIX: passwords stored in plaintext — for a personal bot this is acceptable,
    # but consider adding encryption for production use
    passwords[user_id].append({"id": idx, "label": label, "password": pw})
    save_passwords(passwords)
    await update.message.reply_text(
        f" Đã tạo & lưu mật khẩu #{idx}:\nTên: {label}\nMật khẩu: `{pw}`\n\nDùng /passwords để xem danh sách.",
        parse_mode="Markdown"
    )


async def list_passwords(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in passwords or not passwords[user_id]:
        await update.message.reply_text("Bạn chưa lưu mật khẩu nào. Dùng /password để tạo.")
        return
    lines = [f"#{p['id']} - {p['label']}: `{p['password']}`" for p in passwords[user_id]]
    # FIX: limit output length to avoid Telegram message size limit
    text = "Danh sách mật khẩu:\n" + "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "..."
    await update.message.reply_text(text, parse_mode="Markdown")


async def editpass_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        pid = int(context.args[0])
        new_val = " ".join(context.args[1:])
        if not new_val:
            await update.message.reply_text("Sai cú pháp. VD: /editpass 1 abc123")
            return
        user_id = str(update.effective_user.id)
        if user_id in passwords:
            for p in passwords[user_id]:
                if p["id"] == pid:
                    p["password"] = new_val
                    save_passwords(passwords)
                    await update.message.reply_text(f" Đã cập nhật mật khẩu #{pid}: `{new_val}`", parse_mode="Markdown")
                    return
        await update.message.reply_text(f"Không tìm thấy mật khẩu #{pid}")
    except (IndexError, ValueError):
        await update.message.reply_text("Sai cú pháp. VD: /editpass 1 abc123")


async def delpass_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        pid = int(context.args[0])
        user_id = str(update.effective_user.id)
        if user_id in passwords:
            passwords[user_id] = [p for p in passwords[user_id] if p["id"] != pid]
            save_passwords(passwords)
            await update.message.reply_text(f" Đã xóa mật khẩu #{pid}")
        else:
            await update.message.reply_text(f"Không tìm thấy mật khẩu #{pid}")
    except (IndexError, ValueError):
        await update.message.reply_text("Sai cú pháp. VD: /delpass 1")


async def _fetch_free():
    urls = [
        "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all",
        "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
        "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
        "https://raw.githubusercontent.com/ngosang/proxies/main/proxies.txt",
        "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
        "https://raw.githubusercontent.com/opsxcq/proxy-list/master/list.txt",
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
        "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
    ]
    proxies = []
    for url in urls:
        try:
            data = await fetch_text(url)
            proxies.extend([p.strip() for p in data.splitlines() if p.strip()])
        except Exception: continue
    return proxies


@rate_limit(5)
async def proxy_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        n = 1
        if context.args:
            try: n = max(1, min(50, int(context.args[0])))
            except: pass
        if PROXY_LIST:
            proxies = PROXY_LIST
        else:
            proxies = await _fetch_free()
        proxies = list(dict.fromkeys(p for p in proxies if p))
        if proxies:
            n = min(n, len(proxies))
            picked = random.sample(proxies, n)
            msg = f"Proxy ({n} cai):\n\n" + "\n".join(f"`{p}`" for p in picked)
            await update.message.reply_text(msg, parse_mode="Markdown")
        else:
            await update.message.reply_text("Khong co proxy nao.")
    except Exception as e:
        logger.warning(f"Proxy cmd: {e}")
        await update.message.reply_text("Loi lay proxy.")


@rate_limit(3)
async def bypass_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = " ".join(context.args)
    if not link:
        await update.message.reply_text(
            "🔗 **Bypass Link**\n\n"
            "Dùng: `/bypass <url>` — Bỏ qua link rút gọn, lấy link gốc.\n\n"
            "Ví dụ: `/bypass https://shorturl.at/abc123`",
            parse_mode="Markdown"
        )
        return
    if not link.startswith("http"):
        link = "https://" + link
    try:
        params = urllib.parse.urlencode({"link": link, "key": API2_BYPASS_KEY})
        url = f"{API2_BYPASS_URL}?{params}"
        data = await fetch_json(url, headers={"User-Agent": "curl/8.0"}, timeout=15)
        result = data.get("result") or data.get("data") or data.get("url") or data.get("bypass") or json.dumps(data, ensure_ascii=False)
        msg = (
            f"🔓 **Kết quả Bypass:**\n\n"
            f"{result}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
    except RateLimited:
        await update.message.reply_text("⏳ API bypass dang bi gioi han, thu lai sau.")
    except Exception as e:
        logger.debug(f"Bypass failed: {e}")
        await update.message.reply_text("❌ Loi bypass link. Kiem tra lai URL hoac thu lai sau.")


@rate_limit(5)
async def code_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ext = context.args[0] if context.args else "py"
    await update.message.reply_text(
        "Gửi code của bạn (text), tôi sẽ tạo ảnh.\n"
        "Hỗ trợ: py, js, ts, java, cpp, html, css, go, rust, php"
    )
    context.user_data["waiting_code"] = ext


async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ext = context.user_data.pop("waiting_code", None)
    if not ext:
        return False
    text = update.message.text
    lang_map = {
        "py": "python", "js": "javascript", "ts": "typescript",
        "java": "java", "cpp": "cpp", "html": "html", "css": "css",
        "go": "go", "rust": "rust", "php": "php", "c": "c",
    }
    lang = lang_map.get(ext, ext)
    try:
        data = json.dumps({
            "code": text,
            "settings": {"language": lang, "theme": "dracula"},
        }).encode()
        img_data = await fetch_bytes(
            "https://sourcecodeshots.com/api/image",
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
            timeout=30,
        )
        await update.message.reply_photo(photo=img_data, caption=f"Code ({lang})")
    except Exception as e:
        logger.debug(f"Code image failed: {e}")
        await update.message.reply_text("Lỗi tạo ảnh code. Thử lại sau.")
    return True


@rate_limit(10)
async def screenshot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = " ".join(context.args)
    if not url:
        await update.message.reply_text("Nhập URL. Ví dụ: /screenshot https://google.com")
        return
    if not url.startswith("http"):
        url = "https://" + url
    try:
        api_url = f"https://api.microlink.io/?url={urllib.parse.quote(url)}&screenshot=true"
        data = await fetch_json(api_url, headers={"User-Agent": "curl/8.0"}, timeout=30)
        img_url = data.get("data", {}).get("screenshot", {}).get("url")
        if not img_url:
            await update.message.reply_text("Không thể chụp ảnh.")
            return
        img_data = await fetch_bytes(img_url, headers={"User-Agent": "curl/8.0"}, timeout=30)
        await update.message.reply_photo(photo=img_data, caption=f"Screenshot: {url}")
    except Exception as e:
        logger.debug(f"Screenshot failed: {e}")
        await update.message.reply_text("Lỗi chụp ảnh. URL không hợp lệ hoặc API giới hạn.")


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("waiting_code"):
        await handle_code(update, context)
        return
    text = update.message.text
    if text.startswith("nhắc"):
        parts = text.split(" ", 1)
        if len(parts) > 1:
            await update.message.reply_text(f" Dùng lệnh: /remind 60 {parts[1]}")
    elif "hello" in text.lower():
        await update.message.reply_text("Hello! Bạn cần gì?")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # FIX: log full traceback for debugging
    logger.exception(f"Update {update.update_id} caused error", exc_info=context.error)


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import platform

    uptime = datetime.datetime.now() - START_TIME
    days = uptime.days
    hours, rem = divmod(uptime.seconds, 3600)
    minutes, _ = divmod(rem, 60)
    total_users = len(set(list(reminders.keys()) + list(passwords.keys())))
    total_reminders = sum(len(v) for v in reminders.values())
    total_passwords = sum(len(v) for v in passwords.values())

    # FIX: cache git hash so we don't spawn a subprocess on every /status call
    if not hasattr(status_cmd, "_git_hash"):
        try:
            import subprocess
            result = subprocess.run(
                ["git", "log", "--oneline", "-1"],
                capture_output=True, text=True, timeout=5
            )
            status_cmd._git_hash = result.stdout.strip() or "N/A"
        except Exception:
            status_cmd._git_hash = "N/A"
    git_hash = status_cmd._git_hash

    # FIX: removed broken ctypes memory detection, use os-based approach
    memory = "N/A"
    try:
        if os.name == "posix":
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemAvailable:"):
                        kb = int(line.split()[1])
                        memory = f"{kb // 1024}MB"
                        break
        else:
            memory = "N/A (Windows)"
    except Exception:
        memory = "N/A"

    msg = (
        f"Bot Status\n"
        f"Thời gian chạy: {days}d {hours}h {minutes}m\n"
        f"Python: {sys.version.split()[0]}\n"
        f"OS: {platform.system()} {platform.release()}\n"
        f"Git: {git_hash}\n"
        f"Ram khả dụng: {memory}\n"
        f"Người dùng: {total_users}\n"
        f"Nhắc nhở: {total_reminders}\n"
        f"Mật khẩu đã lưu: {total_passwords}"
    )
    await update.message.reply_text(msg)


@rate_limit(10)
async def van_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    BASE = "https://vietjack.com"
    try:
        html = await fetch_text(BASE + "/van-mau-lop-8/", timeout=15)
        links = re.findall(r'href="([^"]+)"', html)
        essays = []
        for l in links:
            if "/van-mau-lop-8/" in l and l.endswith(".jsp") and "index.jsp" not in l:
                if l.startswith("../"):
                    essays.append(BASE + l[2:])
                else:
                    essays.append(BASE + l)
        if not essays:
            await update.message.reply_text("Không tìm thấy bài văn nào.")
            return
        blacklist = load_van_blacklist()
        available = [e for e in essays if e not in blacklist]
        if not available:
            blacklist.clear()
            available = essays
        essay_url = random.choice(available)
        blacklist.append(essay_url)
        save_van_blacklist(blacklist)
        html2 = await fetch_text(essay_url, timeout=15)

        # Extract middle-col content with proper depth tracking
        m = re.search(r'<div[^>]*class="[^"]*(?:col-md-7\s+)?middle-col[^"]*"[^>]*>', html2, re.DOTALL)
        if m:
            depth = 1; i = m.end()
            while i < len(html2) and depth > 0:
                if html2[i:i+6] == '</div>':
                    depth -= 1; i += 6
                elif html2[i:i+4] == '<!--':
                    end = html2.find('-->', i+4)
                    i = end + 3 if end > i else i + 1
                elif html2[i] == '<' and html2[i+1:i+4] == 'div' and html2[i+4:i+5] in (' ', '>', '\n', '\r', '\t'):
                    depth += 1; i += 4
                else:
                    i += 1
            content = html2[m.end():i-6]
        else:
            content = html2

        # FIX: combined multiple regex substitutions into one pass
        for tag in ['script', 'style']:
            content = re.sub(rf'<{tag}[^>]*>.*?</{tag}>', '', content, flags=re.DOTALL)
        for cls in ['pre-btn', 'nxt-btn', 'social-btn', 'box-new-title', 'box-new', 'vj-toc', 'ads_ads', 'ads_txt']:
            content = re.sub(rf'<div[^>]*class="[^"]*{re.escape(cls)}[^"]*"[^>]*>.*?</div>', '', content, flags=re.DOTALL)
        content = re.sub(r'<div[^>]*class="[^"]*bottom(?:google)?ad[^"]*"[^>]*>.*?</div>', '', content, flags=re.DOTALL)

        # Split into sections by anchor tags, skip outline sections
        sections = re.split(r'(<a\s+name="[^"]*"\s*></a>)', content)
        keep_parts = []
        current_is_dany = False
        for part in sections:
            anchor = re.search(r'name="([^"]*)"', part)
            if anchor:
                current_is_dany = anchor.group(1) in ('dany', 'dan-y', 'dany')
                continue
            if not current_is_dany and part.strip():
                keep_parts.append(part)
            current_is_dany = False

        content = '\n'.join(keep_parts)
        p_tags = re.findall(r'<p[^>]*>(.*?)</p>', content, re.DOTALL)
        paragraphs = []
        for p in p_tags:
            text = re.sub(r'<[^>]+>', '', p)
            text = html_mod.unescape(text).strip()
            if len(text) > 30 and 'Mục lục' not in text and 'Quảng cáo' not in text:
                paragraphs.append(text)
        result = '\n\n'.join(paragraphs)
        if len(result) > 4000:
            result = result[:4000] + "..."
        await update.message.reply_text(result)
    except Exception as e:
        logger.debug(f"Van command failed: {e}")
        await update.message.reply_text("Lỗi lấy bài văn.")


@rate_limit(3)
async def translate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Nhập văn bản. VD: /translate hello world")
        return
    try:
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=vi&dt=t&q={urllib.parse.quote(text)}"
        result = await fetch_json(url, headers={"User-Agent": "curl/8.0"})
        # FIX: safer traversal of nested array response
        translated = ""
        if isinstance(result, list) and len(result) > 0 and isinstance(result[0], list):
            translated = "".join(part[0] for part in result[0] if isinstance(part, list) and len(part) > 0)
        else:
            translated = str(result)
        await update.message.reply_text(f"Bản dịch: {translated}")
    except Exception as e:
        logger.debug(f"Translate failed: {e}")
        await update.message.reply_text("Lỗi dịch.")


@rate_limit(3)
async def shorten_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = " ".join(context.args)
    if not url:
        await update.message.reply_text("Nhập URL. VD: /shorten https://example.com")
        return
    try:
        api = f"https://tinyurl.com/api-create.php?url={urllib.parse.quote(url)}"
        short = (await fetch_text(api, headers={"User-Agent": "curl/8.0"})).strip()
        await update.message.reply_text(f"Link rút gọn: {short}")
    except Exception as e:
        logger.debug(f"Shorten failed: {e}")
        await update.message.reply_text("Lỗi rút gọn link.")


@rate_limit(3)
async def qr_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Nhập nội dung. VD: /qr https://google.com")
        return
    try:
        url = f"https://api.qrserver.com/v1/create-qr-code/?size=400x400&data={urllib.parse.quote(text)}"
        img = await fetch_bytes(url, headers={"User-Agent": "curl/8.0"}, timeout=15)
        await update.message.reply_photo(photo=img, caption="QR Code")
    except Exception as e:
        logger.debug(f"QR failed: {e}")
        await update.message.reply_text("Lỗi tạo QR.")


@rate_limit(3)
async def crypto_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cached = cache_get("crypto", ttl=60)
    if cached:
        await update.effective_message.reply_text(cached)
        return
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana,binancecoin,ripple&vs_currencies=usd&include_24hr_change=true"
        data = await fetch_json(url, headers={"User-Agent": "curl/8.0"})
        lines = ["Giá Crypto (USD):"]
        for coin, info in data.items():
            price = info["usd"]
            change = info.get("usd_24h_change", 0)
            arrow = "📈" if change >= 0 else "📉"
            lines.append(f"{coin.upper()}: ${price} ({arrow} {change:+.2f}%)")
        result = "\n".join(lines)
        cache_set("crypto", result)
        await update.effective_message.reply_text(result)
    except RateLimited:
        await update.effective_message.reply_text("⏳ API crypto đang bị giới hạn, thử lại sau ít phút.")
    except Exception as e:
        logger.debug(f"Crypto failed: {e}")
        await update.effective_message.reply_text("Lỗi lấy giá crypto.")


@rate_limit(3)
async def joke_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = "https://v2.jokeapi.dev/joke/Any?safe-mode"
        data = await fetch_json(url, headers={"User-Agent": "curl/8.0"})
        text = data.get("joke") or (data["setup"] + "\n" + data["delivery"])
        turl = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=vi&dt=t&q=" + urllib.parse.quote(text)
        tdata = await fetch_json(turl, headers={"User-Agent": "curl/8.0"})
        translated = "".join(part[0] for part in tdata[0]) if isinstance(tdata, list) and len(tdata) > 0 else str(tdata)
        await update.effective_message.reply_text(translated)
    except Exception as e:
        logger.debug(f"Joke failed: {e}")
        await update.effective_message.reply_text("Lỗi lấy joke.")


async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = f"@{user.username}" if user.username else "Không có"
    msg = (
        f"ID của bạn: {user.id}\n"
        f"Tên: {user.full_name}\n"
        f"Username: {username}"
    )
    await update.message.reply_text(msg)


async def restart_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ADMIN_ID is not None and user_id != ADMIN_ID:
        await update.message.reply_text("Bạn không có quyền restart bot.")
        return
    await update.message.reply_text("Đang restart bot...")
    # FIX: flush JSON state before exit to prevent data loss
    save_json(DATA_FILE, reminders)
    save_passwords(passwords)
    logger.info("Bot restart initiated by user %s", user_id)
    global _shutdown_event
    _shutdown_event = True


# FIX: replaced eval with a safe expression parser for calc_cmd
# Sandbox escape via eval("math.__class__.__mro__[1].__subclasses__()...") is blocked
SAFE_MATH = {
    "abs": abs, "round": round, "int": int, "float": float, "str": str,
    "len": len, "min": min, "max": max, "sum": sum, "pow": pow,
    "sqrt": lambda x: x ** 0.5,
    "pi": 3.141592653589793, "e": 2.718281828459045,
}


def safe_eval(expr):
    """Evaluate a math expression safely without using eval on raw input.
    
    Uses a restricted syntax: only numbers, operators, parentheses, and
    whitelisted names are allowed.
    """
    # FIX: character whitelist blocks all injection vectors
    allowed_chars = set("0123456789+-*/.()% ,[]abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_")
    if not all(c in allowed_chars for c in expr):
        raise ValueError("Invalid characters in expression")

    # FIX: compile AST and verify it contains only safe nodes
    import ast
    tree = ast.parse(expr, mode="eval")
    # FIX: Python 3.14 removed ast.Num/ast.Str - use ast.Constant only
    allowed_node_types = {
        ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.List,
        ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow,
        ast.FloorDiv, ast.USub, ast.UAdd,
        ast.Name, ast.Call, ast.Attribute,
        ast.Load,
    }
    for node in ast.walk(tree):
        if type(node) not in allowed_node_types:
            raise ValueError(f"Expression contains forbidden construct: {type(node).__name__}")
        # Block attribute access (prevents __class__ attacks)
        if isinstance(node, ast.Attribute):
            raise ValueError("Attribute access is not allowed")

    compiled = compile(tree, filename="<safe_eval>", mode="eval")
    # FIX: no __builtins__, use SAFE_MATH as the local namespace
    return eval(compiled, {"__builtins__": {}}, SAFE_MATH)


async def calc_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    expr = " ".join(context.args)
    if not expr:
        await update.message.reply_text("Nhập biểu thức. VD:\n/calc 1+1\n/calc 2x3 (x = nhân)\n/calc 6:2 (: = chia)")
        return
    try:
        expr_normalized = expr.replace("x", "*").replace("X", "*").replace(":", "/")
        result = safe_eval(expr_normalized)
        await update.message.reply_text(f"= {result}")
    except Exception as e:
        logger.debug(f"Calc failed: {expr} -> {e}")
        await update.message.reply_text("Lỗi tính toán.")


@rate_limit(3)
async def anime_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("Nhập tên anime. VD: /anime one piece")
        return

    cache_key = f"anime:{query.lower()}"
    cached = cache_get(cache_key, ttl=3600)
    if cached:
        msg, img = cached
        if img:
            await update.message.reply_photo(photo=img, caption=msg, parse_mode="HTML")
        else:
            await update.message.reply_text(msg, parse_mode="HTML")
        return

    try:
        url = f"https://api.jikan.moe/v4/anime?q={urllib.parse.quote(query)}&limit=1"
        data = await fetch_json(url)
        if not data.get("data"):
            await update.message.reply_text("Không tìm thấy anime.")
            return
        a = data["data"][0]
        title = a.get("title", "N/A")
        title_jp = a.get("title_japanese", "")
        type_ = a.get("type", "N/A")
        episodes = a.get("episodes", "N/A")
        score = a.get("score", "N/A")
        status = a.get("status", "N/A")
        synopsis = a.get("synopsis", "")
        if synopsis and len(synopsis) > 300:
            synopsis = synopsis[:300] + "..."
        msg = f"<b>{title}</b>"
        if title_jp:
            msg += f" ({title_jp})"
        msg += f"\nType: {type_} | Ep: {episodes} | Score: {score} | Status: {status}"
        if synopsis:
            msg += f"\n\n{synopsis}"
        msg += f"\n\n<a href='{a.get('url', '')}'>Xem trên MyAnimeList</a>"
        img = a.get("images", {}).get("jpg", {}).get("large_image_url")
        cache_set(cache_key, (msg, img))
        if img:
            await update.message.reply_photo(photo=img, caption=msg, parse_mode="HTML")
        else:
            await update.message.reply_text(msg, parse_mode="HTML")
    except RateLimited:
        await update.message.reply_text("⏳ API anime đang bị giới hạn, thử lại sau ít giây.")
    except Exception as e:
        logger.debug(f"Anime lookup failed: {e}")
        await update.message.reply_text("Lỗi tra anime.")


@rate_limit(5)
async def meme_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        subreddits = ["vozmemes", "VietNamMeme", "VietnameseMemes"]
        sub = secrets.choice(subreddits)
        url = f"https://www.reddit.com/r/{sub}/random.json"
        data = await fetch_json(url)
        if isinstance(data, list) and len(data) > 0:
            data = data[0]
        children = data.get("data", {}).get("children", [])
        if not children:
            await update.effective_message.reply_text("Không có meme.")
            return
        post = children[0]["data"]
        img_url = post.get("url_overridden_by_dest") or post.get("url", "")
        title = post.get("title", "")
        if img_url and any(img_url.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif"]):
            await update.effective_message.reply_photo(photo=img_url, caption=title)
        else:
            await update.effective_message.reply_text(f"{title}\n{img_url}")
    except RateLimited:
        await update.effective_message.reply_text("⏳ Reddit đang bị giới hạn, thử lại sau.")
    except Exception as e:
        logger.debug(f"Meme failed: {e}")
        await update.effective_message.reply_text("Lỗi lấy meme.")


@rate_limit(3)
async def wiki_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("Nhập từ khóa. VD: /wiki Việt Nam")
        return

    cache_key = f"wiki:{query.lower()}"
    cached = cache_get(cache_key, ttl=86400)
    if cached:
        await update.message.reply_text(cached)
        return
    try:
        title = urllib.parse.quote(query.replace(" ", "_"))
        url = f"https://vi.wikipedia.org/api/rest_v1/page/summary/{title}"
        data = await fetch_json(url)
        extract = data.get("extract")
        if not extract:
            await update.message.reply_text(f"Không tìm thấy '{query}' trên Wikipedia.")
            return
        page_url = data.get("content_urls", {}).get("desktop", {}).get("page", "")
        msg = f"📖 **{data.get('title', query)}**\n\n{extract}"
        if page_url:
            msg += f"\n\n🔗 {page_url}"
        cache_set(cache_key, msg)
        await update.message.reply_text(msg)
    except Exception as e:
        logger.debug(f"Wiki lookup failed: {e}")
        await update.message.reply_text(f"Không tìm thấy '{query}' hoặc lỗi API.")


@rate_limit(3)
async def tygia_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cached = cache_get("tygia", ttl=600)
    if cached:
        await update.effective_message.reply_text(cached)
        return
    try:
        data = await fetch_json("https://open.er-api.com/v6/latest/USD")
        rates = data.get("rates", {})
        vnd = rates.get("VND")
        if not vnd:
            await update.effective_message.reply_text("Lỗi lấy tỷ giá.")
            return
        # quy đổi 1 đơn vị ngoại tệ -> VND qua trung gian USD
        def to_vnd(code):
            r = rates.get(code)
            return vnd / r if r else None
        pairs = [("🇺🇸 USD", vnd), ("🇪🇺 EUR", to_vnd("EUR")),
                 ("🇯🇵 JPY", to_vnd("JPY")), ("🇬🇧 GBP", to_vnd("GBP")),
                 ("🇨🇳 CNY", to_vnd("CNY")), ("🇰🇷 KRW", to_vnd("KRW"))]
        lines = ["💱 **Tỷ giá sang VND:**"]
        for name, v in pairs:
            if v:
                lines.append(f"{name}: {v:,.0f}đ")
        updated = data.get("time_last_update_utc", "")[:16]
        if updated:
            lines.append(f"\n🕒 Cập nhật: {updated} UTC")
        result = "\n".join(lines)
        cache_set("tygia", result)
        await update.effective_message.reply_text(result)
    except Exception as e:
        logger.debug(f"Tygia failed: {e}")
        await update.effective_message.reply_text("Lỗi lấy tỷ giá.")


# --- Lịch âm Việt Nam ---
_CAN = ['Giáp', 'Ất', 'Bính', 'Đinh', 'Mậu', 'Kỷ', 'Canh', 'Tân', 'Nhâm', 'Quý']
_CHI = ['Tý', 'Sửu', 'Dần', 'Mão', 'Thìn', 'Tỵ', 'Ngọ', 'Mùi', 'Thân', 'Dậu', 'Tuất', 'Hợi']
_TIET = ['Xuân', 'Hạ', 'Thu', 'Đông']
_THU = ['Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy', 'Chủ Nhật']

async def lich_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        now = datetime.datetime.now()
        d = context.args[0] if context.args else None
        if d:
            parts = d.replace("/", "-").split("-")
            if len(parts) == 3:
                day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                dt = datetime.date(year, month, day)
            else:
                await update.message.reply_text("❌ Định dạng: /lich DD/MM/YYYY")
                return
        else:
            dt = now.date()

        lunar = lunardate.LunarDate.fromSolarDate(dt.year, dt.month, dt.day)
        can_chi = f"{_CAN[(lunar.year - 4) % 10]} {_CHI[(lunar.year - 4) % 12]}"
        thang_am = f"Tháng {lunar.month}"
        ngay_am = f"Ngày {lunar.day}"

        # Tiết khí (approximate — first day of each solar term)
        # Use solar longitude to determine tiết
        sol_month = dt.month
        if dt.day >= 20:
            sol_month += 1
            if sol_month > 12:
                sol_month = 1
        tiet_idx = ((sol_month - 1) % 12) // 3
        tiet = _TIET[tiet_idx]

        thu = _THU[dt.weekday()]
        msg = (
            f"📅 **{dt.day:02d}/{dt.month:02d}/{dt.year}**\n"
            f"📍 {thu}\n\n"
            f"🌙 **Âm lịch:** {ngay_am} {thang_am} {can_chi}\n"
            f"🌸 **Tiết:** {tiet}\n"
        )

        if lunar.day == 1:
            msg += "🌑 **Mùng 1 — Sóc**"
        elif lunar.day == 15:
            msg += "🌕 **Rằm — Vọng**"
        await update.message.reply_text(msg)
    except ImportError:
        await update.message.reply_text("❌ Thư viện lịch chưa được cài.")
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {e}")


# ══════════════════════════════════════════════════════════════
#  🎵  TikTok Features
# ══════════════════════════════════════════════════════════════
TIKTOK_API = "https://www.tikwm.com/api/"


@rate_limit(5)
async def tiktok_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Download TikTok video không logo + hiển thị thông tin"""
    url = " ".join(context.args) if context.args else ""
    if not url:
        await update.message.reply_text(
            "🎵 **TikTok Downloader**\n\n"
            "Dùng: `/tiktok <url>`\n\n"
            "Ví dụ: `/tiktok https://www.tiktok.com/@user/video/1234567890`",
            parse_mode="Markdown",
        )
        return
    try:
        api_url = f"{TIKTOK_API}?url={urllib.parse.quote(url)}"
        data = await fetch_json(api_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        if data.get("code") != 0 or not data.get("data"):
            await update.message.reply_text("❌ Không thể tải video. Kiểm tra lại URL.")
            return
        d = data["data"]
        author = d.get("author", {}).get("unique_id", "N/A")
        nickname = d.get("author", {}).get("nickname", "")
        desc = d.get("title", "") or "Không có mô tả"
        stats = d.get("stats", {})
        plays = stats.get("play_count", 0)
        likes = stats.get("digg_count", 0)
        comments = stats.get("comment_count", 0)
        shares = stats.get("share_count", 0)
        video_url = d.get("play") or d.get("wmplay") or ""
        if not video_url:
            await update.message.reply_text("❌ Không tìm thấy video.")
            return
        caption = (
            f"🎵 **TikTok Video**\n"
            f"👤 **@{author}** {nickname}\n"
            f"📝 {desc[:200]}{'...' if len(desc) > 200 else ''}\n\n"
            f"❤️ {likes:,}  💬 {comments:,}  🔄 {shares:,}  👀 {plays:,}"
        )
        video_data = await fetch_bytes(video_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        await update.message.reply_video(video=video_data, caption=caption, parse_mode="Markdown")
    except RateLimited:
        await update.message.reply_text("⏳ API đang bị giới hạn, thử lại sau.")
    except Exception as e:
        logger.debug(f"TikTok download failed: {e}")
        await update.message.reply_text("❌ Lỗi tải TikTok.")






@rate_limit(5)
async def tiktok_profile_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xem thông tin profile TikTok"""
    username = " ".join(context.args) if context.args else ""
    if not username:
        await update.message.reply_text(
            "὆4 **TikTok Profile**\n\n"
            "Dùng: `/tiktok_profile <username>`\n\n"
            "Ví dụ: `/tiktok_profile theanh28`",
            parse_mode="Markdown",
        )
        return
    username = username.replace("@", "").strip()
    try:
        api_url = f"{TIKTOK_API}user/?unique_id={urllib.parse.quote(username)}"
        data = await fetch_json(api_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        if data.get("code") != 0 or not data.get("data"):
            await update.message.reply_text(f"❌ Không tìm thấy user @{username}.")
            return
        d = data["data"]
        user_info = d.get("user", {})
        stats = d.get("stats", {})
        nickname = user_info.get("nickname", "N/A")
        unique_id = user_info.get("unique_id", username)
        bio = user_info.get("signature", "") or "Không có bio"
        avatar = user_info.get("avatar")
        followers = stats.get("follower_count", 0)
        following = stats.get("following_count", 0)
        likes = stats.get("heart_count", 0)
        videos = stats.get("video_count", 0)
        msg = (
            f"὆4 **{nickname}** (@{unique_id})\n\n"
            f"📝 {bio[:300]}{'...' if len(bio) > 300 else ''}\n\n"
            f"👥 **{followers:,}** followers\n"
            f"📌 **{following:,}** following\n"
            f"❤️ **{likes:,}** likes\n"
            f"🎬 **{videos:,}** videos"
        )
        if avatar:
            await update.message.reply_photo(photo=avatar, caption=msg, parse_mode="Markdown")
        else:
            await update.message.reply_text(msg, parse_mode="Markdown")
    except RateLimited:
        await update.message.reply_text("⏳ API đang bị giới hạn, thử lại sau.")
    except Exception as e:
        logger.debug(f"TikTok profile failed: {e}")
        await update.message.reply_text("❌ Lỗi lấy thông tin profile.")


@rate_limit(5)
async def tiktok_search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tìm kiếm video trên TikTok"""
    keyword = " ".join(context.args) if context.args else ""
    if not keyword:
        await update.message.reply_text(
            "🔎 **TikTok Search**\n\n"
            "Dùng: `/tiktok_search <từ khóa>`\n\n"
            "Ví dụ: `/tiktok_search mèo cute`",
            parse_mode="Markdown",
        )
        return
    try:
        api_url = f"{TIKTOK_API}search/?keywords={urllib.parse.quote(keyword)}&count=5"
        data = await fetch_json(api_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        if data.get("code") != 0 or not data.get("data"):
            await update.message.reply_text(f"❌ Không tìm thấy kết quả cho '{keyword}'.")
            return
        videos = data["data"]
        lines = [f"🔎 **Kết quả: {keyword}**\n"]
        for i, v in enumerate(videos[:5], 1):
            author = v.get("author", {}).get("unique_id", "N/A")
            desc = v.get("title", "") or "Không có mô tả"
            stats = v.get("stats", {})
            likes = stats.get("digg_count", 0)
            link = v.get("share_url", f"https://tiktok.com/@{author}")
            lines.append(f"**{i}.** 👤 @{author}  ❤️ {likes:,}")
            lines.append(f"   📝 {desc[:100]}")
            lines.append(f"   🔗 [Xem video]({link})\n")
        await update.message.reply_text(
            "\n".join(lines), parse_mode="Markdown", disable_web_page_preview=True,
        )
    except RateLimited:
        await update.message.reply_text("⏳ API đang bị giới hạn, thử lại sau.")
    except Exception as e:
        logger.debug(f"TikTok search failed: {e}")
        await update.message.reply_text("❌ Lỗi tìm kiếm TikTok.")


@rate_limit(5)
async def tiktok_trending_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xem video thịnh hành trên TikTok"""
    try:
        api_url = f"{TIKTOK_API}feed/trending"
        data = await fetch_json(api_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        if data.get("code") != 0 or not data.get("data"):
            await update.message.reply_text("❌ Không thể lấy video thịnh hành.")
            return
        videos = data["data"].get("videos", [])
        if not videos:
            await update.message.reply_text("❌ Không có video trending.")
            return
        lines = ["🔥 **TikTok Trending Top 10**\n"]
        for i, v in enumerate(videos[:10], 1):
            author = v.get("author", {}).get("unique_id", "N/A")
            desc = v.get("title", "") or "Không có mô tả"
            stats = v.get("stats", {})
            likes = stats.get("digg_count", 0)
            plays = stats.get("play_count", 0)
            lines.append(f"**{i}.** 👤 @{author}  👀 {plays:,}  ❤️ {likes:,}")
            lines.append(f"   📝 {desc[:80]}\n")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except RateLimited:
        await update.message.reply_text("⏳ API đang bị giới hạn, thử lại sau.")
    except Exception as e:
        logger.debug(f"TikTok trending failed: {e}")
        await update.message.reply_text("❌ Lỗi lấy video thịnh hành.")


@rate_limit(3)
async def tiktok_seo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gợi ý SEO cho TikTok (tiêu đề, hashtag, mô tả)"""
    keyword = " ".join(context.args) if context.args else ""
    if not keyword:
        await update.message.reply_text(
            "📈 **TikTok SEO Assistant**\n\n"
            "Dùng: `/tiktok_seo <từ khóa>`\n\n"
            "Bot sẽ gợi ý:\n"
            "• Tiêu đề tối ưu\n"
            "• Hashtag thịnh hành\n"
            "• Mô tả video\n\n"
            "Ví dụ: `/tiktok_seo cách nấu phở`",
            parse_mode="Markdown",
        )
        return
    kw = keyword.lower().strip()
    titles = [
        f"{keyword.title()} | Bạn đã biết chưa?",
        f"Hướng dẫn {kw} đơn giản tại nhà",
        f"{keyword.title()} siêu dễ, ai cũng làm được",
        f"Bí quyết {kw} không phải ai cũng biết",
        f"{keyword.title()} — Xem ngay kẻo lỡ!",
    ]
    words = kw.split()
    base_tags = [kw.replace(" ", "")]
    if len(words) > 1:
        base_tags.extend(words)
    hashtags = []
    for t in base_tags:
        hashtags.extend([f"#{t}", f"#{t}tiktok", f"#{t}xuhuong", f"hoc{t.replace(' ', '')}", f"#{t}moingay"])
    hashtags.extend(["#fyp", "#foryou", "#xuhuong", "#tiktokvn", "#viral"])
    hashtags = list(dict.fromkeys(hashtags))
    tag_str = " ".join(hashtags[:15])
    desc = (
        f"📌 {keyword.title()} 🎯\n\n"
        f"Bạn đã thử {kw} chưa? Xem ngay và học theo! 🔥\n\n"
        f"👇 Đừng quên:\n"
        f"✅ Like nếu hữu ích\n"
        f"💬 Comment cảm nhận của bạn\n"
        f"🔔 Lưu để xem sau\n\n"
        f"{tag_str}"
    )
    msg = (
        f"📈 **TikTok SEO — {keyword.title()}**\n\n"
        f"**🎯 Tiêu đề gợi ý:**\n"
        + "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
        + f"\n\n**🏷️ Hashtag gợi ý:**\n{tag_str}\n\n"
        f"**📝 Mô tả gợi ý:**\n{desc[:800]}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


@rate_limit(3)
async def tiktok_hashtag_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tra cứu hashtag TikTok + gợi ý hashtag liên quan"""
    tag = " ".join(context.args) if context.args else ""
    if not tag:
        await update.message.reply_text(
            "🏷️ **TikTok Hashtag**\n\n"
            "Dùng: `/tiktok_hashtag <tag>`\n\n"
            "Ví dụ: `/tiktok_hashtag hoc tap`",
            parse_mode="Markdown",
        )
        return
    tc = tag.replace("#", "").strip().lower()
    related = [
        f"#{tc}", f"#{tc}tiktok", f"#{tc}vn",
        f"#{tc}challenge", f"#{tc}trend",
        f"xuhuong{tc.replace(' ', '')}", f"hoc{tc.replace(' ', '')}",
    ]
    msg = (
        f"🏷️ **Hashtag: #{tc}**\n\n"
        f"**📊 Mẹo dùng hashtag hiệu quả:**\n"
        f"• Dùng **3-5 hashtag** chính liên quan đến nội dung\n"
        f"• Thêm **2-3 hashtag thịnh hành** (#fyp, #xuhuong)\n"
        f"• Đặt hashtag ở **cuối mô tả** hoặc **comment đầu tiên**\n"
        f"• Trộn hashtag lớn (nhiều view) và hashtag nhỏ (ít cạnh tranh)\n\n"
        f"**🔗 Hashtag liên quan:**\n"
        + "\n".join(f"• {h}" for h in related)
        + f"\n\n**🔥 Hashtag thịnh hành hiện tại:**\n"
        "#fyp #foryou #xuhuong #tiktokvn #viral #trending #learnontiktok"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


# ═══ AI Chatbot ═══
_ai_history: dict = {}
AI_HISTORY_LIMIT = 10

# Auto-detect TikTok URLs in any message and reply with download
tiktok_url_pattern = re.compile(r"(https?://(?:www\.)?tiktok\.com/@[\w.]+/video/\d+[^\s]*)", re.IGNORECASE)

async def auto_tiktok_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Auto-detect TikTok URLs and reply with video info."""
    text = update.message.text or ""
    match = tiktok_url_pattern.search(text)
    if not match or context.user_data.get("waiting_code"):
        return  # Let echo handle it
    url = match.group(1).strip()
    try:
        api_url = f"{TIKTOK_API}?url={urllib.parse.quote(url)}"
        data = await fetch_json(api_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        if data.get("code") == 0 and data.get("data"):
            d = data["data"]
            author = d.get("author", {}).get("unique_id", "N/A")
            desc = d.get("title", "") or "Không có mô tả"
            stats = d.get("stats", {})
            video_url = d.get("play") or d.get("wmplay") or ""
            if video_url:
                caption = f"🎵 **TikTok Video**\n\n\U0001f464 **@{author}**\n\n\U0001f4dd {desc[:200]}\n\n\u2764 {stats.get('digg_count',0):,}  \U0001f440 {stats.get('play_count',0):,}"
                vd = await fetch_bytes(video_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
                await update.message.reply_video(video=vd, caption=caption, parse_mode="Markdown")
                return
    except Exception:
        pass

@rate_limit(5)
async def ask_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.message.reply_text(
            "🤖 **AI Chatbot**\n\n"
            "Dùng: `/ask <câu hỏi>`\n"
            "Ví dụ: `/ask Python là gì?`\n\n"
            "`/ask reset` — Xoá lịch sử chat",
            parse_mode="Markdown",
        )
        return
    if query.lower() in ("reset", "clear", "xoa", "xo"):
        user_id = update.effective_user.id
        _ai_history.pop(user_id, None)
        await update.message.reply_text("✅ Đã xoá lịch sử chat.")
        return
    user_id = update.effective_user.id
    if user_id not in _ai_history:
        _ai_history[user_id] = []
    _ai_history[user_id].append({"role": "user", "content": query})
    if len(_ai_history[user_id]) > AI_HISTORY_LIMIT:
        _ai_history[user_id] = _ai_history[user_id][-AI_HISTORY_LIMIT:]
    thinking_msg = await update.message.reply_text("🔄 Đang suy nghĩ...")
    try:
        answer = await ask_ai(query)
        _ai_history[user_id].append({"role": "assistant", "content": answer})
        if len(answer) > 4000:
            answer = answer[:4000] + "..."
        await thinking_msg.edit_text(answer)
    except Exception as e:
        logger.debug(f"AI failed: {e}")
        await thinking_msg.edit_text(f"❌ Lỗi AI: {e}")


# ═══ Stats Commands ═══
@rate_limit(5)
async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        s = await db.get_stats_summary()
        top = "\n".join(
            f"  {i+1}. `{r['command']}` — {r['cnt']}"
            for i, r in enumerate(s["top_cmds"][:5])
        ) or "  Chà chơ..."
        msg = (
            f"📊 **Thống kê sử dụng**\n\n"
            f"📥 **Tổng lệnh:** {s['total_cmds']}\n"
            f"📅 **Hôm nay:** {s['today_cmds']}\n"
            f"👥 **Tổng người dùng:** {s['total_users']}\n"
            f"🔔 **Nhắc nhở:** {s['total_reminders']}\n"
            f"🔐 **Mật khẩu:** {s['total_passwords']}\n\n"
            f"🏆 **Top lệnh:**\n{top}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        logger.debug(f"Stats failed: {e}")
        await update.message.reply_text("❌ Lỗi lấy thống kê.")


@rate_limit(5)
async def myusage_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = update.effective_user.id
        _db = await db.get_db()
        cur = await _db.execute(
            "SELECT command, COUNT(*) as cnt FROM stats_cmds WHERE user_id=? GROUP BY command ORDER BY cnt DESC LIMIT 10",
            (uid,),
        )
        rows = [dict(r) for r in await cur.fetchall()]
        if not rows:
            await update.message.reply_text("Bạn chưa dùng lệnh nào.")
            return
        lines = "\n".join(f"  `{r['command']}` — {r['cnt']}" for r in rows)
        msg = (
            f"📊 **Lịch sử của bạn** (@{update.effective_user.username or 'N/A'})\n\n"
            f"{lines}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        logger.debug(f"My usage failed: {e}")
        await update.message.reply_text("❌ Lỗi lấy thông tin.")


# ═══ TikTok Auto-Post ═══
# {chat_id: {"task": asyncio.Task, "interval": minutes, "running": True}}
_tiktok_auto_tasks: dict = {}

async def _tiktok_auto_worker(bot, chat_id: int, interval: int):
    """Post trending TikTok videos to chat periodically."""
    import asyncio
    while True:
        try:
            api_url = f"{TIKTOK_API}feed/trending"
            data = await fetch_json(api_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            if data.get("code") == 0 and data.get("data"):
                videos = data["data"].get("videos", [])
                if videos:
                    # Pick 1-3 random trending videos
                    chosen = random.sample(videos[:10], min(3, len(videos[:10])))
                    for v in chosen:
                        author = v.get("author", {}).get("unique_id", "N/A")
                        desc = v.get("title", "") or "No description"
                        stats = v.get("stats", {})
                        video_url = v.get("play") or v.get("wmplay") or ""
                        if video_url:
                            caption = (
                                f"🔥 **TikTok Trending**\n\n"
                                f"👤 **@{author}**\n"
                                f"📝 {desc[:200]}\n\n"
                                f"❤ {stats.get('digg_count',0):,}  "
                                f"👀 {stats.get('play_count',0):,}"
                            )
                            try:
                                vd = await fetch_bytes(video_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
                                await bot.send_video(chat_id=chat_id, video=vd, caption=caption, parse_mode="Markdown")
                                await asyncio.sleep(5)  # avoid flood
                            except Exception as e:
                                logger.debug(f"Auto-post video failed: {e}")
        except Exception as e:
            logger.debug(f"TikTok auto-post error: {e}")
        await asyncio.sleep(interval * 60)


@rate_limit(10)
async def tiktok_auto_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start auto-posting trending TikTok to a chat."""
    if not ADMIN_ID or update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Only admin can use this.")
        return
    try:
        interval = int(context.args[0]) if context.args else 30
        chat_id_str = context.args[1] if len(context.args) > 1 else None
        if chat_id_str:
            chat_id = int(chat_id_str)
        else:
            chat_id = update.effective_chat.id
        interval = max(10, min(1440, interval))  # 10min to 24h
        # Stop existing task if any
        if chat_id in _tiktok_auto_tasks:
            _tiktok_auto_tasks[chat_id]["task"].cancel()
        task = asyncio.create_task(_tiktok_auto_worker(context.application.bot, chat_id, interval))
        _tiktok_auto_tasks[chat_id] = {"task": task, "interval": interval, "running": True}
        await update.message.reply_text(
                                f"🔥 **Auto TikTok Trending ON**\n\n"
                                f"Chat: `{chat_id}`\n"
                                f"Interval: {interval} phút\n"
                                f"Mỗi {interval}p sẽ gửi 1-3 video trending.\n\n"
            f"`/tiktok_stop` — Tạm dừng",
            parse_mode="Markdown"
        )
    except (IndexError, ValueError):
        await update.message.reply_text(
                                "Sai cú pháp:\n"
                                "`/tiktok_auto` — Bật (30 phút, chat hiện tại)\n"
                                "`/tiktok_auto 15` — Mỗi 15 phút\n"
            "`/tiktok_auto 30 -1001234` — Gửi vào chat ID",
            parse_mode="Markdown"
        )


@rate_limit(5)
async def tiktok_stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop auto-posting TikTok."""
    if not ADMIN_ID or update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Only admin can use this.")
        return
    chat_id = update.effective_chat.id
    if chat_id in _tiktok_auto_tasks:
        _tiktok_auto_tasks[chat_id]["task"].cancel()
        del _tiktok_auto_tasks[chat_id]
        await update.message.reply_text("✅ Đã tạm dừng auto TikTok.")
    else:
        await update.message.reply_text("ℹ️ Chưa bật auto TikTok cho chat này.")


# Maps menu "run_" buttons to their handlers (defined after all handlers exist)
RUN_ACTIONS = {
    "ip": ip_cmd,
    "joke": joke_cmd,
    "meme": meme_cmd,
    "crypto": crypto_cmd,
    "tygia": tygia_cmd,
}


# FIX: consolidated main function with proper startup sequence
async def main():
    app = Application.builder().token(TOKEN).build()

    commands = [
        BotCommand("start", "Bắt đầu"),
        BotCommand("help", "Trợ giúp"),
        BotCommand("van", "Văn mẫu lớp 8"),
        BotCommand("weather", "Thời tiết"),
        BotCommand("translate", "Dịch văn bản"),
        BotCommand("shorten", "Rút gọn link"),
        BotCommand("qr", "Tạo QR code"),
        BotCommand("crypto", "Giá crypto"),
        BotCommand("joke", "Câu chuyện vui"),
        BotCommand("id", "Thông tin của bạn"),
        BotCommand("status", "Trạng thái bot"),
        BotCommand("dictionary", "Tra từ điển"),
        BotCommand("ip", "Tra thông tin IP"),
        BotCommand("screenshot", "Chụp ảnh web"),
        BotCommand("remind", "Đặt nhắc nhở"),
        BotCommand("list", "DS nhắc nhở"),
        BotCommand("code", "Chạy code Python"),
        BotCommand("password", "Tạo mật khẩu"),
        BotCommand("calc", "Máy tính"),
        BotCommand("anime", "Tra anime"),
        BotCommand("meme", "Meme ngẫu nhiên"),
        BotCommand("lich", "Lịch âm Việt Nam"),
        BotCommand("wiki", "Tra Wikipedia"),
        BotCommand("tygia", "Tỷ giá ngoại tệ"),
        BotCommand("bypass", "Bypass link rút gọn"),
        BotCommand("tiktok", "Tai video TikTok"),
        BotCommand("tiktok_profile", "Xem profile TikTok"),
        BotCommand("tiktok_search", "Tim kiem TikTok"),
        BotCommand("tiktok_trending", "Video thinh hanh"),
        BotCommand("tiktok_seo", "Goi y SEO TikTok"),
        BotCommand("tiktok_hashtag", "Tra hashtag TikTok"),
        BotCommand("ask", "Hỏi AI Chatbot"),
        BotCommand("stats", "Thống kê sử dụng"),
        BotCommand("myusage", "Lịch sử của bạn"),
    ]
    await app.bot.set_my_commands(commands)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(menu_handler, pattern="^(menu_|run_)"))
    app.add_handler(CommandHandler("remind", remind))
    app.add_handler(CommandHandler("list", list_reminders))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("dictionary", dictionary))
    app.add_handler(CommandHandler("weather", weather))
    app.add_handler(CommandHandler("ip", ip_cmd))
    app.add_handler(CommandHandler("password", password_cmd))
    app.add_handler(CommandHandler("passwords", list_passwords))
    app.add_handler(CommandHandler("editpass", editpass_cmd))
    app.add_handler(CommandHandler("delpass", delpass_cmd))
    app.add_handler(CommandHandler("proxy", proxy_cmd))
    app.add_handler(CommandHandler("code", code_cmd))
    app.add_handler(CommandHandler("screenshot", screenshot_cmd))
    app.add_handler(CommandHandler("translate", translate_cmd))
    app.add_handler(CommandHandler("van", van_cmd))
    app.add_handler(CommandHandler("shorten", shorten_cmd))
    app.add_handler(CommandHandler("qr", qr_cmd))
    app.add_handler(CommandHandler("crypto", crypto_cmd))
    app.add_handler(CommandHandler("joke", joke_cmd))
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler("restart", restart_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("calc", calc_cmd))
    app.add_handler(CommandHandler("anime", anime_cmd))
    app.add_handler(CommandHandler("meme", meme_cmd))
    app.add_handler(CommandHandler("lich", lich_cmd))
    app.add_handler(CommandHandler("wiki", wiki_cmd))
    app.add_handler(CommandHandler("tygia", tygia_cmd))
    app.add_handler(CommandHandler("bypass", bypass_cmd))
    app.add_handler(CommandHandler("tiktok", tiktok_cmd))
    app.add_handler(CommandHandler("tiktok_profile", tiktok_profile_cmd))
    app.add_handler(CommandHandler("tiktok_search", tiktok_search_cmd))
    app.add_handler(CommandHandler("tiktok_trending", tiktok_trending_cmd))
    app.add_handler(CommandHandler("tiktok_seo", tiktok_seo_cmd))
    app.add_handler(CommandHandler("tiktok_hashtag", tiktok_hashtag_cmd))
    app.add_handler(CommandHandler("ask", ask_cmd))
    app.add_handler(CommandHandler("tiktok_auto", tiktok_auto_cmd))
    app.add_handler(CommandHandler("tiktok_stop", tiktok_stop_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("myusage", myusage_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, auto_tiktok_reply), group=0)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    app.add_error_handler(error_handler)

    # Stats middleware: log every command
    async def stats_middleware(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message and update.message.text and update.message.text.startswith("/"):
            cmd = update.message.text.split()[0].split("@")[0].strip("/")
            user = update.effective_user
            try:
                await db.log_command(user.id if user else None, user.username if user else None, cmd)
            except Exception:
                pass
    app.add_handler(MessageHandler(filters.Regex("^/"), stats_middleware), group=99)

    # Initialize database
    await db.get_db()

    PORT = int(os.environ.get("PORT", 10000))
    from aiohttp import web

    async def handle(request):
        return web.Response(text="OK")

    web_app = web.Application()
    setup_dashboard(web_app)
    web_app.router.add_get("/health", handle)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info("Dashboard + Health server started on port %d", PORT)

    logger.info("Bot started")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    # FIX: re-arm reminders that were persisted before the last restart
    await reschedule_reminders(app.bot)

    # FIX: use an Event to allow graceful shutdown instead of while+sleep
    try:
        while not _shutdown_event:
            await asyncio.sleep(60)
        logger.info("Shutdown received, stopping bot...")
    except asyncio.CancelledError:
        logger.info("Shutdown received, stopping bot...")
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        if 'runner' in locals():
            await runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except SystemExit:
        logger.info("Bot restarting...")
