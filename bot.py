import logging
import asyncio
import re
import datetime
import json
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN", "PASTE_BOT_TOKEN_HERE")
ADMIN_ID = int(os.environ["ADMIN_ID"]) if "ADMIN_ID" in os.environ else None
DATA_FILE = "reminders.json"
PASSWORDS_FILE = "passwords.json"
START_TIME = datetime.datetime.now()


def load_reminders():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}


def save_reminders(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


reminders = load_reminders()


def load_passwords():
    if os.path.exists(PASSWORDS_FILE):
        with open(PASSWORDS_FILE, "r") as f:
            return json.load(f)
    return {}


def save_passwords(data):
    with open(PASSWORDS_FILE, "w") as f:
        json.dump(data, f, indent=2)


passwords = load_passwords()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "Chào bạn! Tôi là bot cá nhân của bạn.\n\n"
        "Lệnh:\n"
        "/remind <giây> <nội dung> - Đặt nhắc nhở\n"
        "/list - Xem danh sách nhắc nhở\n"
        "/cancel <id> - Hủy nhắc nhở\n"
        "/dictionary <từ> - Tra từ điển\n"
        "/weather <thành phố> - Xem thời tiết\n"
        "/ip - Check IP + vị trí\n"
        "/password <số> - Tạo & lưu mật khẩu\n"
        "/passwords - Xem pass đã lưu\n"
        "/editpass <id> <mk> - Sửa pass\n"
        "/delpass <id> - Xóa pass\n"
        "/proxy - Random proxy\n"
        "/code <ext> - Ảnh code đẹp\n"
        "/screenshot <url> - Chụp web\n"
        "/help - Hướng dẫn"
    )
    await update.message.reply_text(msg)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "/remind 60 Mua sữa - Nhắc sau 60s\n"
        "/remind 3600 Họp lúc 10h - Nhắc sau 1h\n"
        "/list - Xem danh sách nhắc nhở\n"
        "/cancel 1 - Hủy nhắc nhở số 1\n"
        "/dictionary hello - Tra từ 'hello'\n"
        "/weather hanoi - Xem thời tiết Hà Nội\n"
        "/ip - IP + vị trí\n"
        "/password 16 <tên> - Tạo & lưu mật khẩu\n"
        "/passwords - Xem mật khẩu đã lưu\n"
        "/editpass <id> <mk mới> - Sửa mật khẩu\n"
        "/delpass <id> - Xóa mật khẩu\n"
        "/proxy - Random proxy\n"
        "/code py - Nhập code nhận ảnh đẹp\n"
        "/screenshot https://... - Chụp ảnh web"
    )
    await update.message.reply_text(msg)


async def remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        seconds = int(context.args[0])
        content = " ".join(context.args[1:]) if len(context.args) > 1 else "Nhắc nhở!"
        if seconds < 5:
            await update.message.reply_text("Tối thiểu 5 giây.")
            return

        user_id = str(update.effective_user.id)
        if user_id not in reminders:
            reminders[user_id] = []
        rid = len(reminders[user_id]) + 1
        reminders[user_id].append({"id": rid, "content": content, "seconds": seconds})
        save_reminders(reminders)

        await update.message.reply_text(f" Đã đặt nhắc nhở #{rid}: '{content}' sau {seconds}s")

        async def remind_task():
            await asyncio.sleep(seconds)
            await update.effective_user.send_message(f"⏰ Nhắc nhở #{rid}: {content}")
            if user_id in reminders:
                reminders[user_id] = [r for r in reminders[user_id] if r["id"] != rid]
                save_reminders(reminders)

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
            save_reminders(reminders)
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

    import urllib.request
    import urllib.parse
    import json as json_lib

    try:
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{urllib.parse.quote(word)}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json_lib.loads(resp.read().decode())

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
        await update.message.reply_text(f"Không tìm thấy từ '{word}' hoặc lỗi API.")


async def weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = " ".join(context.args)
    if not city:
        await update.message.reply_text("Nhập thành phố. Ví dụ: /weather hanoi")
        return

    import urllib.request
    import json as json_lib

    try:
        url = f"https://wttr.in/{city}?format=%C|%t|%h|%w|%p"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
        parts = raw.split("|")
        if len(parts) >= 5:
            msg = (
                f" Thời tiết {city.capitalize()}:\n"
                f"Trạng thái: {parts[0]}\n"
                f"Nhiệt độ: {parts[1]}\n"
                f"Độ ẩm: {parts[2]}\n"
                f"Gió: {parts[3]}\n"
                f"Mưa: {parts[4]}"
            )
        else:
            msg = f"Không có dữ liệu cho '{city}'."
        await update.message.reply_text(msg)
    except Exception:
        await update.message.reply_text(f"Không tìm thấy thành phố '{city}'.")


async def ip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import urllib.request
    import json as json_lib
    try:
        req = urllib.request.Request("http://ip-api.com/json/", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json_lib.loads(resp.read().decode())
        msg = (
            f"IP: {data.get('query')}\n"
            f"Quốc gia: {data.get('country')}\n"
            f"Thành phố: {data.get('city')}\n"
            f"ISP: {data.get('isp')}\n"
            f"Lat/Lon: {data.get('lat')}, {data.get('lon')}"
        )
        await update.message.reply_text(msg)
    except Exception:
        await update.message.reply_text("Lỗi lấy thông tin IP.")


async def password_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import secrets
    import string
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
    await update.message.reply_text("Danh sách mật khẩu:\n" + "\n".join(lines), parse_mode="Markdown")


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


async def proxy_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import urllib.request
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
            except:
                continue
        import random as rnd
        if proxies:
            p = rnd.choice(proxies)
            await update.message.reply_text(f"Proxy ngẫu nhiên:\n`{p}`", parse_mode="Markdown")
        else:
            await update.message.reply_text("Không lấy được proxy.")
    except Exception:
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
    import urllib.request
    import urllib.parse
    import json as json_lib
    text = update.message.text
    lang_map = {
        "py": "python", "js": "javascript", "ts": "typescript",
        "java": "java", "cpp": "cpp", "html": "html", "css": "css",
        "go": "go", "rust": "rust", "php": "php", "c": "c",
    }
    lang = lang_map.get(ext, ext)
    try:
        data = json_lib.dumps({
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
    except Exception:
        await update.message.reply_text("Lỗi tạo ảnh code. Thử lại sau.")
    return True


async def screenshot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = " ".join(context.args)
    if not url:
        await update.message.reply_text("Nhập URL. Ví dụ: /screenshot https://google.com")
        return
    if not url.startswith("http"):
        url = "https://" + url
    import urllib.request
    import urllib.parse
    import json as json_lib
    try:
        api_url = f"https://api.microlink.io/?url={urllib.parse.quote(url)}&screenshot=true"
        req = urllib.request.Request(api_url, headers={"User-Agent": "curl/8.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json_lib.loads(resp.read().decode())
        img_url = data.get("data", {}).get("screenshot", {}).get("url")
        if not img_url:
            await update.message.reply_text("Không thể chụp ảnh.")
            return
        req2 = urllib.request.Request(img_url, headers={"User-Agent": "curl/8.0"})
        with urllib.request.urlopen(req2, timeout=30) as resp:
            img_data = resp.read()
        await update.message.reply_photo(photo=img_data, caption=f"Screenshot: {url}")
    except Exception:
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
    logger.warning(f"Update {update} caused error {context.error}")


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import platform, sys, subprocess, os as os_module

    uptime = datetime.datetime.now() - START_TIME
    days = uptime.days
    hours, rem = divmod(uptime.seconds, 3600)
    minutes, _ = divmod(rem, 60)
    total_users = len(set(list(reminders.keys()) + list(passwords.keys())))
    total_reminders = sum(len(v) for v in reminders.values())
    total_passwords = sum(len(v) for v in passwords.values())

    git_hash = ""
    try:
        git_hash = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()
    except Exception:
        git_hash = "N/A"

    memory = "N/A"
    try:
        if os_module.name == "nt":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            cachel = ctypes.c_size_t()
            total = ctypes.c_size_t()
            free = ctypes.c_size_t()
            kernel32.GetNativeSystemInfo(ctypes.byref(ctypes.c_int(0)))
            kernel32.GlobalMemoryStatusEx(ctypes.byref(ctypes.c_int(0)))
            memory = "xem qua Task Manager"
        else:
            with open("/proc/meminfo") as f:
                mem = f.read()
            for line in mem.splitlines():
                if line.startswith("MemAvailable:"):
                    kb = int(line.split()[1])
                    memory = f"{kb // 1024}MB"
                    break
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


VAN_BLACKLIST_FILE = "van_blacklist.json"


def load_van_blacklist():
    if os.path.exists(VAN_BLACKLIST_FILE):
        with open(VAN_BLACKLIST_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_van_blacklist(data):
    with open(VAN_BLACKLIST_FILE, "w") as f:
        json.dump(list(data), f, indent=2)


async def van_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import urllib.request, re, random, html as html_mod
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
            blacklist = set()
            available = essays
        essay_url = random.choice(available)
        blacklist.add(essay_url)
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

        content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL)
        content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL)
        content = re.sub(r'<div class="(pre|nxt)-btn">.*?</div>', '', content, flags=re.DOTALL)
        content = re.sub(r'<div class="social-btn.*?</div>', '', content, flags=re.DOTALL)
        content = re.sub(r'<ul class="box-new-title">.*?</ul>', '', content, flags=re.DOTALL)
        content = re.sub(r'<div class="(?:box-new|vj-toc|ads_ads|ads_txt).*?</div>', '', content, flags=re.DOTALL)
        content = re.sub(r'<div[^>]*class="[^"]*bottom(?:google)?ad[^"]*"[^>]*>.*?</div>', '', content, flags=re.DOTALL)

        # Split into sections by anchor tags, keep only essay sections (skip dany/outline)
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
            if current_is_dany:
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
    except Exception:
        await update.message.reply_text("Lỗi lấy bài văn.")


async def translate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Nhập văn bản. VD: /translate hello world")
        return
    import urllib.request, urllib.parse
    try:
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=vi&dt=t&q={urllib.parse.quote(text)}"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
        result = json.loads(raw)
        translated = result[0][0][0]
        await update.message.reply_text(f"Bản dịch: {translated}")
    except Exception:
        await update.message.reply_text("Lỗi dịch.")


async def shorten_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = " ".join(context.args)
    if not url:
        await update.message.reply_text("Nhập URL. VD: /shorten https://example.com")
        return
    import urllib.request, urllib.parse
    try:
        api = f"https://tinyurl.com/api-create.php?url={urllib.parse.quote(url)}"
        req = urllib.request.Request(api, headers={"User-Agent": "curl/8.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            short = resp.read().decode("utf-8").strip()
        await update.message.reply_text(f"Link rút gọn: {short}")
    except Exception:
        await update.message.reply_text("Lỗi rút gọn link.")


async def qr_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Nhập nội dung. VD: /qr https://google.com")
        return
    import urllib.request, urllib.parse
    try:
        url = f"https://api.qrserver.com/v1/create-qr-code/?size=400x400&data={urllib.parse.quote(text)}"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            img = resp.read()
        await update.message.reply_photo(photo=img, caption="QR Code")
    except Exception:
        await update.message.reply_text("Lỗi tạo QR.")


async def crypto_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import urllib.request
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
    except Exception:
        await update.message.reply_text("Lỗi lấy giá crypto.")


async def joke_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import urllib.request, urllib.parse
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
        translated = "".join(part[0] for part in tdata[0])
        await update.message.reply_text(translated)
    except Exception:
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
    import sys
    sys.exit(0)


async def calc_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    expr = " ".join(context.args)
    if not expr:
        await update.message.reply_text("Nhập biểu thức. VD:\n/calc 1+1\n/calc 2x3 (x = nhân)\n/calc 6:2 (: = chia)")
        return
    import math
    try:
        expr = expr.replace("x", "*").replace("X", "*").replace(":", "/")
        allowed = {"abs": abs, "round": round, "int": int, "float": float, "str": str, "len": len, "min": min, "max": max, "sum": sum, "pow": pow, "math": math}
        result = eval(expr, {"__builtins__": {}}, allowed)
        await update.message.reply_text(f"= {result}")
    except Exception:
        await update.message.reply_text("Lỗi tính toán.")


async def anime_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("Nhập tên anime. VD: /anime one piece")
        return
    import urllib.request, urllib.parse
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
    except Exception:
        await update.message.reply_text("Lỗi tra anime.")


async def meme_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import urllib.request, random
    try:
        subreddits = ["vozmemes", "VietNamMeme", "VietnameseMemes"]
        sub = random.choice(subreddits)
        url = f"https://www.reddit.com/r/{sub}/random.json"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        # Reddit returns a list with one element for random endpoint
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
    except Exception:
        await update.message.reply_text("Lỗi lấy meme.")


async def vmos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import urllib.request, json, random, re, html as html_mod
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    gm = "https://api.guerrillamail.com/ajax.php"

    msg = await update.message.reply_text("⏳ Tạo email tạm...")
    try:
        r = json.loads(urllib.request.urlopen(urllib.request.Request(f"{gm}?f=get_email_address", headers={"User-Agent": ua}), timeout=15).read().decode())
        email = (r if isinstance(r, dict) else {}).get("email_addr", "")
        sid = (r if isinstance(r, dict) else {}).get("sid_token", "")
        if not email:
            await msg.edit_text("❌ Không tạo được email"); return

        pw = str(random.randint(10000, 99999))
        await msg.edit_text(
            f"📧 `{email}`\n🔑 `{pw}`\n\n"
            f"1️⃣ Mở https://cloud.vmoscloud.com/buy\n"
            f"2️⃣ Nhập email + pass trên → gửi mã\n"
            f"3️⃣ **Kéo mảnh ghép captcha**\n\n"
            f"🔄 Bot đang chờ mail... (tối đa 2p)")

        for i in range(40):
            await asyncio.sleep(3)
            try:
                r = json.loads(urllib.request.urlopen(urllib.request.Request(f"{gm}?f=get_email_list&sid_token={sid}", headers={"User-Agent": ua}), timeout=10).read().decode())
                msgs = (r if isinstance(r, dict) else {}).get("list", [])
                if not msgs:
                    if i > 0 and i % 4 == 0:
                        await msg.edit_text(f"📧 `{email}` | ⏳ {(i+1)*3}s...\n👉 Giải captcha ở cloud.vmos.com xong chưa?")
                    continue
                d = json.loads(urllib.request.urlopen(urllib.request.Request(f"{gm}?f=fetch_email&email_id={msgs[0].get('mail_id','')}&sid_token={sid}", headers={"User-Agent": ua}), timeout=10).read().decode())
                body = html_mod.unescape((d if isinstance(d, dict) else {}).get("mail_body", "") or "")
                codes = re.findall(r'\b\d{6}\b', body)
                if codes:
                    otp = codes[0]
                    await msg.edit_text(f"✅ Có mã `{otp}`\n⏳ Đang reg + trial...")
                    bx = "https://api.vmoscloud.com/vcpcloud/api"
                    hd = {"Content-Type": "application/json", "User-Agent": ua, "requestsource": "wechat-miniapp", "clientType": "web", "appVersion": "3.6.1401"}
                    for b in [
                        {"email": email, "password": pw, "confirmPassword": pw, "verifyCode": otp},
                        {"email": email, "password": pw, "confirmPassword": pw},
                        {"mobilePhone": email, "password": pw, "confirmPassword": pw, "verifyCode": otp},
                    ]:
                        try:
                            r = urllib.request.urlopen(urllib.request.Request(f"{bx}/user/register", data=json.dumps(b).encode(), headers=hd, method="POST"), timeout=10)
                            reg = json.loads(r.read().decode())
                            rd = reg if isinstance(reg, dict) else (reg[0] if isinstance(reg, list) and reg else {})
                            if rd.get("code") == 200:
                                try:
                                    t = urllib.request.urlopen(urllib.request.Request(f"{bx}/order/create", data=json.dumps({"email": email, "type": 1}).encode(), headers=hd, method="POST"), timeout=10)
                                    tj = json.loads(t.read().decode())
                                    td = tj if isinstance(tj, dict) else {}
                                    await msg.edit_text(f"🎉 **Acc VMOS**\n📧 `{email}`\n🔑 `{pw}`\n{'✅ Trial' if td.get('code')==200 else '❌ '+str(td.get('msg',''))[:30]}")
                                except:
                                    await msg.edit_text(f"🎉 **Acc VMOS**\n📧 `{email}`\n🔑 `{pw}`\n✅ Reg OK")
                                return
                        except: pass
                    await msg.edit_text(f"✅ Có mã `{otp}` nhưng reg lỗi\n📧 `{email}`\n🔑 `{pw}`\n👉 Reg tay: cloud.vmos.com")
                    return
            except: pass
        await msg.edit_text(f"❌ Hết giờ\n📧 `{email}`\n🔑 `{pw}`\n📬 https://www.guerrillamail.com/")
    except Exception as e:
        try: await msg.edit_text(f"❌ {str(e)[:200]}")
        except: pass


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
        BotCommand("vmos", "Tạo VMOS Cloud trial"),
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
    app.add_handler(CommandHandler("vmos", vmos_cmd))
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
    print(f"Health server on port {PORT}")

    print("Bot đang chạy...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
