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
DATA_FILE = "reminders.json"
PASSWORDS_FILE = "passwords.json"


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
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
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
    try:
        api_url = f"https://api.screenshotlayer.com/api/capture?access_key=free&url={urllib.parse.quote(url)}&viewport=1280x720&width=1024"
        req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    app.add_error_handler(error_handler)

    await asyncio.gather(health_server(), run_bot(app))


if __name__ == "__main__":
    asyncio.run(main())
