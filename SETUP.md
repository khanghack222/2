# Hướng dẫn Setup và Chạy Bot

## Yêu cầu hệ thống

- Python 3.10+
- pip
- Git (optional)

## Các bước cài đặt

### 1. Clone/Copy project

```bash
cd C:\Users\XUAN\Desktop\telegram_bot
```

### 2. Tạo virtual environment (recommended)

```bash
# Tạo virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (Linux/Mac)
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

Nếu có lỗi với requirements.txt cũ, dùng:
```bash
pip install -r requirements_new.txt
```

### 4. Tạo file .env

Copy file `.env.example` thành `.env`:

```bash
copy .env.example .env
```

Sau đó edit file `.env` và thêm các thông tin cần thiết:

```env
# BẮT BUỘC - Lấy từ @BotFather trên Telegram
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz

# OPTIONAL - ID của admin (để dùng /kick, /ban, etc.)
ADMIN_ID=123456789

# Database
DB_PATH=data/bot.db

# AI Providers - Cần ít nhất 1 trong 3
# Lấy từ: https://openrouter.ai/keys
OPENROUTER_API_KEY=sk-or-v1-xxxxx

# Lấy từ: https://console.groq.com/keys
GROQ_API_KEY=gsk_xxxxx

# Lấy từ: https://platform.openai.com/api-keys
OPENAI_API_KEY=sk-xxxxx

# Optional APIs
EXCHANGERATE_API_KEY=  # Lấy từ: https://exchangerate-api.com/
WEATHER_API_KEY=       # Lấy từ: https://openweathermap.org/api

# Cache settings
CACHE_MAX_SIZE=1000
CACHE_DEFAULT_TTL=300

# Rate limiting
RATE_LIMIT_WINDOW=60
RATE_LIMIT_MAX_REQUESTS=20

# HTTP settings
HTTP_TIMEOUT=30
HTTP_MAX_RETRIES=3
HTTP_RETRY_DELAY=1.0
```

### 5. Tạo thư mục data

```bash
mkdir data
```

### 6. Chạy bot

```bash
python main.py
```

## Kiểm tra bot hoạt động

1. Mở Telegram
2. Tìm bot của bạn (tên bạn đặt khi tạo với @BotFather)
3. Gửi `/start`
4. Bot sẽ trả lời với menu chính

## Các lệnh cơ bản để test

```
/start          - Khởi động bot
/help           - Xem trợ giúp
/menu           - Menu tương tác
/weather Hanoi  - Xem thời tiết Hà Nội
/ask Hello      - Hỏi AI
/crypto         - Xem giá crypto
```

## Troubleshooting

### Lỗi: "Module not found"
```bash
pip install -r requirements.txt --upgrade
```

### Lỗi: "BOT_TOKEN is required"
- Kiểm tra file `.env` có tồn tại không
- Kiểm tra BOT_TOKEN đã được set đúng không

### Lỗi: "Database error"
```bash
# Xóa database cũ
rmdir /s /q data

# Tạo lại
mkdir data

# Chạy lại bot
python main.py
```

### Lỗi: "AI provider not configured"
- Thêm ít nhất 1 AI provider API key vào `.env`
- Restart bot sau khi thêm key

### Bot không phản hồi
- Kiểm tra kết nối internet
- Kiểm tra BOT_TOKEN có đúng không
- Xem logs trong terminal để biết lỗi

## Chạy với Docker (Optional)

### Build image
```bash
docker build -t telegram-bot .
```

### Run container
```bash
docker run -d \
  --name telegram-bot \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  telegram-bot
```

### Xem logs
```bash
docker logs -f telegram-bot
```

## Development

### Chạy tests
```bash
pytest tests/
```

### Format code
```bash
black .
```

### Lint code
```bash
flake8 .
```

## Production deployment

### Sử dụng systemd (Linux)

Tạo file `/etc/systemd/system/telegram-bot.service`:

```ini
[Unit]
Description=Telegram Bot
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/telegram_bot
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable và start service:
```bash
sudo systemctl enable telegram-bot
sudo systemctl start telegram-bot
sudo systemctl status telegram-bot
```

### Sử dụng Docker Compose

Tạo file `docker-compose.yml`:

```yaml
version: '3.8'

services:
  bot:
    build: .
    env_file: .env
    volumes:
      - ./data:/app/data
    restart: unless-stopped
```

Run:
```bash
docker-compose up -d
```

## Monitoring

Bot tự động track các metrics:
- Command usage statistics
- AI provider health
- API response times
- Cache hit rates

Để xem dashboard (nếu có):
```
http://localhost:8080/dashboard
```

## Backup

### Backup database
```bash
# Manual backup
copy data\bot.db data\bot.db.backup

# Auto backup (Windows Task Scheduler)
# Tạo task chạy hàng ngày
```

### Backup .env
```bash
copy .env .env.backup
```

## Support

Nếu gặp vấn đề:
1. Xem logs trong terminal
2. Kiểm tra file `.env`
3. Đảm bảo đã install đủ dependencies
4. Restart bot

## Next Steps

- Thêm plugins mới theo nhu cầu
- Customize messages trong `i18n/vi.json`
- Cấu hình rate limiting phù hợp
- Setup monitoring và alerting
