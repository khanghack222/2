import logging
import asyncio
import re
import datetime
import json
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
    import random
    jokes = [
        "Một anh chàng hỏi bạn:\n- Sao mặt mày buồn thế?\n- Tao vừa bị vợ đuổi ra khỏi nhà.\n- Sao lại thế?\n- Nó bảo tao chỉ biết ăn với ngủ như con heo.\n- Thế thì có gì mà buồn?\n- Tao bảo: ừ thì tao là heo thật đấy, nhưng heo cũng biết yêu mà!",
        "Vợ hỏi chồng:\n- Anh ơi, anh có yêu em không?\nChồng:\n- Yêu chứ! Em là ánh sáng của cuộc đời anh.\nVợ (cười):\n- Thế sao hôm qua anh bảo anh bị mù?\nChồng: ...",
        "Cô giáo hỏi học sinh:\n- Em hãy cho cô biết bố mẹ em làm nghề gì?\nHọc sinh:\n- Bố em là bác sĩ, mẹ em là nội trợ ạ.\nCô giáo:\n- Thế còn em, em muốn làm gì khi lớn lên?\nHọc sinh:\n- Em muốn làm... bệnh nhân của bố ạ!",
        "Một anh nông dân ra chợ mua một con vịt. Anh ta hỏi:\n- Con vịt này bao nhiêu?\nNgười bán:\n- 100 nghìn.\n- Sao đắt thế? Tôi mua có 50 nghìn thôi.\n- Vịt ngon, vịt to thế này cơ mà.\n- Ngon thì ngon thật, nhưng mà nó cứ nhìn tôi như kiểu quen nhau ấy.\nNgười bán nhìn con vịt rồi nói:\n- À, thì ra là vịt nhà anh đây mà!",
        "Bác sĩ bảo bệnh nhân:\n- Tôi có tin vui và tin buồn.\nBệnh nhân:\n- Tin buồn là gì?\n- Ông chỉ còn sống được 24 tiếng nữa thôi.\n- Á! Thế tin vui là gì?\n- Tôi có hẹn với ông vào ngày mai... mà quên mất!",
        "Hai người bạn nói chuyện:\n- Tao mới mua một con chó thông minh lắm mày ạ.\n- Thông minh cỡ nào?\n- Hôm qua tao bảo nó: đi mua bia cho tao. Nó liền chạy đi.\n- Ồ, thế bia đâu?\n- Nó chạy đi mất tiêu rồi, chắc vẫn đang tìm tiền đâu đó.",
        "Cô gái hỏi người yêu:\n- Anh ơi, bố mẹ anh có thích em không?\n- Có chứ, bố mẹ anh bảo em hiền lành, dễ thương.\n- Thế mà sao hôm qua em thấy bố anh lắc đầu khi nhìn em?\n- À, bố anh bị rụng tóc, ông ấy lắc đầu để kiểm tra tóc còn rụng không thôi.",
        "Ông chồng khoe với bạn:\n- Vợ tôi nấu ăn ngon lắm! Hôm nào anh đến ăn thử.\n- Thế vợ anh nấu món gì ngon nhất?\n- Mì tôm.\n- ... Thế còn món gì nữa?\n- Mì tôm trứng.\n- ...",
        "Một anh chàng vào quán phở:\n- Cho tô phở bò tái.\n- Vâng, có ngay.\nSau khi ăn xong:\n- Tính tiền!\n- 50 nghìn ạ.\nAnh ta móc túi:\n- Ủa, tôi quên mang ví.\n- Thế anh định trả bằng gì?\n- Bằng... nụ cười được không?\n- Được thôi, anh cười đi.\nAnh ta cười:\n- Hà hà!\nChủ quán:\n- Anh còn nợ tôi 50 nghìn nụ cười nữa.",
        "Vova học tiếng Anh:\nCô giáo hỏi:\n- Em hãy dịch câu: 'I love you' sang tiếng Việt.\nVova:\n- Anh yêu em ạ.\n- Giỏi lắm! Thế 'I like you' là gì?\n- Em thích anh.\n- Tốt! Thế 'I miss you'?\nVova suy nghĩ:\n- Em... nhớ anh?\n- Xuất sắc! Thế 'I eat rice'?\nVova:\n- Em... ăn cơm?\n- Ừ, thế 'I go to school'?\nVova:\n- Em đi học?\nCô giáo bực mình:\n- Sao em cứ thêm 'em' vào hết thế?\nVova:\n- Thế không phải cô đang dạy em là phải thêm chủ ngữ vào à? Mà em là con trai, sao toàn phải làm 'em' thế?",
        "Một người đàn ông đi khám mắt:\nBác sĩ:\n- Ông bị cận thị nặng, phải đeo kính.\n- Có cách nào khác không bác sĩ?\n- Có, ông có thể tập nhìn xa.\n- Tập thế nào?\n- Mỗi ngày nhìn ra xa 30 phút, sau 6 tháng sẽ đỡ.\nSau 6 tháng, ông ta quay lại:\n- Bác sĩ ơi, tôi vẫn không thấy đường.\n- Thế ông có tập nhìn xa không?\n- Có chứ! Tôi nhìn vào tài khoản ngân hàng của tôi mỗi ngày!",
        "Anh chàng nọ vào cửa hàng bánh:\n- Cho tôi cái bánh kem.\n- Bánh kem có kem tươi ở trên.\n- Thế cho tôi cái không kem.\n- Không có kem là bánh mì không.\n- Thế cho tôi cái bánh mì không.\n- Bánh mì không là 5 nghìn.\n- Đắt thế? Ở kia có 3 nghìn.\n- Thế sao anh không ra kia mua?\n- Ở kia hết bánh rồi.\n- Khi nào hết thì mới đắt chứ!",
        "Cô gái nói với bạn trai:\n- Anh ơi, em muốn hỏi anh một câu.\n- Em hỏi đi.\n- Nếu em và mẹ anh rơi xuống sông, anh cứu ai trước?\n- Anh cứu em.\n- Ôi! Thật á? Tại sao?\n- Vì mẹ anh biết bơi từ nhỏ rồi.",
        "Ông chồng đang đọc báo thì vợ hỏi:\n- Anh ơi, em mập hơn hồi cưới phải không?\nChồng (không ngước lên):\n- Ừ, hơi hơi.\nVợ:\n- Anh nói thế là ý gì? Anh chê em à?\nChồng (vẫn đọc báo):\n- Không, anh chỉ trả lời thôi mà.\nVợ:\n- Thế tại sao hồi cưới anh bảo em đẹp nhất?\nChồng:\n- Thì hồi đó anh mới bị cận mà chưa có kính.",
        "Sếp hỏi nhân viên:\n- Sao tháng nào anh cũng đi muộn?\n- Thưa sếp, vì tôi đọc được một nghiên cứu nói rằng ngủ thêm 10 phút mỗi ngày sẽ kéo dài tuổi thọ thêm 3 năm.\n- Thế anh định sống bao nhiêu tuổi?\n- Tôi không biết nữa, nhưng tôi muốn kéo dài tới lúc nào sếp nghỉ hưu thì thôi.",
        "Bé Tèo hỏi bố:\n- Bố ơi, sao con phải đi học?\nBố:\n- Để sau này con lớn lên làm người có ích.\nTèo:\n- Thế bố đi học chưa?\nBố:\n- Bố học rồi.\nTèo:\n- Sao bố không làm người có ích?\nBố: ...",
        "Một anh chàng đứng trước gương ngắm mình:\n- Trời ơi, mình đẹp trai quá!\nVợ anh ta từ trong bếp nói vọng ra:\n- Đừng có tự lừa dối bản thân như thế!\nChồng:\n- Ai bảo em thế? Anh chỉ nói sự thật thôi.\nVợ:\n- Sự thật là anh đang nói chuyện với cái gương đấy à?",
    ]
    await update.message.reply_text(random.choice(jokes))


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


async def run_bot(app):
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    print("Bot đang chạy...")
    while True:
        await asyncio.sleep(3600)


async def health_server():
    from aiohttp import web
    PORT = int(os.environ.get("PORT", 10000))

    async def handle(request):
        return web.Response(text="OK")

    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"Health server on port {PORT}")


async def main():
    app = Application.builder().token(TOKEN).build()

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
    app.add_handler(CommandHandler("shorten", shorten_cmd))
    app.add_handler(CommandHandler("qr", qr_cmd))
    app.add_handler(CommandHandler("crypto", crypto_cmd))
    app.add_handler(CommandHandler("joke", joke_cmd))
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler("restart", restart_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    app.add_error_handler(error_handler)

    await asyncio.gather(health_server(), run_bot(app))


if __name__ == "__main__":
    asyncio.run(main())
