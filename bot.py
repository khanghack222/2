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

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    force=True,
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    sys.exit("FATAL: BOT_TOKEN environment variable is required")

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
PROXY_LIST = []

# Thread-safety locks for shared mutable state
_reminders_lock = asyncio.Lock()
_passwords_lock = asyncio.Lock()
_cache_lock = asyncio.Lock()
_task_list: list[asyncio.Task] = []

# ═══════════════════════════════════════════════════════════════
#  🌐 Multi-language (EN/VI)
# ═══════════════════════════════════════════════════════════════
_user_lang = {}  # {user_id: "vi" | "en"} — in-memory cache, backed by DB

STRINGS = {
    "vi": {
        "rate_limit": "⏳ Chậm thôi nào! Thử lại sau {s}s.",
        "no_args_weather": "🌤 `/weather hanoi` — Thời tiết Hà Nội\n🌤 `/weather da nang` — Đà Nẵng",
        "city_not_found": "❌ Không tìm thấy '{city}'. Thử /weather hanoi",
        "weather_header": "🌤 **Thời tiết {place}:**",
        "weather_humidity": "💧 Độ ẩm {val}%",
        "weather_wind": "💨 Gió {val} km/h",
        "api_limited": "⏳ API đang bị giới hạn, thử lại sau.",
        "error_generic": "❌ Lỗi: {e}",
        "not_found": "Không tìm thấy '{q}'.",
        "help_title": "━━━ **Ví dụ sử dụng** ━━━",
        "stock_title": "📈 **Giá cổ phiếu: {symbol}**",
        "stock_price": "💰 Giá: **${price}**",
        "stock_change": "📊 Thay đổi: {arrow} {change}%",
        "stock_volume": "📦 Khối lượng: {vol}",
        "stock_market": "🏢 Sàn: {market}",
        "stock_no_args": "Dùng: `/stock FPT` hoặc `/stock VNM.VN`\n\nCổ phiếu VN thêm `.VN`: FPT.VN, VNM.VN, VCB.VN",
        "yt_title": "🎵 **YouTube Downloader**",
        "yt_processing": "⏳ Đang tải...",
        "yt_sending": "📤 Đang gửi...",
        "yt_no_url": "Nhập URL YouTube. VD: `/yt https://youtube.com/watch?v=...`",
        "yt_invalid": "❌ URL không hợp lệ. Dùng: `/yt <url>`",
        "yt_import_error": "❌ Thiếu yt-dlp. pip install yt-dlp",
        "yt_success": "🎵 {title} ({duration})",
        "lang_changed": "✅ Ngôn ngữ đã đổi sang: **Tiếng Việt**",
    },
    "en": {
        "rate_limit": "⏳ Slow down! Try again in {s}s.",
        "no_args_weather": "🌤 `/weather hanoi` — Weather in Hanoi\n🌤 `/weather new york` — Weather in New York",
        "city_not_found": "❌ City '{city}' not found. Try /weather hanoi",
        "weather_header": "🌤 **Weather in {place}:**",
        "weather_humidity": "💧 Humidity {val}%",
        "weather_wind": "💨 Wind {val} km/h",
        "api_limited": "⏳ API rate limited, try again later.",
        "error_generic": "❌ Error: {e}",
        "not_found": "'{q}' not found.",
        "help_title": "━━━ **Usage Examples** ━━━",
        "stock_title": "📈 **Stock Price: {symbol}**",
        "stock_price": "💰 Price: **${price}**",
        "stock_change": "📊 Change: {arrow} {change}%",
        "stock_volume": "📦 Volume: {vol}",
        "stock_market": "🏢 Exchange: {market}",
        "stock_no_args": "Usage: `/stock AAPL` or `/stock FPT.VN`\n\nVietnamese stocks add `.VN`: FPT.VN, VNM.VN, VCB.VN",
        "yt_title": "🎵 **YouTube Downloader**",
        "yt_processing": "⏳ Downloading...",
        "yt_sending": "📤 Sending...",
        "yt_no_url": "Enter a YouTube URL. Usage: `/yt https://youtube.com/watch?v=...`",
        "yt_invalid": "❌ Invalid URL. Usage: `/yt <url>`",
        "yt_import_error": "❌ yt-dlp not installed. pip install yt-dlp",
        "yt_success": "🎵 {title} ({duration})",
        "lang_changed": "✅ Language changed to: **English**",
    },
}


def t(key: str, user_id=None, **kwargs) -> str:
    lang = get_user_lang(user_id) if user_id else "vi"
    s = STRINGS.get(lang, STRINGS["vi"]).get(key)
    if s is None:
        s = STRINGS["vi"].get(key, key)
    return s.format(**kwargs) if kwargs else s


def get_user_lang(user_id) -> str:
    if user_id and user_id in _user_lang:
        return _user_lang[user_id]
    return "vi"



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
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        raise


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
    tmp = PASSWORDS_ENC_FILE + ".tmp"
    try:
        token = _get_fernet().encrypt(json.dumps(data, ensure_ascii=False).encode("utf-8"))
        with open(tmp, "wb") as f:
            f.write(token)
        os.replace(tmp, PASSWORDS_ENC_FILE)
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        raise


def load_passwords():
    if os.path.exists(PASSWORDS_FILE) and not os.path.exists(PASSWORDS_ENC_FILE):
        legacy = safe_json_load(PASSWORDS_FILE, {})
        if legacy:
            try:
                # Atomic migration: write new first, delete old only if new succeeds
                save_passwords(legacy)
                try:
                    os.remove(PASSWORDS_FILE)
                except OSError:
                    pass
                logger.info("Migrated plaintext passwords -> encrypted store")
            except Exception as e:
                logger.warning("Password migration failed: %s", e)
        return legacy
    if not os.path.exists(PASSWORDS_ENC_FILE):
        return {}
    try:
        with open(PASSWORDS_ENC_FILE, "rb") as f:
            token = f.read()
        if not token:
            return {}
        try:
            return json.loads(_get_fernet().decrypt(token).decode("utf-8"))
        except Exception:
            logger.warning("Password decryption failed, file corrupted. Trying backup...")
            # Try .bak version
            bak = PASSWORDS_ENC_FILE + ".bak"
            if os.path.exists(bak):
                with open(bak, "rb") as f:
                    token = f.read()
                if token:
                    return json.loads(_get_fernet().decrypt(token).decode("utf-8"))
            return {}
    except Exception as e:
        logger.warning("Cannot load passwords: %s", e)
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


# --- Simple TTL cache with LRU eviction to cut down on repeat API calls ---
_cache = {}
_cache_maxsize = 500
_cache_access_order = []
_shutdown_event = False


def cache_get(key, ttl):
    entry = _cache.get(key)
    if entry is not None and (time.monotonic() - entry[0]) < ttl:
        if key in _cache_access_order:
            _cache_access_order.remove(key)
        _cache_access_order.append(key)
        return entry[1]
    if entry is not None:
        _cache.pop(key, None)
        if key in _cache_access_order:
            _cache_access_order.remove(key)
    return None


def cache_set(key, value):
    if key in _cache_access_order:
        _cache_access_order.remove(key)
    while len(_cache) >= _cache_maxsize and _cache_access_order:
        oldest = _cache_access_order.pop(0)
        _cache.pop(oldest, None)
    _cache[key] = (time.monotonic(), value)
    _cache_access_order.append(key)


# --- Per-user rate limiting (anti-spam) with periodic cleanup ---
_last_call = {}
_RATE_LIMIT_CLEANUP_INTERVAL = 300


def _cleanup_rate_limits():
    now = time.monotonic()
    stale = [k for k, v in _last_call.items() if now - v > 3600]
    for k in stale:
        del _last_call[k]
    flood_stale = []
    for uid, timestamps in _flood_count.items():
        if timestamps:
            latest = max(timestamps)
            if now - latest > 3600:
                flood_stale.append(uid)
    for k in flood_stale:
        del _flood_count[k]


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
                msg = update.effective_message
                if msg:
                    await msg.reply_text(
                        t("rate_limit", user.id, s=int(seconds - elapsed) + 1)
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
        "`/tygia`     — Tỷ giá ngoại tệ → VND\n"
        "`/stock`     — Giá cổ phiếu real-time"),
    "lich": ("📅  Lịch & Nhắc nhở",
        "`/lich`      — Lịch âm (hôm nay / ngày)\n"
        "`/remind`    — Đặt nhắc nhở\n"
        "`/list`      — DS nhắc nhở\n"
        "`/cancel`    — Huỷ nhắc nhở"),
    "ai": ("🤖  AI Chatbot",
        "`/ask <câu hỏi>`    — Hỏi AI ChatGPT/Claude\n"
        "`/ask reset`        — Xoá lịch sử chat\n"
        "`/clear`            — Xoá lịch sử chat\n"
        "`/clear all`        — Xoá toàn bộ dữ liệu"),
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
    "nhac": ("🎵  Nhạc & Tin tức",
        "`/yt`       — Tải video YouTube\n"
        "`/music`    — Tải nhạc YouTube (audio)\n"
        "`/news`     — Tin tức mới nhất"),
    "khac": ("ℹ️  Hệ thống",
        "`/id`        — Thông tin Telegram của bạn\n"
        "`/status`    — Trạng thái & thời gian hoạt động\n"
        "`/lang`      — Đổi ngôn ngữ (EN/VI)\n"
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


# Commands: auto-run (no-arg) + suggestions (need input)
SECTION_RUN = {
    "tienich": {
        "auto": [("🌍 IP của tôi", "ip")],
        "suggestions": [
            ("🌤 Thời tiết Hà Nội", "weather", "hanoi"),
            ("🌤 Thời tiết Đà Nẵng", "weather", "da nang"),
            ("🌤 Thời tiết TP.HCM", "weather", "thanh pho ho chi minh"),
            ("🔤 Dịch 'hello world'", "translate", "hello world"),
            ("🔤 Dịch 'good morning'", "translate", "good morning"),
            ("🔗 Rút gọn URL", "shorten", "https://example.com"),
            ("🔗 Rút gọn YouTube", "shorten", "https://youtube.com/watch?v=123"),
            ("📷 Chụp ảnh Google", "screenshot", "https://google.com"),
        ],
    },
    "congcu": {
        "auto": [],
        "suggestions": [
            ("💻 Code Python", "code", "py"),
            ("💻 Code JavaScript", "code", "js"),
            ("💻 Code HTML", "code", "html"),
            ("🔐 Pass 16 ký tự", "password", "16"),
            ("🔐 Pass 20 ký tự", "password", "20"),
            ("🔐 Pass mặc định", "password", ""),
            ("🔗 Bypass link", "bypass", "https://shorturl.at/abc123"),
        ],
    },
    "giaitri": {
        "auto": [("🎭 Joke", "joke"), ("😂 Meme", "meme")],
        "suggestions": [
            ("🔎 Anime Naruto", "anime", "naruto"),
            ("🔎 Anime One Piece", "anime", "one piece"),
            ("🔎 Anime Dragon Ball", "anime", "dragon ball"),
            ("🔎 Anime Attack on Titan", "anime", "attack on titan"),
        ],
    },
    "hoctap": {
        "auto": [],
        "suggestions": [
            ("📚 Từ điển 'hello'", "dictionary", "hello"),
            ("📚 Từ điển 'beautiful'", "dictionary", "beautiful"),
            ("📚 Từ điển 'freedom'", "dictionary", "freedom"),
            ("📖 Wikipedia 'Vietnam'", "wiki", "Vietnam"),
            ("📖 Wikipedia 'Python'", "wiki", "Python"),
            ("📖 Văn mẫu lớp 8", "van", ""),
        ],
    },
    "taichinh": {
        "auto": [("💰 Crypto", "crypto"), ("💱 Tỷ giá", "tygia")],
        "suggestions": [
            ("📈 FPT.VN", "stock", "FPT.VN"),
            ("📈 VNM.VN", "stock", "VNM.VN"),
            ("📈 VCB.VN", "stock", "VCB.VN"),
            ("📈 TCB.VN", "stock", "TCB.VN"),
            ("📈 AAPL", "stock", "AAPL"),
            ("📈 TSLA", "stock", "TSLA"),
            ("📈 NVDA", "stock", "NVDA"),
        ],
    },
    "lich": {
        "auto": [("📅 Lịch hôm nay", "lich")],
        "suggestions": [
            ("📅 Lịch 30/4/2026", "lich", "30/4/2026"),
            ("📅 Lịch 2/9/2026", "lich", "2/9/2026"),
            ("📅 Lịch Tết 2027", "lich", "1/1/2027"),
            ("⏰ Nhắc 60 giây", "remind", "60 Mua sữa"),
            ("⏰ Nhắc 5 phút", "remind", "300 Học bài"),
            ("⏰ Nhắc 1 tiếng", "remind", "3600 Họp nhóm"),
        ],
    },
    "ai": {
        "auto": [],
        "suggestions": [
            ("🤖 Python là gì?", "ask", "Python là gì?"),
            ("🤖 ChatGPT hoạt động?", "ask", "ChatGPT hoạt động ra sao?"),
            ("🤖 Mẹo học tiếng Anh", "ask", "Mẹo học tiếng Anh hiệu quả"),
        ],
    },
    "tiktok": {
        "auto": [("🔥 Trending", "tiktok_trending")],
        "suggestions": [
            ("🔎 Tìm 'cooking'", "tiktok_search", "cooking"),
            ("🔎 Tìm 'dance'", "tiktok_search", "dance"),
            ("👤 Profile @username", "tiktok_profile", "username"),
            ("📈 SEO 'nấu ăn'", "tiktok_seo", "nấu ăn"),
            ("📈 SEO 'makeup'", "tiktok_seo", "makeup"),
            ("🏷️ Tag #fyp", "tiktok_hashtag", "fyp"),
            ("🏷️ Tag #dance", "tiktok_hashtag", "dance"),
        ],
    },
    "stats": {
        "auto": [("📊 Thống kê", "stats"), ("📜 Lịch sử", "myusage")],
        "suggestions": [],
    },
    "nhac": {
        "auto": [("📰 Tin tức", "news")],
        "suggestions": [
            ("🎵 Tải nhạc YouTube", "music", "https://youtube.com/watch?v=123"),
            ("📰 Tin sức khỏe", "news", "sức khỏe"),
            ("📰 Tin thể thao", "news", "thể thao"),
        ],
    },
    "khac": {
        "auto": [("🌍 IP", "ip"), ("📡 Trạng thái", "status")],
        "suggestions": [],
    },
}


def section_keyboard(key=None):
    rows = []
    section_data = SECTION_RUN.get(key, {})
    if isinstance(section_data, dict):
        auto_cmds = section_data.get("auto", [])
        suggestions = section_data.get("suggestions", [])
    else:
        auto_cmds = section_data
        suggestions = []

    # Auto-run buttons (no-arg commands)
    run_btns = [
        InlineKeyboardButton(label, callback_data=f"run_{cmd}")
        for label, cmd in auto_cmds
    ]
    for i in range(0, len(run_btns), 2):
        rows.append(run_btns[i:i + 2])

    # Suggestion buttons (user types input → send)
    sug_btns = [
        InlineKeyboardButton(label, callback_data=f"suggest_{cmd}|{arg}")
        for label, cmd, arg in suggestions
    ]
    for i in range(0, len(sug_btns), 2):
        rows.append(sug_btns[i:i + 2])

    if not rows:
        rows.append([InlineKeyboardButton("ℹ️ Dùng /help", callback_data="noop")])
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
    if data.startswith("run_") and "|" not in data:
        handler = RUN_ACTIONS.get(data.replace("run_", ""))
        if handler:
            await handler(update, context)
        return

    # Show suggestion with buttons
    if data.startswith("suggest_"):
        payload = data[len("suggest_"):]
        sep = payload.find("|")
        if sep == -1:
            return
        cmd = payload[:sep]
        arg = payload[sep + 1:]
        cmd_text = f"/{cmd} {arg}".strip()
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("\U0001f680 G\u1eedi ngay", callback_data=f"run_{cmd}|{arg}"),
            ],
            [InlineKeyboardButton("\u2b05\ufe0f Quay l\u1ea1i", callback_data="menu_home")],
        ])
        await q.edit_message_text(
            f"\U0001f4dd **Nh\u1eadp l\u1ec7nh:**\n`{cmd_text}`\n\n"
            f"\U0001f449 **G\u1eedi ngay:** Nh\u1ea5n n\u00fat \U0001f680\n"
            f"\U0001f449 **T\u1eeb g\u1eedi:** Copy c\u00e1ch g\u1eedi v\u00e0o \u00f4 chat, s\u1eeda n\u1ed9i dung r\u1ed3i g\u1eedi",
            reply_markup=kb,
            parse_mode="Markdown",
        )
        return    # Gửi ngay: run command with args
    if data.startswith("run_") and "|" in data:
        payload = data[len("run_"):]
        sep = payload.find("|")
        cmd = payload[:sep]
        arg = payload[sep + 1:]
        handler = RUN_ACTIONS.get(cmd)
        if handler:
            context.args = arg.split() if arg.strip() else []
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
        "  `/tiktok_hashtag <tag>`      — Tra hashtag\n\n"
            "**Nhạc & Tin tức**\n"
            "  `/music <url>`               — Tải nhạc YouTube\n"
            "  `/news`                      — Tin tức mới nhất\n\n"
            "**Quản lý nhóm (Admin)**\n"
            "  `/kick`  `/ban`  `/unban`    — Quản lý thành viên\n"
            "  `/mute`  `/unmute`           — Mute/Unmute"
    )
    await update.message.reply_text(msg)


async def _fire_reminder(bot, user_id, rid, content, due_ts):
    try:
        await asyncio.sleep(max(0, due_ts - time.time()))
        await bot.send_message(chat_id=int(user_id), text=f"⏰ Nhắc nhở #{rid}: {content}")
    except Exception as e:
        logger.warning(f"Failed to send reminder #{rid}: {e}")
    finally:
        async with _reminders_lock:
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
        if seconds < 5:
            await update.message.reply_text("Tối thiểu 5 giây.")
            return
        if seconds > 86400 * 30:
            await update.message.reply_text("Tối đa 30 ngày.")
            return

        user_id = str(update.effective_user.id)
        async with _reminders_lock:
            if user_id not in reminders:
                reminders[user_id] = []
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
        async with _reminders_lock:
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
    async with _passwords_lock:
        if user_id not in passwords:
            passwords[user_id] = []
        idx = max((p["id"] for p in passwords[user_id]), default=0) + 1
        label = " ".join(context.args[1:]) if len(context.args) > 1 else f"pass{idx}"
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
        async with _passwords_lock:
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
    if is_flood(update.effective_user.id):
        return
    text = update.message.text
    if text.startswith("nhắc"):
        parts = text.split(" ", 1)
        if len(parts) > 1:
            await update.message.reply_text(f" Dùng lệnh: /remind 60 {parts[1]}")
    elif "hello" in text.lower():
        await update.message.reply_text("Hello! Bạn cần gì?")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.exception(f"Update {update.update_id} caused error", exc_info=context.error)
    cmd = "unknown"
    if update and update.message and update.message.text and update.message.text.startswith("/"):
        cmd = update.message.text.split()[0].split("@")[0].strip("/")
    try:
        await db.log_error(cmd, str(context.error)[:500])
    except Exception:
        pass


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
        expr_normalized = re.sub(r'(\d)x(\d)', r'\1*\2', expr, flags=re.IGNORECASE)
        expr_normalized = expr_normalized.replace(":", "/")
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

# Auto-detect TikTok URLs in any message and reply with download
tiktok_url_pattern = re.compile(r"(https?://(?:www\.)?tiktok\.com/@[\w.]+/video/\d+[^\s]*)", re.IGNORECASE)

async def auto_tiktok_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Auto-detect TikTok URLs and reply with video info."""
    text = update.message.text or ""
    match = tiktok_url_pattern.search(text)
    if not match or context.user_data.get("waiting_code"):
        return  # Let echo handle it
    if is_flood(update.effective_user.id):
        return
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
                caption = (
                    f"🎵 **TikTok Video**\n\n"
                    f"👤 **@{author}**\n\n"
                    f"📝 {desc[:200]}\n\n"
                    f"❤️ {stats.get('digg_count',0):,}  "
                    f"👀 {stats.get('play_count',0):,}"
                )
                vd = await fetch_bytes(video_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
                await update.message.reply_video(video=vd, caption=caption, parse_mode="Markdown")
                return
    except Exception as e:
        logger.debug(f"Auto TikTok failed: {e}")

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
        await db.clear_ai_history(user_id)
        await update.message.reply_text("✅ Đã xoá lịch sử chat.")
        return
    user_id = update.effective_user.id
    history = await db.load_ai_history(user_id)
    history.append({"role": "user", "content": query})
    thinking_msg = await update.message.reply_text("🔄 Đang suy nghĩ...")
    try:
        answer = await ask_ai(query, history)
        history.append({"role": "assistant", "content": answer})
        if len(answer) > 4000:
            answer = answer[:4000] + "..."
        await db.save_ai_history(user_id, history)
        await thinking_msg.edit_text(answer)
    except Exception as e:
        logger.debug(f"AI failed: {e}")
        await thinking_msg.edit_text(f"❌ Lỗi AI: {e}")


@rate_limit(3)
async def clear_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear AI chat history or all user data."""
    user_id = update.effective_user.id
    arg = " ".join(context.args).lower() if context.args else ""
    if arg == "all":
        await db.clear_ai_history(user_id)
        if user_id in passwords:
            passwords[user_id] = []
            save_passwords(passwords)
        if str(user_id) in reminders:
            reminders[str(user_id)] = []
            save_json(DATA_FILE, reminders)
        await update.message.reply_text("✅ Đã xoá tất cả dữ liệu (chat, mật khẩu, nhắc nhở).")
    else:
        await db.clear_ai_history(user_id)
        await update.message.reply_text("✅ Đã xoá lịch sử chat AI. Dùng `/clear all` để xoá toàn bộ.", parse_mode="Markdown")


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



# --- Flood protection ---
_flood_count = {}  # {user_id: [timestamps]}
FLOOD_LIMIT = 8
FLOOD_WINDOW = 15


def is_flood(user_id: int) -> bool:
    now = time.monotonic()
    if user_id not in _flood_count:
        _flood_count[user_id] = []
    _flood_count[user_id] = [ts for ts in _flood_count[user_id] if now - ts < FLOOD_WINDOW]
    if len(_flood_count[user_id]) >= FLOOD_LIMIT:
        return True
    _flood_count[user_id].append(now)
    return False


@rate_limit(10)
async def news_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import xml.etree.ElementTree as ET
    feeds = [
        ("https://vnexpress.net/rss/suc-khoe.rss", "Sức khỏe"),
        ("https://vnexpress.net/rss/doi-song.rss", "Đời sống"),
        ("https://vnexpress.net/rss/khoa-hoc.rss", "Khoa học"),
        ("https://vnexpress.net/rss/the-thao.rss", "Thể thao"),
        ("https://vnexpress.net/rss/tin-moi.rss", "Tin mới"),
    ]
    sel = None
    src = " ".join(context.args).lower() if context.args else ""
    for url, name in feeds:
        if src and src in name.lower():
            sel = (url, name)
            break
    if not sel:
        import random as _r
        sel = _r.choice(feeds)
    url, name = sel
    try:
        xml_text = await fetch_text(url, timeout=15)
        root = ET.fromstring(xml_text)
        items = root.findall(".//item")[:8]
        if not items:
            return await update.message.reply_text("Không có tin.")
        lines = [f"📰 **{name}**"]
        for item in items:
            t = item.findtext("title", "Không tiêu đề")
            l = item.findtext("link", "")
            if t and l:
                lines.append(f"• [{t}]({l})")
        await update.message.reply_text("\n".join(lines), disable_web_page_preview=True)
    except ET.ParseError as e:
        logger.debug(f"News XML parse error: {e}")
        await update.message.reply_text("❌ Lỗi đọc tin tức.")
    except Exception as e:
        logger.debug(f"News: {e}")
        await update.message.reply_text("❌ Lỗi tin tức.")

@rate_limit(5)
async def music_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = " ".join(context.args) if context.args else ""
    if not url or not ("youtube.com" in url or "youtu.be" in url):
        return await update.message.reply_text("Dùng: `/music <youtube_url>`", parse_mode="Markdown")
    msg = await update.message.reply_text("⏳ Đang tải...")
    fn = None
    try:
        import yt_dlp
        import tempfile
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(tempfile.gettempdir(), "%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 30,
        }
        def _dl():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info), info.get("title", "Audio"), info.get("duration", 0)
        fn, title, dur = await asyncio.to_thread(_dl)
        if not os.path.exists(fn):
            await msg.edit_text("❌ Không tìm thấy file audio.")
            return
        with open(fn, "rb") as f:
            audio = f.read()
        ds = f"{dur//60}:{dur%60:02d}" if dur else ""
        await msg.edit_text("📤 Đang gửi...")
        await update.message.reply_audio(audio=audio, title=title[:200], caption=f"🎵 {title[:200]} ({ds})")
        try:
            await msg.delete()
        except Exception:
            pass
    except ImportError:
        await msg.edit_text("❌ Thiếu yt-dlp. pip install yt-dlp")
    except Exception as e:
        logger.debug(f"Music: {e}")
        await msg.edit_text(f"❌ Lỗi tải nhạc: {str(e)[:200]}")
    finally:
        if fn and os.path.exists(fn):
            try:
                os.remove(fn)
            except OSError:
                pass


@rate_limit(5)
async def stock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Real-time stock price using yfinance."""
    symbol = " ".join(context.args).upper().strip() if context.args else ""
    if not symbol:
        await update.message.reply_text(
            t("stock_no_args", update.effective_user.id),
            parse_mode="Markdown",
        )
        return
    # Auto-add .VN suffix for common Vietnamese stocks without suffix
    vn_tickers = {"FPT", "VNM", "VCB", "BID", "CTG", "TCB", "MBB", "VPB", "STB",
                  "ACB", "TPB", "HDB", "VIB", "EIB", "SSB", "PVB", "PVD", "PLX",
                  "SAB", "MSN", "VRE", "VIC", "MWG", "PNJ", "GMD", "HPG", "NKG",
                  "HSG", "VGC", "VSH", "DPM", "DCM", "CSV", "ANC", "BAF", "DGC"}
    if "." not in symbol and symbol in vn_tickers:
        symbol = f"{symbol}.VN"
    cache_key = f"stock:{symbol}"
    cached = cache_get(cache_key, ttl=60)
    if cached:
        await update.message.reply_text(cached, parse_mode="Markdown")
        return
    try:
        import yfinance as yf

        def _fetch_stock(sym):
            t = yf.Ticker(sym)
            info = t.fast_info
            return info.last_price, info.previous_close, info.last_volume, getattr(info, "exchange", "N/A")

        price, prev, vol, market = await asyncio.to_thread(_fetch_stock, symbol)
        if price is None:
            await update.message.reply_text(t("not_found", uid, q=symbol))
            return
        change = ((price - prev) / prev) * 100 if prev and prev > 0 else 0
        arrow = "📈" if change >= 0 else "📉"
        vol = info.last_volume or 0
        market = getattr(info, "exchange", "N/A")
        msg = (
            f"{t('stock_title', update.effective_user.id, symbol=symbol)}\n"
            f"{t('stock_price', update.effective_user.id, price=f'{price:,.2f}')}\n"
            f"{t('stock_change', update.effective_user.id, arrow=arrow, change=f'{change:+.2f}')}\n"
            f"{t('stock_volume', update.effective_user.id, vol=f'{vol:,}')}\n"
            f"{t('stock_market', update.effective_user.id, market=market)}"
        )
        cache_set(cache_key, msg)
        await update.message.reply_text(msg, parse_mode="Markdown")
    except ImportError:
        await update.message.reply_text("❌ Thiếu yfinance. pip install yfinance")
    except Exception as e:
        logger.debug(f"Stock lookup failed: {symbol} -> {e}")
        await update.message.reply_text(
            t("not_found", uid, q=symbol)
        )


async def lang_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch language EN/VI."""
    user_id = update.effective_user.id
    arg = (context.args[0].lower() if context.args else "").strip()
    if arg in ("en", "vi"):
        _user_lang[user_id] = arg
        await asyncio.gather(
            db.set_user_lang(user_id, arg),
            update.message.reply_text(t("lang_changed", user_id), parse_mode="Markdown"),
        )
    else:
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🇻🇳 Tiếng Việt", callback_data="lang_vi"),
                InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
            ]
        ])
        await update.message.reply_text(
            "🌐 **Choose language:**\n\n"
            "• 🇻🇳 **Tiếng Việt**\n"
            "• 🇬🇧 **English**",
            reply_markup=kb,
            parse_mode="Markdown",
        )


async def lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle language selection callback."""
    q = update.callback_query
    await q.answer()
    data = q.data
    user_id = q.from_user.id
    if data == "lang_vi":
        _user_lang[user_id] = "vi"
        await asyncio.gather(
            db.set_user_lang(user_id, "vi"),
            q.edit_message_text("✅ Đã đổi sang **Tiếng Việt**", parse_mode="Markdown"),
        )
    elif data == "lang_en":
        _user_lang[user_id] = "en"
        await asyncio.gather(
            db.set_user_lang(user_id, "en"),
            q.edit_message_text("✅ Switched to **English**", parse_mode="Markdown"),
        )


@rate_limit(10)
async def yt_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Download YouTube video (not just audio). Supports format selection."""
    uid = update.effective_user.id
    url = " ".join(context.args) if context.args else ""
    if not url or not ("youtube.com" in url or "youtu.be" in url):
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🎵 Audio", callback_data="yt_audio"),
                InlineKeyboardButton("🎬 Video", callback_data="yt_video"),
            ]
        ])
        await update.message.reply_text(
            t("yt_title", uid) + "\n\n" + t("yt_no_url", uid),
            reply_markup=kb,
            parse_mode="Markdown",
        )
        return
    fmt = context.user_data.get("yt_format", "audio")
    await _download_yt(update, url, fmt)


async def _download_yt(update: Update, url: str, fmt: str = "audio"):
    """Core YouTube download logic."""
    uid = update.effective_user.id
    msg = await update.message.reply_text(t("yt_processing", uid))
    fn = None
    try:
        import yt_dlp
        import tempfile
        if fmt == "video":
            ydl_opts = {
                "format": "best[ext=mp4]/best",
                "outtmpl": os.path.join(tempfile.gettempdir(), "%(id)s.%(ext)s"),
                "quiet": True,
                "no_warnings": True,
                "socket_timeout": 30,
            }
        else:
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": os.path.join(tempfile.gettempdir(), "%(id)s.%(ext)s"),
                "quiet": True,
                "no_warnings": True,
                "socket_timeout": 30,
            }

        def _dl():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info), info.get("title", "Video"), info.get("duration", 0)

        fn, title, dur = await asyncio.to_thread(_dl)
        if not os.path.exists(fn):
            await msg.edit_text("❌ File not found.")
            return
        ds = f"{dur//60}:{dur%60:02d}" if dur else ""
        await msg.edit_text(t("yt_sending", uid))
        with open(fn, "rb") as f:
            media_data = f.read()
        caption = t("yt_success", uid, title=title[:200], duration=ds)
        if fmt == "video":
            await update.message.reply_video(video=media_data, caption=caption, parse_mode="Markdown")
        else:
            await update.message.reply_audio(audio=media_data, title=title[:200], caption=caption)
        try:
            await msg.delete()
        except Exception:
            pass
    except ImportError:
        await msg.edit_text(t("yt_import_error", uid))
    except Exception as e:
        logger.debug(f"YT download failed: {e}")
        await msg.edit_text(f"❌ {str(e)[:200]}")
    finally:
        if fn and os.path.exists(fn):
            try:
                os.remove(fn)
            except OSError:
                pass


async def yt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle yt audio/video format selection."""
    q = update.callback_query
    await q.answer()
    data = q.data
    if data == "yt_audio":
        context.user_data["yt_format"] = "audio"
        await q.edit_message_text("🎵 **Audio mode** selected.\nNow send a YouTube URL.", parse_mode="Markdown")
    elif data == "yt_video":
        context.user_data["yt_format"] = "video"
        await q.edit_message_text("🎬 **Video mode** selected.\nNow send a YouTube URL.", parse_mode="Markdown")


async def kick_cmd(update, context):
    if not update.effective_chat or update.effective_chat.type=="private": return await update.message.reply_text("Chỉ dùng trong group.")
    m = await update.effective_chat.get_member(update.effective_user.id)
    if m.status not in ("administrator","creator"): return await update.message.reply_text("Cần quyền Admin.")
    t = update.message.reply_to_message.from_user.id if update.message.reply_to_message else (int(context.args[0]) if context.args else None)
    if not t: return await update.message.reply_text("Reply hoặc /kick <id>")
    try: await update.effective_chat.ban_member(t); await update.effective_chat.unban_member(t); await update.message.reply_text(f"Kick {t}.")
    except Exception as e: await update.message.reply_text(f"Loi: {e}")

async def ban_cmd(update, context):
    if not update.effective_chat or update.effective_chat.type=="private": return await update.message.reply_text("Chỉ dùng trong group.")
    m = await update.effective_chat.get_member(update.effective_user.id)
    if m.status not in ("administrator","creator"): return await update.message.reply_text("Cần quyền Admin.")
    t = update.message.reply_to_message.from_user.id if update.message.reply_to_message else (int(context.args[0]) if context.args else None)
    if not t: return await update.message.reply_text("Reply hoặc /ban <id>")
    try: await update.effective_chat.ban_member(t); await update.message.reply_text(f"Ban {t}.")
    except Exception as e: await update.message.reply_text(f"Loi: {e}")

async def unban_cmd(update, context):
    if not update.effective_chat or update.effective_chat.type=="private": return await update.message.reply_text("Chỉ dùng trong group.")
    m = await update.effective_chat.get_member(update.effective_user.id)
    if m.status not in ("administrator","creator"): return await update.message.reply_text("Cần quyền Admin.")
    t = update.message.reply_to_message.from_user.id if update.message.reply_to_message else (int(context.args[0]) if context.args else None)
    if not t: return await update.message.reply_text("Reply hoặc /unban <id>")
    try: await update.effective_chat.unban_member(t); await update.message.reply_text(f"Unban {t}.")
    except Exception as e: await update.message.reply_text(f"Loi: {e}")

async def mute_cmd(update, context):
    if not update.effective_chat or update.effective_chat.type == "private":
        return await update.message.reply_text("Chỉ dùng trong group.")
    m = await update.effective_chat.get_member(update.effective_user.id)
    if m.status not in ("administrator", "creator"):
        return await update.message.reply_text("Cần quyền Admin.")
    t = update.message.reply_to_message.from_user.id if update.message.reply_to_message else (int(context.args[0]) if context.args else None)
    if not t:
        return await update.message.reply_text("Reply hoặc /mute <id>")
    try:
        from telegram import ChatPermissions
        await update.effective_chat.restrict_member(
            t,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
                can_send_audios=False,
                can_send_documents=False,
                can_send_photos=False,
                can_send_videos=False,
                can_send_video_notes=False,
                can_send_voice_notes=False,
            ),
            until_date=None,
        )
        await update.message.reply_text(f"🔇 Muted {t} (vĩnh viễn).")
    except Exception as e:
        await update.message.reply_text(f"Lỗi: Bot cần quyền 'restrict members'.")


async def unmute_cmd(update, context):
    if not update.effective_chat or update.effective_chat.type == "private":
        return await update.message.reply_text("Chỉ dùng trong group.")
    m = await update.effective_chat.get_member(update.effective_user.id)
    if m.status not in ("administrator", "creator"):
        return await update.message.reply_text("Cần quyền Admin.")
    t = update.message.reply_to_message.from_user.id if update.message.reply_to_message else (int(context.args[0]) if context.args else None)
    if not t:
        return await update.message.reply_text("Reply hoặc /unmute <id>")
    try:
        from telegram import ChatPermissions
        await update.effective_chat.restrict_member(
            t,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_invite_users=True,
                can_pin_messages=True,
                can_change_info=True,
            ),
            until_date=None,
        )
        await update.message.reply_text(f"🔊 Unmuted {t} (khôi phục toàn bộ quyền).")
    except Exception as e:
        await update.message.reply_text(f"Lỗi: Bot cần quyền 'restrict members'.")
# Maps menu "run_" buttons to their handlers (defined after all handlers exist)
RUN_ACTIONS = {
    "ip": ip_cmd,
    "joke": joke_cmd,
    "meme": meme_cmd,
    "crypto": crypto_cmd,
    "tygia": tygia_cmd,
    "weather": weather,
    "translate": translate_cmd,
    "shorten": shorten_cmd,
    "screenshot": screenshot_cmd,
    "password": password_cmd,
    "bypass": bypass_cmd,
    "code": code_cmd,
    "anime": anime_cmd,
    "dictionary": dictionary,
    "wiki": wiki_cmd,
    "van": van_cmd,
    "lich": lich_cmd,
    "remind": remind,
    "ask": ask_cmd,
    "tiktok_search": tiktok_search_cmd,
    "tiktok_profile": tiktok_profile_cmd,
    "tiktok_seo": tiktok_seo_cmd,
    "tiktok_hashtag": tiktok_hashtag_cmd,
    "tiktok_trending": tiktok_trending_cmd,
    "stats": stats_cmd,
    "myusage": myusage_cmd,
    "news": news_cmd,
    "music": music_cmd,
    "stock": stock_cmd,
    "yt": yt_cmd,
    "lang": lang_cmd,
    "status": status_cmd,
}


# FIX: consolidated main function with proper startup sequence

async def _backup_db_loop():
    import shutil
    while True:
        await asyncio.sleep(6 * 3600)
        try:
            if os.path.exists("bot.db"):
                shutil.copy2("bot.db", "bot.backup.db")
                logger.info("DB backed up")
        except Exception as e:
            logger.debug(f"Backup: {e}")


async def _periodic_cleanup_loop():
    while True:
        await asyncio.sleep(300)
        try:
            _cleanup_rate_limits()
            async with _cache_lock:
                now = time.monotonic()
                expired = [k for k, (ts, _) in _cache.items() if now - ts > 3600]
                for k in expired:
                    _cache.pop(k, None)
                    if k in _cache_access_order:
                        _cache_access_order.remove(k)
            logger.debug(
                f"Cleanup: cache={len(_cache)}, rate_limit={len(_last_call)}, flood={len(_flood_count)}"
            )
        except Exception as e:
            logger.debug(f"Cleanup loop error: {e}")


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
        BotCommand("code", "Code → ảnh"),
        BotCommand("password", "Tạo mật khẩu"),
        BotCommand("calc", "Máy tính"),
        BotCommand("anime", "Tra anime"),
        BotCommand("meme", "Meme ngẫu nhiên"),
        BotCommand("lich", "Lịch âm Việt Nam"),
        BotCommand("wiki", "Tra Wikipedia"),
        BotCommand("tygia", "Tỷ giá ngoại tệ"),
        BotCommand("bypass", "Bypass link rút gọn"),
        BotCommand("tiktok", "Tải video TikTok"),
        BotCommand("tiktok_profile", "Xem profile TikTok"),
        BotCommand("tiktok_search", "Tìm kiếm TikTok"),
        BotCommand("tiktok_trending", "Video thịnh hành"),
        BotCommand("tiktok_seo", "Gợi ý SEO TikTok"),
        BotCommand("tiktok_hashtag", "Tra hashtag TikTok"),
        BotCommand("ask", "Hỏi AI Chatbot"),
        BotCommand("stats", "Thống kê sử dụng"),
        BotCommand("myusage", "Lịch sử của bạn"),
        BotCommand("music", "Tải nhạc YouTube"),
        BotCommand("yt", "Tải video YouTube"),
        BotCommand("stock", "Giá cổ phiếu real-time"),
        BotCommand("lang", "Đổi ngôn ngữ (EN/VI)"),
        BotCommand("clear", "Xoá lịch sử chat"),
        BotCommand("news", "Tin tức"),
        BotCommand("kick", "Kick user"),
        BotCommand("ban", "Ban user"),
        BotCommand("unban", "Unban user"),
        BotCommand("mute", "Mute user"),
        BotCommand("unmute", "Unmute user"),
    ]
    await app.bot.set_my_commands(commands)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(menu_handler, pattern="^(menu_|run_|suggest_|noop)"))
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
    app.add_handler(CommandHandler("kick", kick_cmd))
    app.add_handler(CommandHandler("ban", ban_cmd))
    app.add_handler(CommandHandler("unban", unban_cmd))
    app.add_handler(CommandHandler("mute", mute_cmd))
    app.add_handler(CommandHandler("unmute", unmute_cmd))
    app.add_handler(CommandHandler("news", news_cmd))
    app.add_handler(CommandHandler("music", music_cmd))
    app.add_handler(CommandHandler("yt", yt_cmd))
    app.add_handler(CommandHandler("stock", stock_cmd))
    app.add_handler(CommandHandler("lang", lang_cmd))
    app.add_handler(CallbackQueryHandler(lang_callback, pattern="^lang_"))
    app.add_handler(CallbackQueryHandler(yt_callback, pattern="^yt_"))
    app.add_handler(CommandHandler("tiktok_auto", tiktok_auto_cmd))
    app.add_handler(CommandHandler("tiktok_stop", tiktok_stop_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("myusage", myusage_cmd))
    app.add_handler(CommandHandler("clear", clear_cmd))
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

    # Initialize database + start flush loop
    await db.get_db()
    db.start_flush_loop()

    # Preload user language preferences from DB
    try:
        cur = await db._exec_read("SELECT user_id, lang FROM user_lang")
        for row in await cur.fetchall():
            _user_lang[row[0]] = row[1]
        if _user_lang:
            logger.info("Loaded %d user language preferences", len(_user_lang))
    except Exception as e:
        logger.debug("No lang prefs to load: %s", e)

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

    await reschedule_reminders(app.bot)
    _task_list.append(asyncio.create_task(_backup_db_loop()))
    _task_list.append(asyncio.create_task(_periodic_cleanup_loop()))

    try:
        while not _shutdown_event:
            await asyncio.sleep(1)
        logger.info("Shutdown received, stopping bot...")
    except asyncio.CancelledError:
        logger.info("Shutdown received, stopping bot...")
    finally:
        # Cancel all background tasks
        for task in _task_list:
            task.cancel()
        await asyncio.gather(*_task_list, return_exceptions=True)
        _task_list.clear()

        # Graceful shutdown: cancel all tiktok auto tasks
        for chat_id, task_info in list(_tiktok_auto_tasks.items()):
            try:
                task_info["task"].cancel()
            except Exception:
                pass
        _tiktok_auto_tasks.clear()

        await app.updater.stop()
        await app.stop()
        await app.shutdown()

        # Close AI session
        try:
            from ai_chat import close_session
            await close_session()
        except Exception:
            pass

        # Close database
        await db.close_db()

        if 'runner' in locals():
            await runner.cleanup()


if __name__ == "__main__":
    import time as _time
    while True:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
            break
        except Exception as _e:
            logger.exception(f"Bot crashed: {_e} - restarting in 5s...")
            _time.sleep(5)
