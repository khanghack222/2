# 🤖 Bot Terminal — Telegram Multi-Function Bot

> **All-in-one Telegram bot** với 40+ lệnh: AI Chatbot, TikTok Downloader, Thời tiết, Từ điển, Mật khẩu, Nhắc nhở, Crypto, Tỷ giá, Văn mẫu, Meme, QR Code, Proxy, và nhiều hơn nữa.

[![Python](https://img.shields.io/badge/Python-3.12+-blue?logo=python)](https://python.org)
[![Telegram Bot](https://img.shields.io/badge/Telegram-Bot-0088CC?logo=telegram)](https://core.telegram.org/bots)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker)](https://docker.com)

---

## 📑 Mục lục

- [🚀 Tính năng](#-tính-năng)
- [📦 Cấu trúc dự án](#-cấu-trúc-dự-án)
- [⚡ Quick Start (Local)](#-quick-start-local)
- [🐳 Docker Deployment](#-docker-deployment)
- [☁️ Deploy lên Render](#️-deploy-lên-render)
- [🤖 Hugging Face Spaces](#-hugging-face-spaces)
- [🔐 Bảo mật](#-bảo-mật)
- [📊 Dashboard Web](#-dashboard-web)
- [🧪 Testing](#-testing)
- [📋 Danh sách lệnh](#-danh-sách-lệnh)
- [❓ FAQ](#-faq)

---

## 🚀 Tính năng

| Nhóm | Lệnh | Mô tả |
|------|------|-------|
| **🤖 AI Chatbot** | `/ask` | Hỏi AI (Groq/OpenAI — **miễn phí**) |
| **🎵 TikTok** | `/tiktok`, `/tiktok_profile`, `/tiktok_trending`, `/tiktok_search`, `/tiktok_seo`, `/tiktok_hashtag`, `/tiktok_auto` | Download, tra cứu, SEO, auto-post |
| **🌤 Tiện ích** | `/weather`, `/translate`, `/shorten`, `/qr`, `/ip`, `/screenshot` | Thời tiết, dịch, rút gọn link, QR code |
| **🛠 Công cụ** | `/code`, `/calc`, `/password`, `/passwords`, `/proxy`, `/bypass` | Code→ảnh, máy tính, quản lý mật khẩu, proxy |
| **🎭 Giải trí** | `/joke`, `/anime`, `/meme` | Joke dịch T-V, tra anime, meme Reddit |
| **📚 Học tập** | `/van`, `/dictionary`, `/wiki` | Văn mẫu lớp 8, từ điển Anh-Việt, Wikipedia |
| **💰 Tài chính** | `/crypto`, `/tygia` | Giá BTC/ETH/SOL, tỷ giá ngoại tệ→VND |
| **📅 Lịch & Nhắc nhở** | `/lich`, `/remind`, `/list`, `/cancel` | Lịch âm Việt Nam, nhắc nhở |
| **📊 Thống kê** | `/stats`, `/myusage` | Thống kê sử dụng bot |
| **ℹ️ Hệ thống** | `/id`, `/status`, `/help`, `/start` | Thông tin user, trạng thái, menu tương tác |

> 💡 **Menu tương tác:** Gõ `/start` → menu inline keyboard → bấm chọn danh mục.

---

## 📦 Cấu trúc dự án

```
telegram_bot/
├── bot.py                  # 🧠 Main bot — all handlers + logic
├── ai_chat.py              # 🤖 AI Chat (Groq / OpenAI)
├── database.py             # 🗄️ SQLite async database
├── dashboard.py            # 📊 Web Dashboard (aiohttp)
├── tests.py                # 🧪 Unit tests (pytest)
│
├── requirements.txt        # 📦 Python dependencies
├── Dockerfile              # 🐳 Multi-stage Docker build
├── docker-compose.yml      # 🐳 Docker Compose (dev + prod)
├── .dockerignore           # 🚫 Exclude files from build context
│
├── DEPLOY.md               # 📄 Render deployment guide
├── README.md               # 📖 File này
│
├── Procfile                # ☁️ Render Procfile
├── render.yaml             # ☁️ Render Blueprint config
│
├── run.bat                 # 🪟 Windows auto-restart wrapper
├── run.sh                  # 🐧 Linux auto-restart wrapper
│
├── .gitignore              # 🙈 Git ignores
├── .env                    # 🔐 Local env vars (KHÔNG commit)
│
├── _fx.py                  # 🔧 Fix utility (internal)
├── _fix_fstrings.py        # 🔧 Fix utility (internal)
│
└── data/                   # 📂 Persistent data (volume mount)
    ├── reminders.json      #    Nhắc nhở
    ├── passwords.enc       #    Mật khẩu (mã hóa)
    ├── pass.key            #    Khóa mã hóa (local)
    └── van_blacklist.json  #    Blacklist văn mẫu
```

---

## ⚡ Quick Start (Local)

```bash
# 1. Clone & cd
cd telegram_bot

# 2. Tạo virtual environment
python -m venv .venv
.venv\Scripts\activate   # Windows
source .venv/bin/activate # Linux/Mac

# 3. Cài dependencies
pip install -r requirements.txt

# 4. Tạo file .env
#    BOT_TOKEN là bắt buộc!

# 5. Chạy bot
python bot.py
```

### 🔐 Biến môi trường (`.env`)

| Biến | Bắt buộc | Mô tả |
|------|----------|-------|
| `BOT_TOKEN` | ✅ **Có** | Token bot từ [@BotFather](https://t.me/BotFather) |
| `ADMIN_ID` | ❌ Không | Telegram ID → cho phép `/restart` |
| `GROQ_API_KEY` | ❌ Không | API key Groq (miễn phí) → bật AI Chat |
| `OPENAI_API_KEY` | ❌ Không | API key OpenAI → fallback AI |
| `AI_MODEL` | ❌ Không | Model AI (mặc định: `llama-3.3-70b-versatile`) |
| `PASS_KEY` | ❌ Không | Key mã hóa mật khẩu (Fernet) |
| `PORT` | ❌ Không | Cổng web dashboard (mặc định: `10000`) |
| `DB_PATH` | ❌ Không | Đường dẫn SQLite (mặc định: `bot.db`) |

> **File `.env` mẫu:**
> ```ini
> BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
> ADMIN_ID=123456789
> GROQ_API_KEY=gsk_your_groq_key_here
> PASS_KEY=your_fernet_key_here
> PORT=10000
> ```

---

## 🐳 Docker Deployment

### Yêu cầu

- Docker Engine ≥ 24.0
- Docker Compose ≥ 2.20
- Hệ điều hành: Windows (WSL2), Linux, macOS

```bash
docker --version          # ≥ 24.0
docker compose version    # ≥ 2.20
```

### Cấu hình môi trường

Tạo file `.env` trong thư mục `telegram_bot/`:

```ini
# BẮT BUỘC
BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11

# Khuyến nghị
ADMIN_ID=123456789
GROQ_API_KEY=gsk_your_groq_key_here

# Mã hóa mật khẩu
# Tạo key: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
PASS_KEY=your_fernet_key_here

PORT=10000
```

### Build & Run

#### 🏃 Single Container (nhanh)

```bash
# Build image
docker build -t bot-terminal:latest .

# Run container
docker run -d --name bot \
  -p 10000:10000 \
  --env-file .env \
  -v bot-data:/app/data \
  --restart always \
  bot-terminal:latest

# Xem logs
docker logs -f bot

# Dừng & xóa
docker stop bot && docker rm bot
```

#### 🛠️ Development (hot-reload)

```bash
# Build + start (hot-reload)
docker compose up dev --build

# Chạy ngầm
docker compose up -d dev --build

# Logs real-time
docker compose logs -f dev

# Dừng
docker compose down
```

> **Hot-reload:** Code mount vào container → sửa code là áp dụng ngay.

#### 🚀 Production

```bash
# Build & start
docker compose up prod --build -d

# Health check
docker compose ps

# Logs
docker compose logs prod

# Dừng
docker compose down

# Xóa volume (⚠️ mất reminders, passwords)
docker compose down -v
```

### So sánh Dev vs Prod

| Tính năng | Dev | Prod |
|-----------|-----|------|
| Hot-reload | ✅ Volume mount | ❌ Image cố định |
| Non-root user | ❌ Root | ✅ User `bot` |
| Resource limits | ❌ | ✅ CPU 1.0 / RAM 512M |
| Restart policy | `unless-stopped` | `always` |
| Logs rotation | 3 × 10MB | 5 × 10MB |
| Use case | Phát triển, debug | Production, deploy |

### Troubleshooting Docker

| Vấn đề | Nguyên nhân | Giải pháp |
|--------|-------------|-----------|
| `conflict` error | Container name tồn tại | `docker compose down` hoặc `docker rm <name>` |
| `BOT_TOKEN required` | Thiếu `.env` | Kiểm tra file `.env` + `--env-file` |
| Container restart loop | Lỗi khởi động | `docker logs <container>` |
| `permission denied` | Volume permission | `chmod -R 777 data/` hoặc dùng root user |
| Port conflict | Cổng 10000 đang dùng | Đổi `PORT` trong `.env` |
| `no space left` | Hết disk | `docker system prune -a` |

---

## ☁️ Deploy lên Render

Xem hướng dẫn chi tiết tại [`DEPLOY.md`](DEPLOY.md).

Tóm tắt:
1. Push code lên GitHub
2. [render.com](https://render.com) → **New Web Service** → chọn repo
3. Build: `pip install -r requirements.txt`
4. Start: `python bot.py`
5. Thêm env vars: `BOT_TOKEN`, `ADMIN_ID`, `PASS_KEY`

---

## 🤖 Hugging Face Spaces

> Dự án `9router-hf/` chứa Dockerfile deploy lên **Hugging Face Spaces**.

```
9router-hf/
├── Dockerfile   # 🐳 HF Spaces Dockerfile
└── README.md    # 📖 Hướng dẫn deploy Spaces
```

**Cách deploy:**
1. Vào [hf.co/new-space](https://huggingface.co/new-space)
2. Chọn **Docker** (SDK) → Upload file
3. Thêm secrets: `BOT_TOKEN`, `ADMIN_ID`, `GROQ_API_KEY`, `PASS_KEY`
4. Deploy → Bot chạy trên Spaces (cổng 7860)

---

## 🔐 Bảo mật

| Tính năng | Chi tiết |
|-----------|----------|
| **Mật khẩu mã hóa** | Fernet (`cryptography`) — lưu `.enc` thay vì `.json` |
| **Password Generator** | Dùng `secrets` (không phải `random`) — cryptographically secure |
| **Safe Eval** | Whitelist AST nodes, block attribute access → chặn sandbox escape |
| **Rate Limiting** | 3-10s per user/command tuỳ loại |
| **Input Validation** | URL auto-add `https://`, whitelist chars cho calculator |
| **Non-root Docker** | Prod image chạy user `bot` |
| **.dockerignore** | Ngăn secret file bake vào image |

> ⚠️ **KHÔNG commit:** `.env`, `pass.key`, `*.enc`, `*.json` (đã có `.gitignore`)

---

## 📊 Dashboard Web

Bot tích hợp web dashboard trên cổng `$PORT` (mặc định 10000):

| URL | Mô tả |
|-----|-------|
| `http://localhost:10000/` | Dashboard HTML |
| `http://localhost:10000/dashboard` | Dashboard (alias) |
| `http://localhost:10000/api/stats` | JSON API thống kê |
| `http://localhost:10000/api/health` | Health check endpoint |
| `http://localhost:10000/health` | Simple health check |

Dashboard hiển thị: Tổng lệnh, lệnh hôm nay, user, nhắc nhở, mật khẩu, top commands, top users, recent errors.

---

## 🧪 Testing

```bash
# Chạy tests
python -m pytest tests.py -v

# Coverage
pip install pytest-cov
python -m pytest tests.py --cov=bot --cov-report=term-missing

# Trong Docker
docker compose run --rm dev python -m pytest tests.py -v
```

**Tests bao gồm:** Safe eval (sandbox + escape attempts), JSON persistence (load/save/corrupt), Van blacklist CRUD, Password CRUD, Reminder logic/bounds, URL validation, Config validation, Translate parser, Crypto parsing.

---

## 📋 Danh sách lệnh

<details>
<summary><b>🌤 Tiện ích</b></summary>

| Lệnh | Ví dụ | Mô tả |
|------|-------|-------|
| `/weather` | `/weather hanoi` | Thời tiết (Open-Meteo) |
| `/translate` | `/translate hello` | Dịch → tiếng Việt |
| `/shorten` | `/shorten https://ex.com` | Rút gọn link (TinyURL) |
| `/qr` | `/qr https://google.com` | Tạo QR code |
| `/ip` | `/ip` | IP + vị trí |
| `/screenshot` | `/screenshot https://google.com` | Chụp ảnh web |
</details>

<details>
<summary><b>🛠 Công cụ</b></summary>

| Lệnh | Ví dụ | Mô tả |
|------|-------|-------|
| `/code` | `/code py` | Code → ảnh đẹp |
| `/calc` | `/calc 2+2*pi` | Máy tính an toàn |
| `/password` | `/password 16 email` | Tạo & lưu mật khẩu |
| `/passwords` | `/passwords` | DS mật khẩu |
| `/editpass` | `/editpass 1 abc123` | Sửa mật khẩu |
| `/delpass` | `/delpass 1` | Xoá mật khẩu |
| `/proxy` | `/proxy 5` | Proxy miễn phí |
| `/bypass` | `/bypass https://shorturl.at/...` | Bypass link rút gọn |
</details>

<details>
<summary><b>🎭 Giải trí</b></summary>

| Lệnh | Ví dụ | Mô tả |
|------|-------|-------|
| `/joke` | `/joke` | Chuyện cười (dịch T-V) |
| `/anime` | `/anime one piece` | Tra anime (Jikan API) |
| `/meme` | `/meme` | Meme Reddit |
</details>

<details>
<summary><b>📚 Học tập</b></summary>

| Lệnh | Ví dụ | Mô tả |
|------|-------|-------|
| `/van` | `/van` | Văn mẫu lớp 8 |
| `/dictionary` | `/dictionary hello` | Từ điển Anh-Việt |
| `/wiki` | `/wiki Vietnam` | Wikipedia |
</details>

<details>
<summary><b>💰 Tài chính</b></summary>

| Lệnh | Ví dụ | Mô tả |
|------|-------|-------|
| `/crypto` | `/crypto` | Giá BTC/ETH/SOL/BNB/XRP |
| `/tygia` | `/tygia` | Tỷ giá→VND |
</details>

<details>
<summary><b>📅 Lịch & Nhắc nhở</b></summary>

| Lệnh | Ví dụ | Mô tả |
|------|-------|-------|
| `/lich` | `/lich 30/4/2026` | Lịch âm Việt Nam |
| `/remind` | `/remind 60 Mua sữa` | Đặt nhắc nhở (giây) |
| `/list` | `/list` | DS nhắc nhở |
| `/cancel` | `/cancel 1` | Huỷ nhắc nhở |
</details>

<details>
<summary><b>🤖 AI Chatbot</b></summary>

| Lệnh | Ví dụ | Mô tả |
|------|-------|-------|
| `/ask` | `/ask Python là gì?` | Hỏi AI |
| `/ask reset` | `/ask reset` | Xoá lịch sử |
</details>

<details>
<summary><b>🎵 TikTok</b></summary>

| Lệnh | Ví dụ | Mô tả |
|------|-------|-------|
| `/tiktok` | `/tiktok <url>` | Download video |
| `/tiktok_profile` | `/tiktok_profile theanh28` | Profile TikTok |
| `/tiktok_search` | `/tiktok_search mèo cute` | Tìm video |
| `/tiktok_trending` | `/tiktok_trending` | Thịnh hành |
| `/tiktok_seo` | `/tiktok_seo cách nấu phở` | Gợi ý SEO |
| `/tiktok_hashtag` | `/tiktok_hashtag học tập` | Tra hashtag |
| `/tiktok_auto` | `/tiktok_auto 30` | [Admin] Auto-post |
| `/tiktok_stop` | `/tiktok_stop` | [Admin] Dừng auto |
</details>

<details>
<summary><b>ℹ️ Hệ thống</b></summary>

| Lệnh | Ví dụ | Mô tả |
|------|-------|-------|
| `/start` | `/start` | Menu tương tác |
| `/help` | `/help` | Hướng dẫn |
| `/id` | `/id` | Thông tin bạn |
| `/status` | `/status` | Trạng thái bot |
| `/restart` | `/restart` | [Admin] Restart |
| `/stats` | `/stats` | Thống kê |
| `/myusage` | `/myusage` | Lịch sử cá nhân |
</details>

---

## ❓ FAQ

<details>
<summary><b>Làm sao có BOT_TOKEN?</b></summary>
Vào [@BotFather](https://t.me/BotFather) → `/newbot` → đặt tên → nhận token.
</details>

<details>
<summary><b>AI không hoạt động?</b></summary>
Cần set `GROQ_API_KEY`. Lấy miễn phí tại [console.groq.com](https://console.groq.com).
</details>

<details>
<summary><b>Mất dữ liệu sau restart Docker?</b></summary>
Dùng volume mount. `docker compose down -v` mới mất. Kiểm tra `docker compose ps`.
</details>

<details>
<summary><b>Render free bị sleep?</b></summary>
Polling Telegram giữ sống. Dùng UptimeRobot ping Render URL mỗi 10p cho chắc.
</details>

<details>
<summary><b>Xem log kiểu gì?</b></summary>
Docker: `docker compose logs -f prod` | Render: Dashboard→Logs | Local: terminal.
</details>

<details>
<summary><b>Mất PASS_KEY thì sao?</b></summary>
Không giải mã được `passwords.enc` cũ. Tạo key mới = mất mật khẩu cũ.
</details>

<details>
<summary><b>Safe eval là gì?</b></summary>
`/calc` dùng safe eval: chỉ cho số, phép toán, whitelist functions. Chặn attribute access → an toàn.
</details>

---

## 📄 License

MIT © 2026 Bot Terminal

---

<p align="center">
  <b>Bot Terminal</b> — <i>All-in-One Telegram Bot</i><br>
  <a href="https://github.com/khanghack222/2">GitHub</a>
</p>
