# Telegram Bot - Kiến trúc mới

Bot Telegram được thiết kế lại với kiến trúc modular, áp dụng các pattern từ 9Router.

## 🏗️ Kiến trúc

### Cấu trúc thư mục

```
telegram_bot/
├── core/                    # Framework cốt lõi
│   ├── config.py           # Quản lý cấu hình tập trung
│   ├── context.py          # Dependency Injection container
│   ├── middleware.py       # Pipeline middleware base
│   ├── middlewares.py      # Các middleware implementations
│   ├── plugin.py           # Plugin registry & auto-discovery
│   ├── menu.py             # Quản lý menu tương tác
│   └── i18n.py             # Hệ thống đa ngôn ngữ
│
├── data/                    # Data layer
│   ├── database.py         # SQLite connection & migrations
│   └── repositories.py     # Repository pattern cho data access
│
├── services/                # Business logic
│   ├── cache.py            # Cache service (LRU + TTL)
│   ├── reminder.py         # Reminder service
│   └── password.py         # Password service (Fernet encryption)
│
├── ai/                      # AI Provider system
│   ├── router.py           # Smart router + Circuit breaker
│   └── providers/          # AI provider implementations
│       ├── __init__.py
│       ├── openrouter.py   # OpenRouter provider
│       ├── groq.py         # Groq provider
│       └── openai_provider.py  # OpenAI provider
│
├── http/                    # HTTP utilities
│   └── client.py           # Async HTTP client + Health tracking
│
├── plugins/                 # Feature plugins (12 plugins)
│   ├── system.py           # /start, /help, /menu, /id, /lang
│   ├── weather.py          # /weather
│   ├── translate.py        # /translate, /dich
│   ├── dictionary.py       # /dict, /dictionary
│   ├── crypto.py           # /crypto, /price
│   ├── stock.py            # /stock
│   ├── ai_chat.py          # /ask
│   ├── reminder.py         # /remind, /reminders, /delremind
│   ├── password.py         # /password, /genpass, /mypasswords, /delpassword
│   ├── utilities.py        # /qr, /shorten, /calc
│   ├── tiktok.py           # /tiktok commands
│   ├── youtube.py          # /yt, /music
│   └── admin.py            # /kick, /ban, /unban, /mute, /unmute
│
├── i18n/                    # Translations
│   ├── vi.json             # Tiếng Việt
│   └── en.json             # English
│
├── main.py                  # Entry point
└── requirements.txt         # Dependencies
```

## 🎯 Các Pattern chính

### 1. Plugin Architecture
- Mỗi tính năng là một plugin độc lập
- Auto-discovery: tự động tìm và load plugins
- BasePlugin interface chuẩn hóa cách plugins hoạt động

### 2. Middleware Pipeline
- Chain of responsibility pattern
- Các middleware: Logging, RateLimit, ErrorHandling
- Áp dụng tự động cho tất cả commands

### 3. AI Router + Circuit Breaker
- Smart routing: chọn provider tốt nhất dựa trên health metrics
- Circuit breaker: tự động disable provider khi fail nhiều lần
- Fallback: tự động chuyển sang provider khác khi cần

### 4. Repository Pattern
- Tách biệt data access logic
- Dễ dàng test và maintain
- Hỗ trợ migrations

### 5. Dependency Injection
- AppContext chứa tất cả dependencies
- Plugins truy cập services qua context
- Dễ dàng mock trong testing

## 🚀 Cài đặt

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Cấu hình môi trường

Tạo file `.env`:

```env
# Required
BOT_TOKEN=your_bot_token_here

# Optional
ADMIN_ID=your_admin_id

# Database
DB_PATH=data/bot.db

# AI Providers (ít nhất 1)
OPENROUTER_API_KEY=your_key
GROQ_API_KEY=your_key
OPENAI_API_KEY=your_key

# Optional APIs
EXCHANGERATE_API_KEY=your_key
WEATHER_API_KEY=your_key

# Cache
CACHE_MAX_SIZE=1000
CACHE_DEFAULT_TTL=300

# Rate limiting
RATE_LIMIT_WINDOW=60
RATE_LIMIT_MAX_REQUESTS=20

# HTTP
HTTP_TIMEOUT=30
HTTP_MAX_RETRIES=3
HTTP_RETRY_DELAY=1.0
```

### 3. Chạy bot

```bash
python main.py
```

## 📦 Plugins

### System Plugin
- `/start` - Khởi động bot
- `/help` - Trợ giúp
- `/menu` - Menu tương tác
- `/id` - Thông tin user
- `/lang` - Đổi ngôn ngữ

### Weather Plugin
- `/weather <city>` - Xem thời tiết

### Translate Plugin
- `/translate <text>` - Dịch văn bản
- `/dich <text>` - Alias cho translate

### Dictionary Plugin
- `/dict <word>` - Tra từ điển
- `/dictionary <word>` - Alias cho dict

### Crypto Plugin
- `/crypto` - Giá crypto top coins
- `/price <coin>` - Giá coin cụ thể

### Stock Plugin
- `/stock <symbol>` - Giá cổ phiếu

### AI Chat Plugin
- `/ask <question>` - Hỏi AI

### Reminder Plugin
- `/remind <time> <text>` - Đặt nhắc nhở
- `/reminders` - Xem danh sách nhắc nhở
- `/delremind <id>` - Xóa nhắc nhở

### Password Plugin
- `/password <label> <password>` - Lưu mật khẩu
- `/genpass [length] [label]` - Tạo mật khẩu ngẫu nhiên
- `/mypasswords` - Xem danh sách mật khẩu
- `/delpassword <id>` - Xóa mật khẩu

### Utilities Plugin
- `/qr <text>` - Tạo QR code
- `/shorten <url>` - Rút gọn URL
- `/calc <expression>` - Máy tính

### TikTok Plugin
- `/tiktok <url>` - Tải video TikTok
- `/tiktok_profile <username>` - Xem profile
- `/tiktok_search <query>` - Tìm kiếm
- `/tiktok_trending` - Video trending

### YouTube Plugin
- `/yt <url>` - Tải video YouTube
- `/music <url>` - Tải nhạc YouTube

### Admin Plugin
- `/kick <user>` - Kick user
- `/ban <user>` - Ban user
- `/unban <user>` - Unban user
- `/mute <user>` - Mute user
- `/unmute <user>` - Unmute user

## 🧪 Testing

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=. --cov-report=html
```

## 📊 Monitoring

Bot tự động track:
- Số lượng commands đã execute
- Tỷ lệ thành công/thất bại
- Response time của các API calls
- Health của AI providers
- Cache hit rate

## 🔧 Troubleshooting

### Bot không phản hồi
- Kiểm tra BOT_TOKEN trong .env
- Xem logs để biết lỗi
- Đảm bảo đã install đủ dependencies

### AI commands không hoạt động
- Kiểm tra có ít nhất 1 AI provider API key
- Xem dashboard để kiểm tra health của providers
- Circuit breaker có thể đang mở (chờ 60s để reset)

### Database errors
- Kiểm tra DB_PATH có tồn tại
- Đảm bảo có quyền ghi vào thư mục data/
- Xem logs để biết lỗi migration

## 📝 License

MIT

## 👥 Contributing

1. Fork repository
2. Tạo feature branch
3. Commit changes
4. Push và tạo Pull Request

## 🎓 Tài liệu tham khảo

- [Design Spec](docs/superpowers/specs/2026-06-21-telegram-bot-architecture-design.md)
- [Implementation Plan](docs/superpowers/plans/2026-06-21-telegram-bot-architecture.md)
- [9Router Patterns](https://github.com/decolua/9router)
