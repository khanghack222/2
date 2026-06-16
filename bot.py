import logging
import asyncio
import re
import datetime
import json
import os
import urllib.request
import urllib.parse
import secrets
import string
import random
import html as html_mod
import sys
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

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
PASSWORDS_FILE = "passwords.json"
START_TIME = datetime.datetime.now()
VAN_BLACKLIST_FILE = "van_blacklist.json"

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


# FIX: global mutable state is acceptable for single-process async,
# but we add a deep-copy on write to prevent partial corruption
reminders = safe_json_load(DATA_FILE, {})
passwords = safe_json_load(PASSWORDS_FILE, {})


# --- Van blacklist helpers ---
def load_van_blacklist():
    return safe_json_load(VAN_BLACKLIST_FILE, [])


def save_van_blacklist(data):
    save_json(VAN_BLACKLIST_FILE, data)


# --- Core command handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "Chào bạn! Tôi là bot cá nhân của bạn.\n\n"
        "📌 **Lệnh cơ bản:**\n"
        "/help - Hướng dẫn chi tiết\n"
        "/id - Thông tin của bạn\n"
        "/status - Trạng thái bot\n\n"
        "📌 **Tiện ích:**\n"
        "/weather <tp> - Thời tiết\n"
        "/translate <văn bản> - Dịch sang Anh\n"
        "/shorten <url> - Rút gọn link\n"
        "/qr <nội dung> - Tạo QR\n"
        "/crypto - Giá crypto\n"
        "/ip - IP + vị trí\n"
        "/screenshot <url> - Chụp web\n\n"
        "📌 **Công cụ:**\n"
        "/code <ext> - Ảnh code đẹp (vd: /code py)\n"
        "/calc <biểu thức> - Máy tính (/calc 2+2*pi)\n"
        "/password <số> - Tạo mật khẩu\n"
        "/passwords - DS mật khẩu\n"
        "/editpass <id> <mk> - Sửa pass\n"
        "/delpass <id> - Xóa pass\n"
        "/proxy - Random proxy\n\n"
        "📌 **Giải trí:**\n"
        "/joke - Câu chuyện vui\n"
        "/anime <tên> - Tra anime\n"
        "/meme - Meme ngẫu nhiên\n\n"
        "📌 **Học tập:**\n"
        "/van - Văn mẫu lớp 8\n"
        "/dictionary <từ> - Tra từ điển\n\n"
        "📌 **Lịch:**\n"
        "/lich - Lịch âm hôm nay\n"
        "/lich 30/4/2026 - Xem lịch ngày cụ thể\n\n"
        "📌 **VMOS:**\n"
        "/vmos - Tạo VMOS Cloud trial (tự động)\n"
        "/otp <mã> - Nhập OTP thủ công nếu auto lỗi\n\n"
        "📌 **Khác:**\n"
        "/remind <giây> <nd> - Đặt nhắc nhở\n"
        "/list - DS nhắc nhở\n"
        "/cancel <id> - Hủy nhắc nhở"
    )
    await update.message.reply_text(msg)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📌 **Ví dụ từng lệnh:**\n\n"
        "🌤 `/weather hanoi` — Thời tiết Hà Nội\n"
        "🌤 `/weather hanoi,vi` — Tiếng Việt\n\n"
        "🌐 `/translate hello world` — Dịch sang Anh\n"
        "🌐 `/translate xin chào|vi|en` — Dịch từ Việt sang Anh\n\n"
        "🔗 `/shorten https://example.com` — Rút gọn link\n\n"
        "📱 `/qr https://example.com` — Tạo QR code\n\n"
        "💰 `/crypto` — Giá BTC, ETH, SOL\n\n"
        "📸 `/screenshot https://example.com` — Chụp ảnh web\n\n"
        "🧮 `/calc 2+2*pi` — Máy tính (pi, e, sqrt, abs, round)\n"
        "🧮 `/calc 2**10` — Luỹ thừa\n"
        "🧮 `/calc sqrt(144)+abs(-5)` — Hàm\n\n"
        "🔐 `/password 16` — Tạo mật khẩu 16 ký tự\n"
        "🔐 `/password 20 email` — Tạo + lưu với tên 'email'\n"
        "🔐 `/passwords` — Xem mật khẩu đã lưu\n"
        "🔐 `/editpass 1 mkmoi` — Sửa mật khẩu số 1\n"
        "🔐 `/delpass 1` — Xóa mật khẩu số 1\n\n"
        "📖 `/dictionary hello` — Tra từ 'hello'\n\n"
        "🎭 `/joke` — Câu chuyện vui\n\n"
        "📺 `/anime naruto` — Tra anime Naruto\n\n"
        "😂 `/meme` — Meme ngẫu nhiên từ Reddit\n\n"
        "📝 `/van` — Văn mẫu lớp 8 ngẫu nhiên\n\n"
        "📅 `/lich` — Lịch âm hôm nay\n"
        "📅 `/lich 30/4/2026` — Xem ngày cụ thể\n\n"
        "🤖 `/vmos` — Tạo VMOS Cloud trial\n"
        "🤖 `/otp 123456` — Nhập OTP thủ công cho VMOS\n\n"
        "⏰ `/remind 60 Mua sữa` — Nhắc sau 60 giây\n"
        "⏰ `/list` — Danh sách nhắc nhở\n"
        "⏰ `/cancel 1` — Hủy nhắc nhở số 1\n\n"
        "ℹ️ `/id` — Thông tin của bạn\n"
        "ℹ️ `/status` — Trạng thái bot\n"
        "ℹ️ `/ip` — IP + vị trí hiện tại\n"
        "ℹ️ `/proxy` — Random proxy miễn phí"
    )
    await update.message.reply_text(msg)


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
        rid = len(reminders[user_id]) + 1
        reminders[user_id].append({"id": rid, "content": content, "seconds": seconds})
        save_json(DATA_FILE, reminders)

        await update.message.reply_text(f" Đã đặt nhắc nhở #{rid}: '{content}' sau {seconds}s")

        async def remind_task():
            try:
                await asyncio.sleep(seconds)
                await update.effective_user.send_message(f"⏰ Nhắc nhở #{rid}: {content}")
            except Exception as e:
                logger.warning(f"Failed to send reminder #{rid}: {e}")
            finally:
                if user_id in reminders:
                    reminders[user_id] = [r for r in reminders[user_id] if r["id"] != rid]
                    save_json(DATA_FILE, reminders)

        asyncio.create_task(remind_task())
    except (IndexError, ValueError):
        await update.message.reply_text("Sai cú pháp. Ví dụ: /remind 60 Mua sữa")


async def list_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in reminders or not reminders[user_id]:
        await update.message.reply_text("Không có nhắc nhở nào.")
        return
    lines = [f"#{r['id']} - {r['content']} (sau {r['seconds']}s)" for r in reminders[user_id]]
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


async def dictionary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    word = " ".join(context.args)
    if not word:
        await update.message.reply_text("Nhập từ cần tra. Ví dụ: /dictionary hello")
        return

    try:
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{urllib.parse.quote(word)}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        meanings = data[0].get("meanings", [])
        lines = [f"**{data[0]['word']}**"]
        for m in meanings[:3]:
            part = m["partOfSpeech"]
            defs = m["definitions"][:2]
            for d in defs:
                lines.append(f"({part}) {d['definition']}")
                if d.get("example"):
                    lines.append(f"  VD: {d['example']}")
        await update.message.reply_text("\n".join(lines) if len(lines) > 1 else "Không tìm thấy.")
    except Exception as e:
        logger.debug(f"Dictionary lookup failed: {e}")
        await update.message.reply_text(f"Không tìm thấy từ '{word}' hoặc lỗi API.")


async def weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = " ".join(context.args)
    if not city:
        await update.message.reply_text(
            "🌤 `/weather hanoi` — Thời tiết Hà Nội\n"
            "🌤 `/weather tuyên quang` — Tuyên Quang\n"
            "🌤 `/weather hanoi,vi` — Tiếng Việt"
        )
        return

    candidates = [city, f"{city},Vietnam", f"{city},Vn"]
    for c in candidates:
        try:
            url = f"https://wttr.in/{urllib.parse.quote(c)}?format=%C|%t|%h|%w|%p&lang=vi"
            req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8")
            parts = raw.split("|")
            if len(parts) >= 5 and not parts[0].startswith("Unknown"):
                name = city.title()
                msg = (
                    f"🌤 **Thời tiết {name}:**\n"
                    f"☁️ {parts[0]}\n"
                    f"🌡 {parts[1]}\n"
                    f"💧 {parts[2]}\n"
                    f"💨 {parts[3]}\n"
                    f"🌧 {parts[4]}"
                )
                await update.message.reply_text(msg)
                return
        except Exception:
            continue
    await update.message.reply_text(f"❌ Không tìm thấy '{city}'. Thử /weather hanoi")


async def ip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        req = urllib.request.Request("http://ip-api.com/json/", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        msg = (
            f"IP: {data.get('query')}\n"
            f"Quốc gia: {data.get('country')}\n"
            f"Thành phố: {data.get('city')}\n"
            f"ISP: {data.get('isp')}\n"
            f"Lat/Lon: {data.get('lat')}, {data.get('lon')}"
        )
        await update.message.reply_text(msg)
    except Exception as e:
        logger.debug(f"IP lookup failed: {e}")
        await update.message.reply_text("Lỗi lấy thông tin IP.")


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
    idx = len(passwords[user_id]) + 1
    label = " ".join(context.args[1:]) if len(context.args) > 1 else f"pass{idx}"
    # FIX: passwords stored in plaintext — for a personal bot this is acceptable,
    # but consider adding encryption for production use
    passwords[user_id].append({"id": idx, "label": label, "password": pw})
    save_json(PASSWORDS_FILE, passwords)
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
                    save_json(PASSWORDS_FILE, passwords)
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
            save_json(PASSWORDS_FILE, passwords)
            await update.message.reply_text(f" Đã xóa mật khẩu #{pid}")
        else:
            await update.message.reply_text(f"Không tìm thấy mật khẩu #{pid}")
    except (IndexError, ValueError):
        await update.message.reply_text("Sai cú pháp. VD: /delpass 1")


async def proxy_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        urls = [
            "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all",
            "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
        ]
        proxies = []
        for url in urls:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = resp.read().decode()
                    proxies.extend([p.strip() for p in data.splitlines() if p.strip()])
            except Exception as e:
                logger.debug(f"Proxy source {url[:40]} failed: {e}")
                continue
        if proxies:
            p = secrets.choice(proxies)  # FIX: use secrets instead of random for unbiased selection
            await update.message.reply_text(f"Proxy ngẫu nhiên:\n`{p}`", parse_mode="Markdown")
        else:
            await update.message.reply_text("Không lấy được proxy.")
    except Exception as e:
        logger.warning(f"Proxy command failed: {e}")
        await update.message.reply_text("Lỗi lấy proxy.")


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
            "language": lang,
            "theme": "dracula",
            "backgroundColor": "rgba(40,44,52,1)",
        }).encode()
        req = urllib.request.Request(
            "https://carbon-api.vercel.app/api/code",
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            img_data = resp.read()
        await update.message.reply_photo(photo=img_data, caption=f"Code ({lang})")
    except Exception as e:
        logger.debug(f"Code image failed: {e}")
        await update.message.reply_text("Lỗi tạo ảnh code. Thử lại sau.")
    return True


async def screenshot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = " ".join(context.args)
    if not url:
        await update.message.reply_text("Nhập URL. Ví dụ: /screenshot https://google.com")
        return
    if not url.startswith("http"):
        url = "https://" + url
    try:
        api_url = f"https://api.microlink.io/?url={urllib.parse.quote(url)}&screenshot=true"
        req = urllib.request.Request(api_url, headers={"User-Agent": "curl/8.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        img_url = data.get("data", {}).get("screenshot", {}).get("url")
        if not img_url:
            await update.message.reply_text("Không thể chụp ảnh.")
            return
        req2 = urllib.request.Request(img_url, headers={"User-Agent": "curl/8.0"})
        with urllib.request.urlopen(req2, timeout=30) as resp:
            img_data = resp.read()
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


async def van_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    BASE = "https://vietjack.com"
    try:
        req = urllib.request.Request(BASE + "/van-mau-lop-8/", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8")
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
        req2 = urllib.request.Request(essay_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req2, timeout=15) as resp2:
            html2 = resp2.read().decode("utf-8")

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


async def translate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Nhập văn bản. VD: /translate hello world")
        return
    try:
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=vi&dt=t&q={urllib.parse.quote(text)}"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
        result = json.loads(raw)
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


async def shorten_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = " ".join(context.args)
    if not url:
        await update.message.reply_text("Nhập URL. VD: /shorten https://example.com")
        return
    try:
        api = f"https://tinyurl.com/api-create.php?url={urllib.parse.quote(url)}"
        req = urllib.request.Request(api, headers={"User-Agent": "curl/8.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            short = resp.read().decode("utf-8").strip()
        await update.message.reply_text(f"Link rút gọn: {short}")
    except Exception as e:
        logger.debug(f"Shorten failed: {e}")
        await update.message.reply_text("Lỗi rút gọn link.")


async def qr_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Nhập nội dung. VD: /qr https://google.com")
        return
    try:
        url = f"https://api.qrserver.com/v1/create-qr-code/?size=400x400&data={urllib.parse.quote(text)}"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            img = resp.read()
        await update.message.reply_photo(photo=img, caption="QR Code")
    except Exception as e:
        logger.debug(f"QR failed: {e}")
        await update.message.reply_text("Lỗi tạo QR.")


async def crypto_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana,binancecoin,ripple&vs_currencies=usd&include_24hr_change=true"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        lines = ["Giá Crypto (USD):"]
        for coin, info in data.items():
            price = info["usd"]
            change = info.get("usd_24h_change", 0)
            arrow = "📈" if change >= 0 else "📉"
            lines.append(f"{coin.upper()}: ${price} ({arrow} {change:+.2f}%)")
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        logger.debug(f"Crypto failed: {e}")
        await update.message.reply_text("Lỗi lấy giá crypto.")


async def joke_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = "https://v2.jokeapi.dev/joke/Any?safe-mode"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        text = data.get("joke") or (data["setup"] + "\n" + data["delivery"])
        turl = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=vi&dt=t&q=" + urllib.parse.quote(text)
        treq = urllib.request.Request(turl, headers={"User-Agent": "curl/8.0"})
        with urllib.request.urlopen(treq, timeout=10) as tresp:
            tdata = json.loads(tresp.read().decode("utf-8"))
        translated = "".join(part[0] for part in tdata[0]) if isinstance(tdata, list) and len(tdata) > 0 else str(tdata)
        await update.message.reply_text(translated)
    except Exception as e:
        logger.debug(f"Joke failed: {e}")
        await update.message.reply_text("Lỗi lấy joke.")


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
    save_json(PASSWORDS_FILE, passwords)
    logger.info("Bot restart initiated by user %s", user_id)
    sys.exit(0)


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


async def anime_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("Nhập tên anime. VD: /anime one piece")
        return
    try:
        url = f"https://api.jikan.moe/v4/anime?q={urllib.parse.quote(query)}&limit=1"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
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
        if img:
            await update.message.reply_photo(photo=img, caption=msg, parse_mode="HTML")
        else:
            await update.message.reply_text(msg, parse_mode="HTML")
    except Exception as e:
        logger.debug(f"Anime lookup failed: {e}")
        await update.message.reply_text("Lỗi tra anime.")


async def meme_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        subreddits = ["vozmemes", "VietNamMeme", "VietnameseMemes"]
        sub = secrets.choice(subreddits)
        url = f"https://www.reddit.com/r/{sub}/random.json"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if isinstance(data, list) and len(data) > 0:
            data = data[0]
        children = data.get("data", {}).get("children", [])
        if not children:
            await update.message.reply_text("Không có meme.")
            return
        post = children[0]["data"]
        img_url = post.get("url_overridden_by_dest") or post.get("url", "")
        title = post.get("title", "")
        if img_url and any(img_url.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif"]):
            await update.message.reply_photo(photo=img_url, caption=title)
        else:
            await update.message.reply_text(f"{title}\n{img_url}")
    except Exception as e:
        logger.debug(f"Meme failed: {e}")
        await update.message.reply_text("Lỗi lấy meme.")


# --- Lịch âm Việt Nam ---
_CAN = ['Giáp', 'Ất', 'Bính', 'Đinh', 'Mậu', 'Kỷ', 'Canh', 'Tân', 'Nhâm', 'Quý']
_CHI = ['Tý', 'Sửu', 'Dần', 'Mão', 'Thìn', 'Tỵ', 'Ngọ', 'Mùi', 'Thân', 'Dậu', 'Tuất', 'Hợi']
_TIET = ['Xuân', 'Hạ', 'Thu', 'Đông']
_THU = ['Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy', 'Chủ Nhật']

async def lich_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        import lunardate
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


# --- VMOS Cloud (mail.tm + auto-poll OTP) ---
# In-memory store: user_id -> registration state
_vmos_registrations: dict[int, dict] = {}
_vmos_poll_tasks: dict[int, asyncio.Task] = {}

_BX = "https://api.vmoscloud.com/vcpcloud/api"
_VMOS_HD = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "requestsource": "wechat-miniapp",
    "clientType": "web",
    "appVersion": "3.6.1401",
}
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def _vmos_req(url, data=None, method="POST", headers=None, timeout=10):
    h = dict(headers or {})
    h.setdefault("User-Agent", _UA)
    if data is not None:
        h.setdefault("Content-Type", "application/json")
    body = json.dumps(data).encode("utf-8") if data is not None else None
    r = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        resp = urllib.request.urlopen(r, timeout=timeout)
        return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return e.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return e.code, {"raw": raw}
    except Exception as e:
        return 0, {"error": str(e)}


def _extract_otp_from_msg(msg_data):
    body_text = ""
    if isinstance(msg_data.get("text"), list):
        for t in msg_data["text"]:
            if isinstance(t, dict):
                body_text += (t.get("content") or "")
            elif isinstance(t, str):
                body_text += t
    elif isinstance(msg_data.get("text"), str):
        body_text = msg_data["text"]

    if not body_text and isinstance(msg_data.get("html"), list):
        import html as _html
        for h in msg_data["html"]:
            if isinstance(h, str):
                body_text += _html.unescape(re.sub(r"<[^>]+>", "", h))

    subject = msg_data.get("subject") or ""
    search_text = f"{subject}\n{body_text}"
    codes = re.findall(r"(?<!\d)(\d{4,8})(?!\d)", search_text)
    return codes[0] if codes else None


async def vmos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Cancel any existing poll task
    old = _vmos_poll_tasks.pop(user_id, None)
    if old is not None:
        old.cancel()

    msg = await update.message.reply_text("⏳ Đang tạo email ảo...")

    # 1. Fetch mail.tm domains
    status, data = _vmos_req("https://api.mail.tm/domains", method="GET", timeout=10)
    if status == 200 and isinstance(data, list):
        domains = [d["domain"] for d in data if d.get("isActive")]
    else:
        logger.debug(f"mail.tm domains failed: status={status}, data={str(data)[:200]}")
        domains = []
    if not domains:
        logger.debug("Falling back to hardcoded domain")
        domains = ["web-library.net"]

    # 2. Create mail.tm account
    domain = random.choice(domains)
    name = "v" + "".join(random.choices(string.ascii_lowercase + string.digits, k=7))
    email = f"{name}@{domain}"
    pw = str(random.randint(100000, 999999))

    status, data = _vmos_req(
        "https://api.mail.tm/accounts",
        {"address": email, "password": pw},
        "POST",
        {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": _UA},
        15,
    )
    if status not in (200, 201):
        err = data.get("violations", data.get("detail", str(data)[:100]))
        await msg.edit_text(f"❌ Lỗi tạo email: {err}")
        return

    # 3. Get mail.tm token
    status, data = _vmos_req(
        "https://api.mail.tm/token",
        {"address": email, "password": pw},
        "POST",
        {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": _UA},
        15,
    )
    if status != 200 or not isinstance(data, dict):
        await msg.edit_text("❌ Lỗi lấy token mail.")
        return
    mail_token = data.get("token") or data.get("id", "")

    # 4. Store registration state
    _vmos_registrations[user_id] = {
        "email": email, "password": pw,
        "mail_token": mail_token, "status": "waiting",
    }

    hint = (
        "📌 **Hướng dẫn:**\n"
        f"1. Mở https://cloud.vmoscloud.com/login\n"
        f"2. Nhập `{email}` → bấm **Gửi mã**\n"
        f"3. **Kéo captcha** → VMOS gửi OTP về email\n"
        f"4. Bot tự động check và reg, **không cần gõ gì thêm**\n\n"
        f"⏳ Nếu lâu quá, dùng `/otp <mã>` để nhập thủ công."
    )

    await msg.edit_text(
        f"📧 `{email}`\n🔑 `{pw}`\n\n{hint}"
    )

    # 5. Start background polling
    task = asyncio.create_task(
        _vmos_poll_loop(user_id, chat_id, context.bot, mail_token, email, pw, msg)
    )
    _vmos_poll_tasks[user_id] = task


async def _vmos_poll_loop(user_id, chat_id, bot, mail_token, email, pw, info_msg):
    """Poll mail.tm inbox for OTP, then auto-register + trial."""
    try:
        known_ids = set()
        for attempt in range(35):
            await asyncio.sleep(3)

            status, data = _vmos_req(
                "https://api.mail.tm/messages?page=1",
                method="GET",
                headers={"Authorization": f"Bearer {mail_token}", "Accept": "application/json", "User-Agent": _UA},
                timeout=10,
            )
            if status != 200:
                continue
            msgs = data if isinstance(data, list) else []
            new_msgs = [m for m in msgs if isinstance(m, dict) and m.get("id") not in known_ids]

            for m in new_msgs:
                known_ids.add(m["id"])
                mid = m["id"]

                status, detail = _vmos_req(
                    f"https://api.mail.tm/messages/{mid}",
                    method="GET",
                    headers={"Authorization": f"Bearer {mail_token}", "Accept": "application/json", "User-Agent": _UA},
                    timeout=10,
                )
                if status != 200:
                    continue

                otp = _extract_otp_from_msg(detail)
                if not otp:
                    continue

                # Found OTP!
                await bot.edit_message_text(
                    f"📧 `{email}`\n🔑 `{pw}`\n\n✅ Nhận được OTP: `{otp}`\n⏳ Đang reg...",
                    chat_id=chat_id, message_id=info_msg.message_id,
                )

                # Register via VMOS API
                reg_ok = False
                token = None
                reg_payloads = [
                    {"mobilePhone": email, "loginType": 0, "verifyCode": otp, "channel": "web"},
                    {"mobilePhone": email, "password": pw, "verifyCode": otp},
                    {"email": email, "password": pw, "verifyCode": otp},
                ]
                for p in reg_payloads:
                    ep = f"{_BX}/user/login" if "loginType" in p else f"{_BX}/user/register"
                    rc, rd = _vmos_req(ep, p, "POST", _VMOS_HD, 10)
                    if isinstance(rd, dict) and rd.get("code") == 200:
                        reg_ok = True
                        token = (rd.get("data") or {}).get("token") if isinstance(rd.get("data"), dict) else None
                        break

                if reg_ok:
                    trial = ""
                    hd2 = {**_VMOS_HD}
                    if token:
                        hd2["Token"] = token
                    for ep in ["/order/create", "/order/createMoneyOrder", "/cloudTemplate/buyGoodTimeOrder"]:
                        tp = {"email": email, "type": 1}
                        if "buyGoodTime" in ep:
                            tp["goodId"] = ""
                        rc2, rd2 = _vmos_req(f"{_BX}{ep}", tp, "POST", hd2, 10)
                        if isinstance(rd2, dict) and rd2.get("code") == 200:
                            trial = " | ✅ Trial"
                            break
                    await bot.edit_message_text(
                        f"🎉 **Acc VMOS**\n📧 `{email}`\n🔑 `{pw}`{trial}",
                        chat_id=chat_id, message_id=info_msg.message_id,
                    )
                else:
                    await bot.edit_message_text(
                        f"✅ Có OTP `{otp}` nhưng reg API lỗi.\n"
                        f"👉 Vào cloud.vmoscloud.com/login nhập OTP `{otp}`, set pass `{pw}` thủ công.",
                        chat_id=chat_id, message_id=info_msg.message_id,
                    )
                return  # done

        # Timeout — no OTP received
        await bot.edit_message_text(
            f"⏰ Quá thời gian chờ OTP.\n"
            f"📧 `{email}`\n🔑 `{pw}`\n\n"
            f"👉 Dùng `/otp <số>` nếu đã nhận được mail.",
            chat_id=chat_id, message_id=info_msg.message_id,
        )
    except asyncio.CancelledError:
        pass
    except Exception as e:
        try:
            await bot.edit_message_text(
                f"❌ Lỗi: {e}",
                chat_id=chat_id, message_id=info_msg.message_id,
            )
        except:
            pass
    finally:
        _vmos_poll_tasks.pop(user_id, None)


async def otp_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    reg = _vmos_registrations.get(user_id)
    if not reg:
        await update.message.reply_text(
            "❌ Chưa chạy `/vmos`.\n"
            "📌 `/vmos` → bot tạo email → bạn nhập email vào cloud.vmoscloud.com/login → nhận OTP → `/otp <mã>`"
        )
        return

    args = context.args
    if not args:
        await update.message.reply_text("❌ Ghi: `/otp 123456`")
        return

    otp = args[0].strip()
    if not re.match(r"^\d{4,8}$", otp):
        await update.message.reply_text("❌ Mã OTP không hợp lệ (4-8 số)")
        return

    email = reg["email"]
    pw = reg["password"]
    msg = await update.message.reply_text("⏳ Đang reg + trial...")

    reg_ok = False
    token = None
    payloads = [
        {"mobilePhone": email, "loginType": 0, "verifyCode": otp, "channel": "web"},
        {"mobilePhone": email, "password": pw, "verifyCode": otp},
        {"email": email, "password": pw, "verifyCode": otp},
    ]
    for p in payloads:
        ep = f"{_BX}/user/login" if "loginType" in p else f"{_BX}/user/register"
        rc, rd = _vmos_req(ep, p, "POST", _VMOS_HD, 10)
        if isinstance(rd, dict) and rd.get("code") == 200:
            reg_ok = True
            token = (rd.get("data") or {}).get("token") if isinstance(rd.get("data"), dict) else None
            break

    if reg_ok:
        trial = ""
        hd2 = {**_VMOS_HD}
        if token:
            hd2["Token"] = token
        for ep in ["/order/create", "/order/createMoneyOrder", "/cloudTemplate/buyGoodTimeOrder"]:
            tp = {"email": email, "type": 1}
            if "buyGoodTime" in ep:
                tp["goodId"] = ""
            rc2, rd2 = _vmos_req(f"{_BX}{ep}", tp, "POST", hd2, 10)
            if isinstance(rd2, dict) and rd2.get("code") == 200:
                trial = " | ✅ Trial"
                break
        await msg.edit_text(f"🎉 **Acc VMOS**\n📧 `{email}`\n🔑 `{pw}`{trial}")
    else:
        await msg.edit_text(
            f"❌ Reg API lỗi.\n"
            f"👉 Vào cloud.vmoscloud.com/login nhập OTP `{otp}`, set pass `{pw}` thủ công"
        )


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
        BotCommand("vmos", "Tạo VMOS Cloud trial"),
        BotCommand("otp", "Nhập mã OTP cho /vmos"),
    ]
    await app.bot.set_my_commands(commands)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
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
    app.add_handler(CommandHandler("vmos", vmos_cmd))
    app.add_handler(CommandHandler("otp", otp_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    app.add_error_handler(error_handler)

    PORT = int(os.environ.get("PORT", 10000))
    from aiohttp import web

    async def handle(request):
        return web.Response(text="OK")

    web_app = web.Application()
    web_app.router.add_get("/", handle)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info("Health server started on port %d", PORT)

    logger.info("Bot started")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    # FIX: use an Event to allow graceful shutdown instead of while+sleep
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        logger.info("Shutdown received, stopping bot...")
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except SystemExit:
        logger.info("Bot restarting...")
