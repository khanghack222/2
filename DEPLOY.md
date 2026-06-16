# Deploy bot 24/7 lên Render (miễn phí)

Bot này có sẵn health server (cổng `$PORT`) nên chạy được dạng **Web Service** free của Render, tự restart khi sập.

## Bước 1 — Tạo khóa mã hóa mật khẩu (PASS_KEY)

Mật khẩu giờ được mã hóa. Trên Render ổ đĩa **không lưu vĩnh viễn**, nên phải đặt `PASS_KEY` qua biến môi trường, nếu không mỗi lần redeploy sẽ mất mật khẩu đã lưu.

Tạo khóa (chạy 1 lần ở máy):

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Copy chuỗi in ra (dạng `xxxx...=`), dùng làm `PASS_KEY` ở bước 3.

## Bước 2 — Đẩy code lên GitHub

Code đã ở `github.com/khanghack222/2`. Đảm bảo đã push nhánh `main`.

## Bước 3 — Tạo service trên Render

1. Vào https://render.com → đăng nhập bằng GitHub.
2. **New → Web Service** → chọn repo `khanghack222/2`.
3. Render tự đọc `render.yaml`. Nếu hỏi tay thì điền:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python bot.py`
   - **Plan:** Free
4. Mục **Environment** thêm các biến:
   | Key | Value |
   |-----|-------|
   | `BOT_TOKEN` | token bot Telegram của bạn |
   | `ADMIN_ID` | Telegram id của bạn (cho /restart) |
   | `PASS_KEY` | khóa Fernet tạo ở Bước 1 |
5. **Create Web Service** → đợi build xong là bot chạy.

## Lưu ý

- **Render free ngủ sau 15 phút không có request.** Bot Telegram vẫn polling nên thường giữ tiến trình sống, nhưng nếu bị ngủ, dùng dịch vụ ping (vd UptimeRobot) ping URL Render mỗi 10 phút cho chắc.
- **Ổ đĩa free không bền:** `reminders.json` và `passwords.enc` có thể mất khi redeploy. `PASS_KEY` qua env giúp mật khẩu cũ vẫn giải mã được *nếu* file `.enc` còn; muốn bền thật thì nâng cấp Persistent Disk (trả phí) hoặc chuyển sang DB.
- Đặt env, **không** commit `pass.key` / `.env` (đã gitignore).

## Chạy ở máy (local)

```bash
pip install -r requirements.txt
export BOT_TOKEN="123:abc"
export ADMIN_ID="your_id"
# PASS_KEY tùy chọn; nếu bỏ trống, bot tự tạo file pass.key
python bot.py
```
